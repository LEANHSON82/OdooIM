"""Helpdesk stage model.

Stages define the ticket lifecycle. A folded stage counts as closed, and archiving or
deleting a stage goes through a wizard so nobody hides or destroys ticket history by
accident.
"""

from odoo import fields, models, _
from odoo.tools.misc import unique


class HelpdeskStage(models.Model):
    """One ticket stage, shared by one or several helpdesk teams."""

    _name = 'helpdesk.stage'
    _description = 'Helpdesk Stage'
    _order = 'sequence, id'

    def _default_team_ids(self):
        """Attach a new stage to the team currently open in the context."""
        team_id = self.env.context.get('default_team_id')
        if team_id:
            return [(4, team_id, 0)]

    active = fields.Boolean(default=True)
    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(export_string_translation=False, default=10)
    fold = fields.Boolean(
        'Folded',
        help='Tickets in a folded stage are considered as closed.')
    team_ids = fields.Many2many(
        'helpdesk.team', relation='team_stage_rel', string='Helpdesk Teams',
        default=_default_team_ids, required=True)
    template_id = fields.Many2one(
        'mail.template', 'Email Template',
        domain="[('model', '=', 'helpdesk.ticket')]",
        help="Email automatically sent to the customer when the ticket reaches this stage.")
    legend_blocked = fields.Char(
        'Red Kanban Label', default=lambda s: s.env._('Blocked'), translate=True, required=True)
    legend_done = fields.Char(
        'Green Kanban Label', default=lambda s: s.env._('Ready'), translate=True, required=True)
    legend_normal = fields.Char(
        'Grey Kanban Label', default=lambda s: s.env._('In Progress'), translate=True, required=True)
    ticket_count = fields.Integer(compute='_compute_ticket_count', export_string_translation=False)
    color = fields.Integer(string='Color', export_string_translation=False)

    def _compute_ticket_count(self):
        """Count the tickets sitting in each stage."""
        res = self.env['helpdesk.ticket']._read_group(
            [('stage_id', 'in', self.ids)],
            ['stage_id'], ['__count'])
        stage_data = {stage.id: count for stage, count in res}
        for stage in self:
            stage.ticket_count = stage_data.get(stage.id, 0)

    def write(self, vals):
        """Archive the tickets of a stage at the same time as the stage itself."""
        if 'active' in vals and not vals['active']:
            self.env['helpdesk.ticket'].search([('stage_id', 'in', self.ids)]).write({'active': False})
        return super().write(vals)

    def action_unarchive(self):
        """Restore the stage and ask whether its tickets should come back too."""
        res = super().action_unarchive()
        stage_active = self.filtered(self._active_name)
        if stage_active and sum(stage_active.with_context(active_test=False).mapped('ticket_count')) > 0:
            wizard = self.env['helpdesk.stage.delete.wizard'].create({
                'stage_ids': stage_active.ids,
            })
            return {
                'name': _('Unarchive Tickets'),
                'view_mode': 'form',
                'res_model': 'helpdesk.stage.delete.wizard',
                'views': [(self.env.ref('im_helpdesk.view_helpdesk_stage_unarchive_wizard').id, 'form')],
                'type': 'ir.actions.act_window',
                'res_id': wizard.id,
                'target': 'new',
            }
        return res

    def action_unlink_wizard(self, stage_view=False):
        """Open the delete/archive wizard before a stage is removed.

        The wizard receives every team using the stage or holding tickets in it,
        so the user sees the real blast radius before confirming.
        """
        self = self.with_context(active_test=False)
        readgroup = self.with_context(active_test=False).env['helpdesk.ticket']._read_group(
            [('stage_id', 'in', self.ids), ('team_id', '!=', False)],
            ['team_id'])
        team_ids = list(unique([team.id for [team] in readgroup] + self.team_ids.ids))

        wizard = self.env['helpdesk.stage.delete.wizard'].create({
            'team_ids': team_ids,
            'stage_ids': self.ids
        })

        context = dict(self.env.context)
        context['stage_view'] = stage_view
        return {
            'name': _('Delete Stage'),
            'view_mode': 'form',
            'res_model': 'helpdesk.stage.delete.wizard',
            'views': [(self.env.ref('im_helpdesk.view_helpdesk_stage_delete_wizard').id, 'form')],
            'type': 'ir.actions.act_window',
            'res_id': wizard.id,
            'target': 'new',
            'context': context,
        }

    def action_open_helpdesk_ticket(self):
        """Open the tickets of this stage from its smart button."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("im_helpdesk.helpdesk_ticket_action_main_tree")
        action.update({
            'domain': [('stage_id', 'in', self.ids)],
            'context': {
                'default_stage_id': self.id,
            },
        })
        return action
