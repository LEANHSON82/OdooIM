"""Helpdesk team model and team-level automation.

This file holds the team configuration, the dashboard figures, the mail alias setup, the
feature group toggles, the assignment algorithms and the cron that closes inactive
tickets.
"""

import ast
import datetime
import heapq
import itertools
import pytz

from dateutil import relativedelta
from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.fields import Command, Domain
from odoo.tools import float_round
from odoo.addons.rating.models.rating_data import RATING_LIMIT_MIN
from odoo.addons.web.controllers.utils import clean_action


class HelpdeskTeam(models.Model):
    """How one helpdesk team receives, assigns and closes its tickets."""

    _name = 'helpdesk.team'
    _inherit = ['mail.alias.mixin', 'mail.thread', 'rating.parent.mixin']
    _description = "Helpdesk Team"
    _order = 'sequence,name'
    _rating_satisfaction_days = 7

    def _default_stage_ids(self):
        """Return the default set of stages used when a team is created."""
        default_stages = self.env['helpdesk.stage']
        for xml_id in ['stage_new', 'stage_in_progress', 'stage_solved', 'stage_cancelled']:
            stage = self.env.ref('im_helpdesk.%s' % xml_id, raise_if_not_found=False)
            if stage:
                default_stages += stage
        if not default_stages:
            default_stages = self.env['helpdesk.stage'].create({
                'name': _("New"),
                'sequence': 0,
                'template_id': self.env.ref('im_helpdesk.new_ticket_request_email_template', raise_if_not_found=False).id or None
            })
        return [Command.set(default_stages.ids)]

    name = fields.Char('Helpdesk Team', required=True, translate=True)
    description = fields.Html('About Team', translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    sequence = fields.Integer(export_string_translation=False, default=10)
    color = fields.Integer('Color Index', default=0)

    stage_ids = fields.Many2many(
        'helpdesk.stage', relation='team_stage_rel', string='Stages',
        default=_default_stage_ids,
        help="Stages the team will use. This team's tickets will only be able to be in these stages.")
    auto_assignment = fields.Boolean("Automatic Assignment")
    assign_method = fields.Selection([
            ('randomly', 'Each user is assigned an equal number of tickets'),
            ('balanced', 'Each user has an equal number of open tickets'),
            ('tags', 'Dispatch tickets based on tags'),
        ],
        string='Assignment Method', default='randomly', required=True,
        help="New tickets will automatically be assigned to the team members that are available, according to their working hours and their time off.")
    member_ids = fields.Many2many('res.users', string='Team Members',
        domain=lambda self: f"[('all_group_ids', 'in', {self.env.ref('im_helpdesk.group_helpdesk_user').id}), ('company_ids', 'in', [company_id])]",
        default=lambda self: self.env.user, required=True)
    privacy_visibility = fields.Selection([
        ('invited_internal', 'Invited internal users (private)'),
        ('internal', 'All internal users (company)'),
        ('portal', 'Invited portal users and all internal users (public)')],
        string='Visibility', required=True,
        default='portal')
    privacy_visibility_warning = fields.Char(compute='_compute_privacy_visibility_warning', export_string_translation=False)
    access_instruction_message = fields.Char(compute='_compute_access_instruction_message', export_string_translation=False)
    ticket_ids = fields.One2many('helpdesk.ticket', 'team_id', string='Tickets')

    use_alias = fields.Boolean('Use Alias', default=True)
    has_external_mail_server = fields.Boolean(compute='_compute_has_external_mail_server', export_string_translation=False)
    allow_portal_ticket_closing = fields.Boolean('Closure by Customers')
    use_rating = fields.Boolean('Customer Ratings')
    use_sla = fields.Boolean('SLA Policies', default=True)

    unassigned_tickets = fields.Integer(string='Unassigned Tickets', compute='_compute_unassigned_tickets')
    resource_calendar_id = fields.Many2one('resource.calendar', 'Working Hours',
        default=lambda self: self.env.company.resource_calendar_id,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), ('flexible_hours', '=', False), ('attendance_ids', '!=', False)]",
        help="Working hours used to determine the deadline of SLA Policies.")
    open_ticket_count = fields.Integer("# Open Tickets", compute='_compute_open_ticket_count')
    sla_policy_count = fields.Integer("# SLA Policy", compute='_compute_sla_policy_count')
    ticket_closed = fields.Integer(string='Ticket Closed', compute='_compute_ticket_closed')
    success_rate = fields.Float(string='Success Rate', compute='_compute_success_rate', groups="im_helpdesk.group_use_sla")
    urgent_ticket = fields.Integer(string='# Urgent Ticket', compute='_compute_urgent_ticket')
    sla_failed = fields.Integer(string='Failed SLA Ticket', compute='_compute_sla_failed')

    auto_close_ticket = fields.Boolean('Automatic Closing')
    auto_close_day = fields.Integer('Inactive Period(days)',
        default=7,
        help="Period of inactivity after which tickets will be automatically closed.")
    from_stage_ids = fields.Many2many('helpdesk.stage', relation='team_stage_auto_close_from_rel',
        string='In Stages',
        domain="[('id', 'in', stage_ids)]")
    to_stage_id = fields.Many2one('helpdesk.stage',
        string='Move to Stage',
        compute="_compute_assign_stage_id", readonly=False, store=True,
        domain="[('id', 'in', stage_ids)]")
    alias_email_from = fields.Char(compute='_compute_alias_email_from', export_string_translation=False)

    @api.depends('auto_close_ticket', 'stage_ids')
    def _compute_assign_stage_id(self):
        """Pick the target stage used when tickets are closed automatically.

        The first folded stage by sequence wins. With no folded stage, the last
        configured stage is used as a fallback.
        """
        stages_dict = {stage['id']: 1 if stage['fold'] else 2 for stage in self.env['helpdesk.stage'].search_read([('id', 'in', self.stage_ids.ids), ('fold', '=', True)], ['id', 'fold'])}
        for team in self:
            if not team.stage_ids:
                team.to_stage_id = False
                continue
            stage_ids = sorted([
                (val, stage_id) for stage_id, val in stages_dict.items() if stage_id in team.stage_ids.ids
            ])
            team.to_stage_id = stage_ids[0][1] if stage_ids else team.stage_ids and team.stage_ids.ids[-1]

    def _compute_alias_email_from(self):
        """Compute the reply-to address shown for the team mail alias."""
        res = self._notify_get_reply_to()
        for team in self:
            team.alias_email_from = res.get(team.id, False)

    def _compute_has_external_mail_server(self):
        """Flag whether an external mail server is configured globally."""
        self.has_external_mail_server = self.env['ir.config_parameter'].sudo().get_param('base_setup.default_external_email_server')

    def _compute_unassigned_tickets(self):
        """Count the open tickets of the team that have no assignee."""
        ticket_data = self.env['helpdesk.ticket']._read_group([
            ('user_id', '=', False),
            ('team_id', 'in', self.ids),
            ('stage_id.fold', '=', False),
        ], ['team_id'], ['__count'])
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.unassigned_tickets = mapped_data.get(team.id, 0)

    def _compute_ticket_closed(self):
        """Count the tickets the team closed over the last seven days."""
        dt = datetime.datetime.combine(datetime.date.today() - relativedelta.relativedelta(days=6), datetime.time.min)
        ticket_data = self.env['helpdesk.ticket']._read_group([
            ('team_id', 'in', self.ids),
            ('stage_id.fold', '=', True),
            ('close_date', '>=', dt)],
            ['team_id'], ['__count'])
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.ticket_closed = mapped_data.get(team.id, 0)

    def _compute_success_rate(self):
        """Compute the seven-day SLA success rate of the team.

        A team without SLA gets -1, so the dashboard widget can hide or special-
        case the metric instead of showing a misleading zero.
        """
        dt = datetime.datetime.combine(datetime.date.today() - relativedelta.relativedelta(days=6), datetime.time.min)
        sla_teams = self.filtered('use_sla')
        domain = [
            ('team_id', 'in', sla_teams.ids),
            '&', ('stage_id.fold', '=', True), ('close_date', '>=', dt)
        ]
        sla_tickets_and_failed_tickets_per_team = defaultdict(lambda: [0, 0])
        today = fields.Datetime.now()
        tickets_sla_count = self.env['helpdesk.ticket']._read_group(domain + [
            '|', ('sla_reached', '=', True), ('sla_reached_late', '=', True)],
            ['team_id'], ['__count']
        )
        tickets_success_count = self.env['helpdesk.ticket']._read_group(domain + [
            '|', ('sla_deadline', '<', today), ('sla_reached_late', '=', True)],
            ['team_id'], ['__count']
        )
        for team, team_count in tickets_sla_count:
            sla_tickets_and_failed_tickets_per_team[team.id][0] = team_count
        for team, team_count in tickets_success_count:
            sla_tickets_and_failed_tickets_per_team[team.id][1] = team_count
        for team in sla_teams:
            if not sla_tickets_and_failed_tickets_per_team.get(team.id):
                team.success_rate = -1
                continue
            total_count = sla_tickets_and_failed_tickets_per_team[team.id][0]
            success_count = total_count - sla_tickets_and_failed_tickets_per_team[team.id][1]
            team.success_rate = float_round(success_count * 100 / total_count, 2) if total_count else 0.0
        (self - sla_teams).success_rate = -1

    def _compute_urgent_ticket(self):
        """Count the open urgent tickets of each team."""
        ticket_data = self.env['helpdesk.ticket']._read_group([
            ('team_id', 'in', self.ids),
            ('stage_id.fold', "=", False),
            ('priority', '=', 3)],
            ['team_id'], ['__count'])
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.urgent_ticket = mapped_data.get(team.id, 0)

    def _compute_sla_failed(self):
        """Count the open tickets whose current SLA status is failing."""
        ticket_data = self.env['helpdesk.ticket']._read_group([
            ('team_id', 'in', self.ids),
            ('stage_id.fold', '=', False),
            ('sla_fail', '=', True)],
            ['team_id'], ['__count'])
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.sla_failed = mapped_data.get(team.id, 0)

    def _compute_open_ticket_count(self):
        """Count the open tickets of each team."""
        ticket_data = self.env['helpdesk.ticket']._read_group([
            ('team_id', 'in', self.ids), ('stage_id.fold', '=', False)
        ], ['team_id'], ['__count'])
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.open_ticket_count = mapped_data.get(team.id, 0)

    def _compute_sla_policy_count(self):
        """Count the SLA policies configured on each team."""
        sla_data = self.env['helpdesk.sla']._read_group([('team_id', 'in', self.ids)], ['team_id'], ['__count'])
        mapped_data = {team.id: count for team, count in sla_data}
        for team in self:
            team.sla_policy_count = mapped_data.get(team.id, 0)

    @api.onchange('use_alias', 'name')
    def _onchange_use_alias(self):
        """Clear or generate the alias name when the alias setup changes."""
        if not self.use_alias:
            self.alias_name = False
        if self._origin.id and self.use_alias and not self.alias_name and self.name:
            self.alias_name = self._alias_get_creation_values()['alias_name'].lower()

    @api.depends('privacy_visibility')
    def _compute_privacy_visibility_warning(self):
        """Warn when a visibility change affects the current followers."""
        for team in self:
            if not team.ids:
                team.privacy_visibility_warning = ''
            elif team.privacy_visibility == 'portal' and team._origin.privacy_visibility != 'portal':
                team.privacy_visibility_warning = _('Customers will be added to the followers of their tickets.')
            elif team.privacy_visibility != 'portal' and team._origin.privacy_visibility == 'portal':
                team.privacy_visibility_warning = _('Portal users will be removed from the followers of the team and its tickets.')
            else:
                team.privacy_visibility_warning = ''

    @api.depends('privacy_visibility')
    def _compute_access_instruction_message(self):
        """Explain who can be invited under the chosen visibility mode."""
        for team in self:
            if team.privacy_visibility == 'portal':
                team.access_instruction_message = _('Grant portal users access to your helpdesk team or tickets by adding them as followers.')
            elif team.privacy_visibility == 'invited_internal':
                team.access_instruction_message = _('Grant employees access to your helpdesk team or tickets by adding them as followers.')
            else:
                team.access_instruction_message = ''

    @api.onchange('auto_assignment')
    def _onchange_assign_method(self):
        """Make sure auto-assignment has at least one team member to pick from."""
        if not self.member_ids:
            self.member_ids = [Command.set(self.env.user.ids)]

    # ------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------

    @api.depends('company_id')
    @api.depends_context('allowed_company_ids')
    def _compute_display_name(self):
        """Append the company name to the default team in a multi-company context."""
        super()._compute_display_name()
        if len(self.env.context.get('allowed_company_ids', [])) <= 1:
            return
        team_default_name = _('Customer Care')
        for team in self:
            if team.name == team_default_name:
                team.display_name = f'{team.display_name} - {team.company_id.name}'

    @api.model_create_multi
    def create(self, vals_list):
        """Create the team and sync the SLA/rating groups and the cron state."""
        teams = super(HelpdeskTeam, self.with_context(mail_create_nosubscribe=True)).create(vals_list)
        teams.sudo()._check_sla_group()
        teams.sudo()._check_rating_group()
        if teams.filtered(lambda x: x.auto_close_ticket):
            teams._update_cron()
        return teams

    def write(self, vals):
        """Update the team, keeping tickets, groups and cron in sync."""
        if vals.get('privacy_visibility'):
            self._change_privacy_visibility(vals['privacy_visibility'])
        if 'alias_name' in vals and not vals['alias_name'] and (vals['use_alias'] if 'use_alias' in vals else self.use_alias):
            default_alias = self.name.replace(' ', '-') if self.name else ''
            vals['alias_name'] = self.alias_name or default_alias

        result = super().write(vals)
        if 'active' in vals:
            self.with_context(active_test=False).mapped('ticket_ids').write({'active': vals['active']})
        if 'use_sla' in vals:
            self.sudo()._check_sla_group()
        if 'use_rating' in vals:
            self.sudo()._check_rating_group()
        if 'auto_close_ticket' in vals:
            self._update_cron()
        return result

    def unlink(self):
        """Delete the stages used only by the teams being deleted."""
        stages = self.mapped('stage_ids').filtered(lambda stage: stage.team_ids <= self)
        stages.unlink()
        return super().unlink()

    def copy_data(self, default=None):
        """Duplicate the team with a recognisable '(copy)' suffix."""
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._("%s (copy)", team.name)) for team, vals in zip(self, vals_list)]

    def _change_privacy_visibility(self, new_visibility):
        """Apply the follower side effects of a team visibility change.

        Moving to portal-public visibility subscribes the ticket customers so
        they can reach their tickets. Leaving portal visibility removes portal
        users from the team and ticket followers, to keep things private.
        """
        for team in self:
            if team.privacy_visibility == new_visibility:
                continue
            if new_visibility == 'portal':
                for ticket in team.mapped('ticket_ids').filtered('partner_id'):
                    ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
            elif team.privacy_visibility == 'portal':
                portal_users = team.message_partner_ids.user_ids.filtered('share')
                team.message_unsubscribe(partner_ids=portal_users.partner_id.ids)
                team.mapped('ticket_ids')._unsubscribe_portal_users()

    @api.model
    def _update_cron(self):
        """Enable or disable the auto-close cron according to the team setup."""
        cron = self.env.ref('im_helpdesk.ir_cron_auto_close_ticket', raise_if_not_found=False)
        cron and cron.toggle(model=self._name, domain=[
            ('auto_close_ticket', '=', True),
            ('auto_close_day', '>', 0),
        ])

    def _get_helpdesk_user_group(self):
        """Return the base Helpdesk User security group."""
        return self.env.ref('im_helpdesk.group_helpdesk_user')

    def _get_helpdesk_use_sla_group(self):
        """Return the optional group that reveals the SLA features."""
        return self.env.ref('im_helpdesk.group_use_sla')

    def _get_helpdesk_use_rating_group(self):
        """Return the optional group that reveals the rating features."""
        return self.env.ref('im_helpdesk.group_use_rating')

    def _check_sla_feature_enabled(self, check_user_has_group=False):
        """Return whether SLA is enabled anywhere, optionally checking one user."""
        user_has_group = self.env.user.has_group('im_helpdesk.group_use_sla') if check_user_has_group else True
        return user_has_group and self.env['helpdesk.team'].search([('use_sla', '=', True)], limit=1)

    def _check_rating_feature_enabled(self, check_user_has_group=False):
        """Return whether rating is enabled anywhere, optionally checking one user."""
        user_has_group = self.env.user.has_group('im_helpdesk.group_use_rating') if check_user_has_group else True
        return user_has_group and self.env['helpdesk.team'].search([('use_rating', '=', True)], limit=1)

    def _check_sla_group(self):
        """Sync the SLA policies and the implied group with the team setup.

        Enabling SLA on any team grants the SLA feature group through the base
        helpdesk group. Disabling it on the last team removes that implied group
        and deactivates the policies of the teams that no longer use SLA.
        """
        sla_teams = self.filtered('use_sla')
        non_sla_teams = self - sla_teams
        use_sla_group = helpdesk_user_group = None
        user_has_use_sla_group = self.env.user.has_group('im_helpdesk.group_use_sla')

        if sla_teams:
            if not user_has_use_sla_group:
                use_sla_group = self._get_helpdesk_use_sla_group()
                helpdesk_user_group = self._get_helpdesk_user_group()
                helpdesk_user_group.write({'implied_ids': [Command.link(use_sla_group.id)]})
            self.env['helpdesk.sla'].with_context(active_test=False).search([
                ('team_id', 'in', sla_teams.ids), ('active', '=', False),
            ]).write({'active': True})

        if non_sla_teams:
            self.env['helpdesk.sla'].search([('team_id', 'in', non_sla_teams.ids)]).write({'active': False})
            if user_has_use_sla_group and not self._check_sla_feature_enabled():
                use_sla_group = use_sla_group or self._get_helpdesk_use_sla_group()
                helpdesk_user_group = helpdesk_user_group or self._get_helpdesk_user_group()
                helpdesk_user_group.write({'implied_ids': [Command.unlink(use_sla_group.id)]})
                use_sla_group.write({'user_ids': [Command.clear()]})

    def _check_rating_group(self):
        """Sync the rating templates and the implied group with the team setup."""
        rating_teams = self.filtered('use_rating')
        user_has_use_rating_group = self.env.user.has_group('im_helpdesk.group_use_rating')
        rating_helpdesk_email_template = self.env.ref('im_helpdesk.rating_ticket_request_email_template')

        if rating_teams and not user_has_use_rating_group:
            self._get_helpdesk_user_group()\
                .write({'implied_ids': [Command.link(self._get_helpdesk_use_rating_group().id)]})
            if not rating_helpdesk_email_template.active:
                rating_helpdesk_email_template.active = True
        elif self - rating_teams and user_has_use_rating_group and not self._check_rating_feature_enabled():
            use_rating_group = self._get_helpdesk_use_rating_group()
            self._get_helpdesk_user_group()\
                .write({'implied_ids': [Command.unlink(use_rating_group.id)]})
            use_rating_group.write({'user_ids': [Command.clear()]})
            if rating_helpdesk_email_template.active:
                rating_helpdesk_email_template.active = False
            self.env['helpdesk.stage'].search([('template_id', '=', self.env.ref('im_helpdesk.rating_ticket_request_email_template').id)]).template_id = False

    # ------------------------------------------------------------
    # Mail Alias Mixin
    # ------------------------------------------------------------

    def _alias_get_creation_values(self):
        """Prepare the mail alias defaults so incoming email opens a ticket."""
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get('helpdesk.ticket').id
        if self._origin.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or "{}")
            defaults['team_id'] = self.id
            if not self.alias_name:
                base_email_alias = self.name.lower().replace(' ', '-')
                values['alias_name'] = self._ensure_unique_email_alias(base_email_alias)
        return values

    def _ensure_unique_email_alias(self, email_alias):
        """Return a sanitised alias name that no existing alias already uses."""
        existing_aliases = self._get_existing_email_aliases(email_alias)
        modified_email_alias = email_alias
        counter = 2
        while modified_email_alias in existing_aliases:
            modified_email_alias = f"{email_alias}-{counter}"
            counter += 1
        return self.env['mail.alias']._sanitize_alias_name(modified_email_alias)

    def _get_existing_email_aliases(self, email_alias):
        """Return the existing aliases that look like the requested one."""
        existing_aliases = self.env['mail.alias'].search([('alias_name', 'ilike', email_alias)])
        return {alias.alias_name for alias in existing_aliases}

    # ------------------------------------------------------------
    # Business methods
    # ------------------------------------------------------------

    @api.model
    def retrieve_dashboard(self):
        """Build the helpdesk dashboard payload for the current user.

        The returned dictionary holds the personal targets, the groups of open
        personal tickets, the tickets closed today, the seven-day metrics, the
        rating metrics, and demo figures while the database still has no ticket.
        """
        user_uses_sla = self._check_sla_feature_enabled(check_user_has_group=True)

        HelpdeskTicket = self.env['helpdesk.ticket']
        show_demo = not bool(HelpdeskTicket.search([], limit=1))
        result = {
            'helpdesk_target_closed': self.env.user.helpdesk_target_closed,
            'helpdesk_target_rating': self.env.user.helpdesk_target_rating,
            'helpdesk_target_success': self.env.user.helpdesk_target_success,
            'today': {'sla_ticket_count': 0, 'count': 0, 'rating': 0, 'success': 0},
            '7days': {'sla_ticket_count': 0, 'count': 0, 'rating': 0, 'success': 0},
            'my_all': {'count': 0, 'hours': 0, 'failed': 0},
            'my_high': {'count': 0, 'hours': 0, 'failed': 0},
            'my_urgent': {'count': 0, 'hours': 0, 'failed': 0},
            'show_demo': show_demo,
            'rating_enable': False,
            'success_rate_enable': user_uses_sla
        }

        if show_demo:
            result.update({
                'my_all': {'count': 10, 'hours': 30, 'failed': 4},
                'my_high': {'count': 3, 'hours': 10, 'failed': 2},
                'my_urgent': {'count': 2, 'hours': 15, 'failed': 1},
                'today': {'sla_ticket_count': 1, 'count': 1, 'rating': 2.5, 'success': 50},
                '7days': {'sla_ticket_count': 1, 'count': 15, 'rating': 3.5, 'success': 80},
                'helpdesk_target_rating': 3.5,
                'helpdesk_target_success': 85,
                'helpdesk_target_closed': 12,
            })
            return result

        def _is_sla_failed(data):
            """Return whether a ticket row from search_read is failing its SLA."""
            deadline = data.get('sla_deadline')
            sla_deadline = fields.Datetime.now() > deadline if deadline else False
            return sla_deadline or data.get('sla_reached_late')

        def add_to(ticket, key="my_all"):
            """Add one ticket row into a dashboard data bucket."""
            result[key]['count'] += 1
            result[key]['hours'] += ticket['open_hours']
            if _is_sla_failed(ticket):
                result[key]['failed'] += 1

        domain = Domain('user_id', '=', self.env.uid)
        tickets = HelpdeskTicket.search_read(
            domain & Domain('stage_id.fold', '=', False),
            ['sla_deadline', 'open_hours', 'sla_reached_late', 'priority']
        )
        for ticket in tickets:
            add_to(ticket, 'my_all')
            if ticket['priority'] == '2':
                add_to(ticket, 'my_high')
            if ticket['priority'] == '3':
                add_to(ticket, 'my_urgent')

        group_fields = []
        if user_uses_sla:
            group_fields = ['sla_reached_late', 'sla_reached']

        today = self._local_midnight_as_utc()
        tickets = HelpdeskTicket._read_group(domain + [('stage_id.fold', '=', True), ('close_date', '>=', today)], group_fields, ['__count'])
        for row in tickets:
            if not user_uses_sla:
                [count] = row
            else:
                sla_reached_late, sla_reached, count = row
                if sla_reached or sla_reached_late:
                    result['today']['sla_ticket_count'] += count
                    if not sla_reached_late:
                        result['today']['success'] += count
            result['today']['count'] += count

        dt = fields.Datetime.to_string((today - relativedelta.relativedelta(days=6)))
        tickets = HelpdeskTicket._read_group(domain + [('stage_id.fold', '=', True), ('close_date', '>=', dt)], group_fields, ['__count'])
        for row in tickets:
            if not user_uses_sla:
                [count] = row
            else:
                sla_reached_late, sla_reached, count = row
                if sla_reached or sla_reached_late:
                    result['7days']['sla_ticket_count'] += count
                    if not sla_reached_late:
                        result['7days']['success'] += count
            result['7days']['count'] += count

        result['today']['success'] = fields.Float.round(result['today']['success'] * 100 / (result['today']['sla_ticket_count'] or 1), 2)
        result['7days']['success'] = fields.Float.round(result['7days']['success'] * 100 / (result['7days']['sla_ticket_count'] or 1), 2)
        result['my_all']['hours'] = fields.Float.round(result['my_all']['hours'] / (result['my_all']['count'] or 1), 2)
        result['my_high']['hours'] = fields.Float.round(result['my_high']['hours'] / (result['my_high']['count'] or 1), 2)
        result['my_urgent']['hours'] = fields.Float.round(result['my_urgent']['hours'] / (result['my_urgent']['count'] or 1), 2)

        if self._check_rating_feature_enabled(check_user_has_group=True):
            result['rating_enable'] = True
            one_week_before = today - relativedelta.relativedelta(weeks=1)
            helpdesk_ratings = self.env['rating.rating'].search([
                ('res_model', '=', 'helpdesk.ticket'),
                ('res_id', '!=', False),
                ('write_date', '>', fields.Datetime.to_string(one_week_before)),
                ('write_date', '<=', fields.Date.today()),
                ('rating', '>=', RATING_LIMIT_MIN),
                ('consumed', '=', True),
            ])
            tickets = HelpdeskTicket.search([('id', 'in', helpdesk_ratings.mapped('res_id')), ('user_id', '=', self.env.uid)])
            today_rating_stat = {'count': 0.0, 'score': 0.0}
            rating_stat = {**today_rating_stat}
            for rating in helpdesk_ratings:
                if rating.res_id not in tickets.ids:
                    continue
                if rating.write_date >= today:
                    today_rating_stat['count'] += 1
                    today_rating_stat['score'] += rating.rating
                rating_stat['score'] += rating.rating
                rating_stat['count'] += 1

            def average_score(d):
                """Return the average rating score, rounded for the dashboard."""
                return fields.Float.round(d['score'] / d['count'] if d['count'] > 0 else 0.0, 2)

            result['today']['rating'] = average_score(today_rating_stat)
            result['7days']['rating'] = average_score(rating_stat)
        return result

    def _action_view_rating(self, period=False, only_closed_tickets=False, user_id=None):
        """Return the action opening the ratings of the selected teams.

        The optional arguments narrow the source tickets by closed state or by
        user. The ``period`` argument only lets the caller say which dashboard
        tile opened the action; the real domain is built below.
        """
        action = self.env["ir.actions.actions"]._for_xml_id("im_helpdesk.rating_rating_action_helpdesk")
        action = clean_action(action, self.env)
        domain = [('team_id', 'in', self.ids)]
        context = dict(ast.literal_eval(action.get('context', {})), search_default_my_ratings=True)

        if only_closed_tickets:
            domain += [('stage_id.fold', '=', True)]
        if user_id:
            domain += [('user_id', '=', user_id)]

        ticket_ids = self.env['helpdesk.ticket'].search(domain).ids
        action.update({
            'context': context,
            'domain': [('res_id', 'in', ticket_ids), ('rating', '>=', RATING_LIMIT_MIN), ('res_model', '=', 'helpdesk.ticket'), ('consumed', '=', True)],
        })
        return action

    def action_view_ticket(self):
        """Open the generic ticket action of the team."""
        action = self.env["ir.actions.actions"]._for_xml_id("im_helpdesk.helpdesk_ticket_action_team")
        action['display_name'] = self.name
        return action

    def _get_action_view_ticket_params(self, is_ticket_closed=False):
        """Return the action parameters shared by open and recently closed tickets."""
        domain = Domain('team_id', 'in', self.ids)
        context = {
            'search_default_is_open': not is_ticket_closed,
            'default_team_id': self.id,
        }
        view_mode = 'list,kanban,form,activity,pivot,graph'
        if is_ticket_closed:
            domain &= Domain('close_date', '>=', self._local_midnight_as_utc() - datetime.timedelta(days=6))
            context.update(search_default_closed_on='custom_closed_on_last_7_days')
        return {
            'domain': domain,
            'context': context,
            'view_mode': view_mode,
        }

    def action_view_closed_ticket(self):
        """Open the tickets the team closed recently."""
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params(True)
        action.update({
            **action_params,
            'domain': Domain.AND([action_params['domain'], [('stage_id.fold', '=', True)]]),
        })
        return action

    def action_view_success_rate(self):
        """Open the recently closed tickets, filtered on SLA success."""
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params(True)
        action.update(
            domain=Domain.AND([
                action_params['domain'],
                [('team_id', 'in', self.ids), ('stage_id.fold', '=', True)],
            ]),
            context={
                **action_params['context'],
                'search_default_sla_success': True,
            },
            view_mode=action_params['view_mode'],
            views=[(False, view) for view in action_params['view_mode'].split(",")],
        )
        return action

    def action_view_customer_satisfaction(self):
        """Open the consumed customer ratings of the selected teams."""
        action = self._action_view_rating(period='seven_days')
        action['context'] = {**self.env.context, **action['context'], 'search_default_my_ratings': False}
        return action

    def action_view_open_ticket(self):
        """Open the tickets of the team that are still open."""
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params()
        action.update({
            'context': action_params['context'],
            'domain': action_params['domain'],
        })
        return action

    def action_view_urgent(self):
        """Open the open tickets with urgent priority."""
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params()
        action.update({
            'context': {
                **action_params['context'],
                'search_default_urgent_priority': True,
            },
        })
        return action

    def action_view_sla_failed(self):
        """Open the open tickets whose SLA has failed."""
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params()
        action.update({
            'context': {
                **action_params['context'],
                'search_default_sla_failed': True,
            },
            'domain': Domain.AND([action_params['domain'], [('sla_fail', '=', True)]]),
        })
        return action

    def action_view_rating_today(self):
        """Open today's ratings of the teams the current user belongs to."""
        return self.search([('member_ids', 'in', self.env.uid)])._action_view_rating(period='today', user_id=self.env.uid)

    def action_view_rating_7days(self):
        """Open the seven-day ratings of the teams the current user belongs to."""
        return self.search([('member_ids', 'in', self.env.uid)])._action_view_rating(period='seven_days', user_id=self.env.uid)

    def action_view_team_rating(self):
        """Open the team ratings, switching to form view when there is only one."""
        self.ensure_one()
        action = self._action_view_rating()
        ratings = self.env['rating.rating'].search(action['domain'])
        if len(ratings) == 1:
            action.update({
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_id': ratings.id
            })
        else:
            action['context'] = {'search_default_filter_rated_on': 'custom_rated_on_last_30_days'}
        return action

    def action_view_open_ticket_view(self):
        """Open the open tickets from the smart button of the team form."""
        action = self.action_view_ticket()
        action.update({
            'display_name': _("Tickets"),
            'domain': [('team_id', '=', self.id), ('stage_id.fold', '=', False)],
        })
        return action

    def action_view_sla_policy(self):
        """Open the SLA policies of the team, or the form when there is only one."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("im_helpdesk.helpdesk_sla_action")
        if self.sla_policy_count == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.env['helpdesk.sla'].search([('team_id', '=', self.id)], limit=1).id,
                'views': [(False, 'form')],
            })
        action.update({
            'context': {'default_team_id': self.id},
            'domain': [('team_id', '=', self.id)],
        })
        return action

    def _determine_user_to_assign(self, count_per_team, force_method=False):
        """Pick the assignee for a team, either randomly or balanced.

        ``count_per_team`` maps a team record to how many tickets need an
        assignee. The result maps each team id to an ordered list of user ids,
        favouring the users whose calendar puts them at work soonest.
        """
        team_without_manually = self.env['helpdesk.team'].browse({
            team.id
            for team in count_per_team
            if team.auto_assignment and (force_method or team.assign_method in ['randomly', 'balanced'])
        })
        result = {team.id: [False] * count for team, count in count_per_team.items()}
        users_per_working_days = team_without_manually.member_ids._get_working_users_per_first_working_day()
        for team in team_without_manually:
            if not team.member_ids:
                continue
            count = count_per_team[team]
            member_ids = team.member_ids.ids
            for user_ids in users_per_working_days:
                if any(user_id in member_ids for user_id in user_ids):
                    member_ids = [user_id for user_id in user_ids if user_id in member_ids]
                    break

            assign_method = force_method or team.assign_method
            if assign_method == 'randomly':
                last_assigned_user = self.env['helpdesk.ticket'].search([('team_id', '=', team.id), ('user_id', '!=', False)], order='create_date desc, id desc', limit=1).user_id
                offset = 0
                if last_assigned_user:
                    for member in team.member_ids:
                        if member.id in member_ids:
                            offset = (offset + 1) % len(member_ids)
                        if member == last_assigned_user:
                            break
                result[team.id] = list(itertools.islice(itertools.cycle(member_ids), offset, offset + count))
            elif assign_method == 'balanced':
                ticket_count_data = self.env['helpdesk.ticket']._read_group([('stage_id.fold', '=', False), ('user_id', 'in', member_ids), ('team_id', '=', team.id)], ['user_id'], ['__count'])
                open_ticket_per_user_map = dict.fromkeys(member_ids, 0)
                open_ticket_per_user_map.update((user.id, count) for user, count in ticket_count_data)
                selected_user_ids = []
                heap = [(open_tickets, user_id) for user_id, open_tickets in open_ticket_per_user_map.items()]
                heapq.heapify(heap)
                for _dummy in range(count):
                    open_tickets, user_id = heapq.heappop(heap)
                    selected_user_ids.append(user_id)
                    heapq.heappush(heap, (open_tickets + 1, user_id))
                result[team.id] = selected_user_ids
        return result

    def _determine_stage(self):
        """Return the first stage by sequence for every team in ``self``."""
        result = dict.fromkeys(self.ids, self.env['helpdesk.stage'])
        for team in self:
            result[team.id] = self.env['helpdesk.stage'].search([('team_ids', 'in', team.id)], order='sequence', limit=1)
        return result

    def _get_closing_stage(self):
        """Return the stage used when a ticket is closed from portal or automation."""
        closed_stage = self.stage_ids.filtered(lambda stage: stage.fold)
        if not closed_stage:
            closed_stage = self.stage_ids[-1]
        return closed_stage

    def _cron_auto_close_tickets(self):
        """Scheduled job closing the inactive tickets of the configured teams.

        A ticket counts as inactive when its last write is older than the team
        threshold and it sits in one of the configured source stages; with no
        source stage configured, every unfolded stage qualifies.
        """
        teams = self.env['helpdesk.team'].search_read(
            domain=[
                ('auto_close_ticket', '=', True),
                ('auto_close_day', '>', 0),
                ('to_stage_id', '!=', False)],
            fields=[
                'id',
                'auto_close_day',
                'from_stage_ids',
                'to_stage_id']
        )
        teams_dict = defaultdict(dict)
        today = fields.Datetime.today()
        for team in teams:
            team['threshold_date'] = today - relativedelta.relativedelta(days=team['auto_close_day'])
            teams_dict[team['id']] = team
        tickets_domain = [('stage_id.fold', '=', False), ('team_id', 'in', list(teams_dict.keys()))]
        tickets = self.env['helpdesk.ticket'].search(tickets_domain)

        def is_inactive_ticket(ticket):
            """Return whether the ticket matches the auto-close conditions of its team.
            """
            team = teams_dict[ticket.team_id.id]
            is_write_date_ok = ticket.write_date <= team['threshold_date']
            if team['from_stage_ids']:
                is_stage_ok = ticket.stage_id.id in team['from_stage_ids']
            else:
                is_stage_ok = not ticket.stage_id.fold
            return is_write_date_ok and is_stage_ok

        inactive_tickets = tickets.filtered(is_inactive_ticket)
        for ticket in inactive_tickets:
            if teams_dict[ticket.team_id.id]['to_stage_id']:
                ticket.write({'stage_id': teams_dict[ticket.team_id.id]['to_stage_id'][0]})

    def _local_midnight_as_utc(self):
        """Return today's local midnight as a naive UTC datetime."""
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        return datetime.datetime.combine(now.date(), datetime.time.min, now.tzinfo).astimezone(pytz.utc).replace(tzinfo=None)
