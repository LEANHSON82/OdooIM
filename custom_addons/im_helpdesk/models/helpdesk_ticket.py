"""Model ticket Helpdesk và logic nghiệp vụ cấp ticket.

File này quản lý các field vòng đời ticket, tự động gắn tag/điều hướng team, tự
phân công, tạo trạng thái SLA, link portal, đồng bộ partner, hành vi mail thread
và tích hợp rating.
"""

import ast
import re
import unicodedata
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from lxml import html

from odoo import api, fields, models, tools, _
from odoo.fields import Command, Domain
from odoo.tools import html2plaintext, html_sanitize, LazyTranslate
from odoo.addons.web.controllers.utils import clean_action

_lt = LazyTranslate(__name__)

TICKET_PRIORITY = [
    ('0', 'Low priority'),
    ('1', 'Medium priority'),
    ('2', 'High priority'),
    ('3', 'Urgent'),
]


class HelpdeskTicket(models.Model):
    """Biểu diễn một yêu cầu hỗ trợ khách hàng do team helpdesk xử lý."""

    _name = 'helpdesk.ticket'
    _description = 'Helpdesk Ticket'
    _order = 'priority desc, id desc'
    _mail_defaults_to_email = True
    _mail_thread_customer = True
    _primary_email = 'partner_email'
    _inherit = [
        'portal.mixin',
        'mail.thread.cc',
        'utm.mixin',
        'rating.mixin',
        'mail.activity.mixin',
        'mail.tracking.duration.mixin',
    ]
    _track_duration_field = 'stage_id'

    @api.model
    def default_get(self, fields):
        """Gán mặc định stage và người phụ trách theo team helpdesk đã chọn."""
        result = super().default_get(fields)
        if result.get('team_id') and fields:
            team = self.env['helpdesk.team'].browse(result['team_id'])
            if 'stage_id' in fields and 'stage_id' not in result:
                result['stage_id'] = team._determine_stage()[team.id].id
            if 'user_id' in fields and 'user_id' not in result and ('stage_id' in fields and not self.env['helpdesk.stage'].browse(result['stage_id']).fold):
                result['user_id'] = team._determine_user_to_assign({team: 1})[team.id][0]
        return result

    def _default_team_id(self):
        """Chọn team của user hiện tại, nếu không có thì lấy team đầu tiên."""
        team_id = self.env['helpdesk.team'].search([('member_ids', 'in', self.env.uid)], limit=1).id
        if not team_id:
            team_id = self.env['helpdesk.team'].search([], limit=1).id
        return team_id

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Mở rộng group kanban theo các stage khả dụng của team mặc định."""
        search_domain = [('id', 'in', stages.ids)]
        if self.env.context.get('default_team_id'):
            search_domain = ['|', ('team_ids', 'in', self.env.context['default_team_id'])] + search_domain
        return stages.search(search_domain)

    name = fields.Char(string='Subject', required=True, index=True, tracking=True)
    team_id = fields.Many2one('helpdesk.team', string='Helpdesk Team',
        default=lambda self: self._default_team_id(), index=True, tracking=True)
    use_sla = fields.Boolean(related='team_id.use_sla')
    team_privacy_visibility = fields.Selection(related='team_id.privacy_visibility', export_string_translation=False)
    description = fields.Html(sanitize_attributes=False)
    active = fields.Boolean(default=True)
    tag_ids = fields.Many2many('helpdesk.tag', string='Tags')
    company_id = fields.Many2one(related='team_id.company_id', string='Company', store=True, readonly=True)
    color = fields.Integer(string='Color Index')
    kanban_state = fields.Selection([
        ('normal', 'In progress'),
        ('done', 'Ready'),
        ('blocked', 'Blocked')], string='Kanban State',
        copy=False, default='normal', required=True)
    kanban_state_label = fields.Char(compute='_compute_kanban_state_label', string='Kanban State Label', tracking=True)
    legend_blocked = fields.Char(related='stage_id.legend_blocked', string='Kanban Blocked Explanation', readonly=True, related_sudo=False)
    legend_done = fields.Char(related='stage_id.legend_done', string='Kanban Valid Explanation', readonly=True, related_sudo=False)
    legend_normal = fields.Char(related='stage_id.legend_normal', string='Kanban Ongoing Explanation', readonly=True, related_sudo=False)
    domain_user_ids = fields.Many2many('res.users', compute='_compute_domain_user_ids', export_string_translation=False)
    user_id = fields.Many2one(
        'res.users', string='Assigned to', compute='_compute_user_and_stage_ids', store=True,
        readonly=False, tracking=True,
        domain=lambda self: [('all_group_ids', 'in', self.env.ref('im_helpdesk.group_helpdesk_user').id)],
        falsy_value_label=_lt("Unassigned"))
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True, index=True)
    partner_ticket_ids = fields.Many2many('helpdesk.ticket', compute='_compute_partner_ticket_count', string="Partner Tickets")
    partner_ticket_count = fields.Integer('Number of other tickets from the same partner', compute='_compute_partner_ticket_count')
    partner_open_ticket_count = fields.Integer('Number of other open tickets from the same partner', compute='_compute_partner_ticket_count')
    partner_name = fields.Char(string='Customer Name', compute='_compute_partner_name', store=True, readonly=False)
    partner_email = fields.Char(string='Customer Email', compute='_compute_partner_email', inverse="_inverse_partner_email", store=True, readonly=False)
    partner_phone = fields.Char(string='Customer Phone', compute='_compute_partner_phone', inverse="_inverse_partner_phone", store=True, readonly=False)
    commercial_partner_id = fields.Many2one(related="partner_id.commercial_partner_id")
    closed_by_partner = fields.Boolean('Closed by Partner', readonly=True)
    priority = fields.Selection(TICKET_PRIORITY, string='Priority', default='0', tracking=True)
    stage_id = fields.Many2one(
        'helpdesk.stage', string='Stage', compute='_compute_user_and_stage_ids', store=True,
        readonly=False, ondelete='restrict', tracking=1, group_expand='_read_group_stage_ids',
        copy=False, index=True, domain="[('team_ids', '=', team_id)]")
    stage_id_color = fields.Integer(string='Stage Color', related="stage_id.color", export_string_translation=False)
    fold = fields.Boolean(related="stage_id.fold", export_string_translation=False)
    date_last_stage_update = fields.Datetime("Last Stage Update", copy=False, readonly=True)
    ticket_ref = fields.Char(string='Ticket IDs Sequence', copy=False, readonly=True, index=True)
    assign_date = fields.Datetime("First assignment date")
    assign_hours = fields.Float("Time to first assignment (hours)", compute='_compute_assign_hours', store=True, aggregator="avg")
    close_date = fields.Datetime("Close date", copy=False)
    close_hours = fields.Float("Time to close (hours)", compute='_compute_close_hours', store=True, aggregator="avg")
    open_hours = fields.Integer("Open Time (hours)", compute='_compute_open_hours', search='_search_open_hours', aggregator="avg")
    # SLA
    sla_ids = fields.Many2many('helpdesk.sla', 'helpdesk_sla_status', 'ticket_id', 'sla_id', string="SLAs", copy=False)
    sla_status_ids = fields.One2many('helpdesk.sla.status', 'ticket_id', string="SLA Status")
    sla_reached_late = fields.Boolean("Has SLA reached late", compute='_compute_sla_reached_late', compute_sudo=True, store=True)
    sla_reached = fields.Boolean("Has SLA reached", compute='_compute_sla_reached', compute_sudo=True, store=True)
    sla_deadline = fields.Datetime("SLA Deadline", compute='_compute_sla_deadline', compute_sudo=True, store=True, falsy_value_label=_lt("Deadline reached"))
    sla_deadline_hours = fields.Float("Working Hours until SLA Deadline", compute='_compute_sla_deadline', compute_sudo=True, store=True, aggregator="avg")
    sla_fail = fields.Boolean("Failed SLA Policy", compute='_compute_sla_fail', search='_search_sla_fail')
    sla_success = fields.Boolean("Success SLA Policy", compute='_compute_sla_success', search='_search_sla_success')
    use_rating = fields.Boolean(related='team_id.use_rating', export_string_translation=False)
    portal_access_link = fields.Char('Portal Link', copy=False, readonly=True)

    is_partner_email_update = fields.Boolean(compute='_compute_is_partner_email_update', export_string_translation=False)
    is_partner_phone_update = fields.Boolean(compute='_compute_is_partner_phone_update', export_string_translation=False)
    website_message_ids = fields.One2many(domain=lambda self: [('model', '=', self._name), ('message_type', 'in', ['email', 'comment', 'email_outgoing', 'auto_comment'])], export_string_translation=False)

    @api.depends('stage_id', 'kanban_state')
    def _compute_kanban_state_label(self):
        """Thiết lập label kanban hiển thị theo legend của stage và state."""
        for ticket in self:
            if ticket.kanban_state == 'normal':
                ticket.kanban_state_label = ticket.legend_normal
            elif ticket.kanban_state == 'blocked':
                ticket.kanban_state_label = ticket.legend_blocked
            else:
                ticket.kanban_state_label = ticket.legend_done

    @api.depends('team_id')
    def _compute_domain_user_ids(self):
        """Tính danh sách người có thể được phân công theo visibility và member của team."""
        user_ids = self.env.ref('im_helpdesk.group_helpdesk_user').all_user_ids.ids
        for ticket in self:
            ticket_user_ids = []
            ticket_sudo = ticket.sudo()
            if ticket_sudo.team_id and ticket_sudo.team_id.privacy_visibility == 'invited_internal':
                ticket_user_ids = ticket_sudo.team_id.message_partner_ids.user_ids.ids
            ticket.domain_user_ids = [Command.set(user_ids + ticket_user_ids)]

    def _compute_access_url(self):
        """Thiết lập URL portal được portal.mixin sử dụng."""
        super()._compute_access_url()
        for ticket in self:
            ticket.access_url = '/my/ticket/%s' % ticket.id

    @api.depends('sla_status_ids.deadline', 'sla_status_ids.reached_datetime')
    def _compute_sla_reached_late(self):
        """Đánh dấu ticket có SLA đạt trễ hoặc hiện đang quá hạn."""
        mapping = {}
        if self.ids:
            self.env.cr.execute("""
                SELECT ticket_id, COUNT(id) AS reached_late_count
                FROM helpdesk_sla_status
                WHERE ticket_id IN %s AND (deadline < reached_datetime OR (deadline < %s AND reached_datetime IS NULL))
                GROUP BY ticket_id
            """, (tuple(self.ids), fields.Datetime.now()))
            mapping = dict(self.env.cr.fetchall())
        for ticket in self:
            ticket.sla_reached_late = mapping.get(ticket.id, 0) > 0

    @api.depends('sla_status_ids.deadline', 'sla_status_ids.reached_datetime')
    def _compute_sla_reached(self):
        """Đánh dấu ticket có ít nhất một SLA hiện đã đạt đúng hạn."""
        sla_status_read_group = self.env['helpdesk.sla.status']._read_group(
            [('exceeded_hours', '<', 0), ('ticket_id', 'in', self.ids)],
            ['ticket_id'],
        )
        sla_status_ids_per_ticket = {ticket.id for [ticket] in sla_status_read_group}
        for ticket in self:
            ticket.sla_reached = ticket.id in sla_status_ids_per_ticket

    @api.depends('sla_status_ids.deadline', 'sla_status_ids.reached_datetime')
    def _compute_sla_deadline(self):
        """Lưu deadline SLA gần nhất chưa đạt và số giờ làm việc còn lại."""
        now = fields.Datetime.now()
        for ticket in self:
            if not ticket.team_id:
                continue
            min_deadline = False
            for status in ticket.sla_status_ids:
                if status.reached_datetime or not status.deadline:
                    continue
                if not min_deadline or status.deadline < min_deadline:
                    min_deadline = status.deadline
            ticket.update({
                'sla_deadline': min_deadline,
                'sla_deadline_hours': ticket.team_id.resource_calendar_id.get_work_duration_data\
                    (now, min_deadline, compute_leaves=True)['hours'] if min_deadline else 0.0,
            })

    @api.depends('sla_deadline', 'sla_reached_late')
    def _compute_sla_fail(self):
        """Tính ticket có đang fail bất kỳ SLA policy nào hay không."""
        now = fields.Datetime.now()
        for ticket in self:
            if ticket.sla_deadline:
                ticket.sla_fail = (ticket.sla_deadline < now) or ticket.sla_reached_late
            else:
                ticket.sla_fail = ticket.sla_reached_late

    @api.depends('partner_email', 'partner_id')
    def _compute_is_partner_email_update(self):
        """Cho biết email trên ticket có khác email của partner hay không."""
        for ticket in self:
            ticket.is_partner_email_update = ticket._get_partner_email_update()

    @api.depends('partner_phone', 'partner_id')
    def _compute_is_partner_phone_update(self):
        """Cho biết số điện thoại trên ticket có khác số của partner hay không."""
        for ticket in self:
            ticket.is_partner_phone_update = ticket._get_partner_phone_update()

    @api.model
    def _search_sla_fail(self, operator, value):
        """Chuyển tìm kiếm SLA failure ảo thành domain trên trường đã lưu."""
        if operator != 'in':
            return NotImplemented
        datetime_now = fields.Datetime.now()
        return ['|', ('sla_reached_late', '=', True), ('sla_deadline', '<', datetime_now)]

    @api.depends('sla_deadline')
    def _compute_sla_success(self):
        """Tính deadline SLA gần nhất có còn ở tương lai hay không."""
        now = fields.Datetime.now()
        for ticket in self:
            ticket.sla_success = (ticket.sla_deadline and ticket.sla_deadline > now)

    @api.model
    def _search_sla_success(self, operator, value):
        """Chuyển tìm kiếm SLA success ảo thành domain theo deadline."""
        if operator != 'in':
            return NotImplemented
        datetime_now = fields.Datetime.now()
        return [('sla_deadline', '>', datetime_now)]

    @api.depends('team_id')
    def _compute_user_and_stage_ids(self):
        """Gán mặc định người phụ trách và stage còn thiếu mỗi khi team thay đổi."""
        for ticket in self.filtered(lambda ticket: ticket.team_id):
            if not ticket.user_id:
                ticket.user_id = ticket.team_id._determine_user_to_assign({ticket.team_id: 1})[ticket.team_id.id][0]
            if not ticket.stage_id or ticket.stage_id not in ticket.team_id.stage_ids:
                ticket.stage_id = ticket.team_id._determine_stage()[ticket.team_id.id]

    @api.depends('partner_id')
    def _compute_partner_name(self):
        """Đồng bộ tên partner sang trường tên khách hàng đã lưu trên ticket."""
        for ticket in self:
            if ticket.partner_id:
                ticket.partner_name = ticket.partner_id.name

    @api.depends('partner_id.email')
    def _compute_partner_email(self):
        """Đồng bộ email partner sang trường email đã lưu trên ticket."""
        for ticket in self:
            if ticket.partner_id:
                ticket.partner_email = ticket.partner_id.email

    def _inverse_partner_email(self):
        """Ghi email ticket đã đổi ngược lại partner được liên kết."""
        for ticket in self:
            if ticket._get_partner_email_update():
                ticket.partner_id.email = ticket.partner_email

    @api.depends('partner_id.phone')
    def _compute_partner_phone(self):
        """Đồng bộ số điện thoại partner sang trường điện thoại đã lưu trên ticket."""
        for ticket in self:
            if ticket.partner_id:
                ticket.partner_phone = ticket.partner_id.phone

    def _inverse_partner_phone(self):
        """Ghi số điện thoại ticket đã đổi ngược lại partner được liên kết."""
        for ticket in self:
            if (ticket._get_partner_phone_update() or not ticket.partner_id.phone) and ticket.partner_phone:
                ticket = ticket.sudo()
                ticket.partner_id.phone = ticket.partner_phone

    @api.depends('partner_id', 'partner_email', 'partner_phone')
    def _compute_partner_ticket_count(self):
        """Tính các ticket liên quan của cùng commercial partner."""
        for ticket in self:
            partner_tickets = self.search_fetch([("partner_id", "child_of", ticket.partner_id.commercial_partner_id.id)], ['fold']) if ticket.partner_id else ticket
            ticket.partner_ticket_ids = partner_tickets
            partner_tickets = partner_tickets - ticket._origin
            ticket.partner_ticket_count = len(partner_tickets) if partner_tickets else 0
            open_ticket = partner_tickets.filtered(lambda ticket: not ticket.fold)
            ticket.partner_open_ticket_count = len(open_ticket)

    @api.depends('assign_date')
    def _compute_assign_hours(self):
        """Tính giờ làm việc từ lúc tạo ticket tới lần phân công đầu tiên."""
        for ticket in self:
            create_date = fields.Datetime.from_string(ticket.create_date)
            if create_date and ticket.assign_date and ticket.team_id.resource_calendar_id:
                duration_data = ticket.team_id.resource_calendar_id.get_work_duration_data(create_date, fields.Datetime.from_string(ticket.assign_date), compute_leaves=True)
                ticket.assign_hours = duration_data['hours']
            else:
                ticket.assign_hours = False

    @api.depends('create_date', 'close_date')
    def _compute_close_hours(self):
        """Tính giờ làm việc từ lúc tạo ticket tới ngày đóng."""
        for ticket in self:
            create_date = fields.Datetime.from_string(ticket.create_date)
            if create_date and ticket.close_date and ticket.team_id:
                duration_data = ticket.team_id.resource_calendar_id.get_work_duration_data(create_date, fields.Datetime.from_string(ticket.close_date), compute_leaves=True)
                ticket.close_hours = duration_data['hours']
            else:
                ticket.close_hours = False

    @api.depends('close_hours')
    def _compute_open_hours(self):
        """Tính số giờ thực tế đã trôi qua khi ticket còn mở."""
        for ticket in self:
            if ticket.create_date:
                if ticket.close_date:
                    time_difference = ticket.close_date - fields.Datetime.from_string(ticket.create_date)
                else:
                    time_difference = fields.Datetime.now() - fields.Datetime.from_string(ticket.create_date)
                ticket.open_hours = (time_difference.seconds) / 3600 + time_difference.days * 24
            else:
                ticket.open_hours = 0

    @api.model
    def _search_open_hours(self, operator, value):
        """Tìm kiếm giá trị open-hour cho cả ticket đang mở và đã đóng."""
        if operator == 'in':
            return Domain.OR(self._search_open_hours('=', v) for v in value)
        if operator == 'not in':
            return Domain.AND(self._search_open_hours('!=', v) for v in value)

        dt = fields.Datetime.now() - relativedelta(hours=value)
        domain_closed = Domain('close_hours', operator, value)
        if operator in ['<', '<=', '>', '>=']:
            domain_unclosed = ~Domain('create_date', operator, dt)
        elif operator in ['=', '!=']:
            dt = dt.replace(minute=0, second=0, microsecond=0)
            domain_unclosed = (
                Domain('create_date', '>=', dt)
                & Domain('create_date', '<', dt + relativedelta(hours=1))
            )
            if operator == '!=':
                domain_unclosed = ~domain_unclosed
        else:
            return NotImplemented
        return (
            (Domain('close_date', '=', False) & domain_unclosed)
            | (Domain('close_date', '!=', False) & domain_closed)
        )

    def _get_partner_email_update(self):
        """Trả về việc email ticket có nên cập nhật vào partner hay không."""
        self.ensure_one()
        if self.partner_id.email and self.partner_email and self.partner_email != self.partner_id.email:
            ticket_email_normalized = tools.email_normalize(self.partner_email) or self.partner_email or False
            partner_email_normalized = tools.email_normalize(self.partner_id.email) or self.partner_id.email or False
            return ticket_email_normalized != partner_email_normalized
        return False

    def _get_partner_phone_update(self):
        """Trả về việc số điện thoại ticket có nên cập nhật vào partner hay không."""
        self.ensure_one()
        if self.partner_id.phone and self.partner_phone and self.partner_phone != self.partner_id.phone:
            ticket_phone_formatted = self.partner_phone or False
            partner_phone_formatted = self.partner_id.phone or False
            return ticket_phone_formatted != partner_phone_formatted
        return False

    def action_customer_preview(self):
        """Mở ticket theo đúng giao diện khách hàng sẽ thấy trên portal."""
        self.ensure_one()
        if self.team_privacy_visibility != 'portal' or not self.partner_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'danger',
                    'message': _('No preview available. The ticket belongs to a non-public team, or there is no customer.'),
                }
            }
        self._portal_ensure_token()
        return {
            'type': 'ir.actions.act_url',
            'url': self.get_portal_url(),
            'target': 'new',
        }

    def action_generate_portal_link(self):
        """Sinh và lưu link truy cập portal có thể chia sẻ cho ticket."""
        self.ensure_one()
        if self.team_privacy_visibility != 'portal' or not self.partner_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'danger',
                    'message': _('No preview available. The ticket belongs to a non-public team, or there is no customer.'),
                }
            }
        self.portal_access_link = self.get_base_url() + self.get_portal_url()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Portal link generated. Copy it from the Portal Link field.'),
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    # ------------------------------------------------------------
    # Ghi đè ORM
    # ------------------------------------------------------------

    @api.depends('ticket_ref', 'partner_name')
    @api.depends_context('with_partner')
    def _compute_display_name(self):
        """Hiển thị subject, mã sequence và tùy chọn kèm tên khách hàng."""
        display_partner_name = self.env.context.get('with_partner', False)
        ticket_with_name = self.filtered('name')
        for ticket in ticket_with_name:
            name = ticket.name
            if ticket.ticket_ref:
                name += f' (#{ticket.ticket_ref})'
            if display_partner_name and ticket.partner_name:
                name += f' - {ticket.partner_name}'
            ticket.display_name = name
        return super(HelpdeskTicket, self - ticket_with_name)._compute_display_name()

    @api.model
    def get_empty_list_help(self, help_message):
        """Tùy chỉnh nội dung helper khi danh sách ticket theo team đang trống."""
        self = self.with_context(
            empty_list_help_id=self.env.context.get('default_team_id'),
            empty_list_help_model='helpdesk.team',
            empty_list_help_document_name=_("tickets"),
        )
        return super().get_empty_list_help(help_message)

    def create_action(self, action_ref, title, search_view_ref):
        """Tạo dictionary action đã clean, có thể gắn title/search view tùy chọn."""
        action = self.env["ir.actions.actions"]._for_xml_id(action_ref)
        action = clean_action(action, self.env)
        if title:
            action['display_name'] = title
        if search_view_ref:
            action['search_view_id'] = self.env.ref(search_view_ref).read()[0]
        if 'views' not in action:
            action['views'] = [(False, view) for view in action['view_mode'].split(",")]
        return action

    @api.model
    def _get_tag_ids_from_vals(self, vals):
        """Lấy tập tag ID cuối cùng từ command values của create/write."""
        return set(self._fields['tag_ids'].convert_to_cache(vals.get('tag_ids') or [], self))

    @api.model
    def _get_auto_tagging_text(self, vals):
        """Tạo text đã chuẩn hóa để match keyword tự động gắn tag."""
        text_parts = [vals.get('name') or '']
        if vals.get('description'):
            text_parts.append(vals['description'])
        return self._normalize_classification_text(' '.join(text_parts))

    @api.model
    def _normalize_classification_text(self, text):
        """Chuẩn hóa text ticket/keyword để so khớp ổn định cho tiếng Việt."""
        text = html2plaintext(text or '')
        text = text.casefold().replace('đ', 'd')
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(char for char in text if not unicodedata.combining(char))
        text = re.sub(r'[^0-9a-z]+', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()

    @api.model
    def _classification_keyword_matches(self, content, keyword):
        """Match keyword theo biên token để tránh dính substring vô tình."""
        if not content or not keyword:
            return False
        return f' {keyword} ' in f' {content} '

    @api.model
    def _score_classification_keywords(self, content, keyword_entries):
        """Tính tổng điểm keyword khớp trong nội dung ticket đã chuẩn hóa."""
        score = 0
        seen_keywords = set()
        for keyword, weight in keyword_entries:
            normalized_keyword = self._normalize_classification_text(keyword)
            if not normalized_keyword or normalized_keyword in seen_keywords:
                continue
            seen_keywords.add(normalized_keyword)
            if self._classification_keyword_matches(content, normalized_keyword):
                score += weight
        return score

    @api.model
    def _apply_auto_tags_to_vals(self, vals_list):
        """Thêm tag vào values đầu vào khi đạt điểm keyword đã cấu hình."""
        keyword_tags = self.env['helpdesk.tag'].sudo().search([('auto_apply_keywords', '!=', False)])
        if not keyword_tags:
            return

        tag_keyword_entries = {
            tag.id: tag._get_auto_apply_keyword_entries()
            for tag in keyword_tags
        }
        for vals in vals_list:
            content = self._get_auto_tagging_text(vals)
            if not content:
                continue

            tag_ids = self._get_tag_ids_from_vals(vals)
            for tag in keyword_tags:
                score = self._score_classification_keywords(content, tag_keyword_entries[tag.id])
                if score >= (tag.auto_apply_min_score or 1):
                    tag_ids.add(tag.id)

            if tag_ids:
                vals['tag_ids'] = [Command.set(sorted(tag_ids))]

    @api.model
    def _get_route_scores_by_tag(self, tag_ids):
        """Trả về điểm route theo team dựa trên tag và trọng số rule."""
        if not tag_ids:
            return {}, {}

        assignments = self.env['helpdesk.tag.assignment'].sudo().search([
            ('tag_id', 'in', list(tag_ids)),
            ('team_id', '!=', False),
            ('team_id.active', '=', True),
            ('team_id.company_id', 'in', self.env.companies.ids),
        ])
        team_scores_by_tag_id = defaultdict(lambda: defaultdict(int))
        team_by_id = {}
        for assignment in assignments:
            team_scores_by_tag_id[assignment.tag_id.id][assignment.team_id.id] += assignment.route_weight or 1
            team_by_id[assignment.team_id.id] = assignment.team_id
        return team_scores_by_tag_id, team_by_id

    @api.model
    def _route_vals_by_tags(self, vals_list):
        """Chuyển values ticket đầu vào về team phù hợp nhất dựa trên điểm tag.

        Mỗi tag assignment khớp cộng ``route_weight`` cho team tương ứng. Team có
        điểm cao nhất thắng; nếu team hiện tại cũng đạt điểm cao nhất thì giữ
        nguyên để tránh ghi đè lựa chọn đã có.
        """
        tag_ids_per_vals = [self._get_tag_ids_from_vals(vals) for vals in vals_list]
        all_tag_ids = set().union(*tag_ids_per_vals) if tag_ids_per_vals else set()
        team_scores_by_tag_id, team_by_id = self._get_route_scores_by_tag(all_tag_ids)
        if not team_scores_by_tag_id:
            return

        for vals, tag_ids in zip(vals_list, tag_ids_per_vals):
            team_scores = defaultdict(int)
            for tag_id in tag_ids:
                for team_id, score in team_scores_by_tag_id.get(tag_id, {}).items():
                    team_scores[team_id] += score
            if not team_scores:
                continue

            max_score = max(team_scores.values())
            current_team_id = vals.get('team_id')
            if current_team_id and team_scores.get(current_team_id) == max_score:
                continue

            routed_team = min(
                (team_by_id[team_id] for team_id, score in team_scores.items() if score == max_score),
                key=lambda team: (team.sequence, team.id),
            )
            vals['team_id'] = routed_team.id
            if vals.get('stage_id') and vals['stage_id'] not in routed_team.stage_ids.ids:
                vals.pop('stage_id')

    @api.model
    def _prepare_auto_tag_route_vals(self, vals_list):
        """Áp dụng tự động gắn tag và điều hướng team, trừ khi context tắt luồng này."""
        if self.env.context.get('skip_helpdesk_auto_tag_route'):
            return
        self._apply_auto_tags_to_vals(vals_list)
        self._route_vals_by_tags(vals_list)

    def _assign_auto_routed_ticket(self, team, tag_ids):
        """Chọn người phụ trách sau khi điều hướng theo nội dung làm ticket đổi team."""
        self.ensure_one()
        if not team.auto_assignment:
            return False

        if team.assign_method == 'tags':
            assignment_vals = {}
            self._assign_vals_by_tags([(team.id, tag_ids, assignment_vals)])
            return assignment_vals.get('user_id', False)

        return team._determine_user_to_assign({team: 1}).get(team.id, [False])[0]

    def _auto_tag_route_assign_from_content(self):
        """Chạy lại tự gắn tag, điều hướng team và phân công từ nội dung đã lưu của ticket.

        Luồng này chủ yếu dùng sau khi body email trở thành mô tả ticket, vì nội
        dung cuối cùng để tìm kiếm có thể chưa tồn tại lúc tạo ban đầu. Context
        guard giúp tránh write đệ quy kích hoạt lại cùng luồng.
        """
        if self.env.context.get('skip_helpdesk_auto_tag_route'):
            return

        for ticket in self.filtered(lambda ticket: not ticket.fold):
            vals = {
                'name': ticket.name,
                'description': ticket.description,
                'team_id': ticket.team_id.id,
                'stage_id': ticket.stage_id.id,
                'tag_ids': [Command.set(ticket.tag_ids.ids)],
            }
            ticket._prepare_auto_tag_route_vals([vals])

            tag_ids = ticket._get_tag_ids_from_vals(vals)
            routed_team = self.env['helpdesk.team'].browse(vals.get('team_id'))
            write_vals = {}
            if tag_ids != set(ticket.tag_ids.ids):
                write_vals['tag_ids'] = [Command.set(sorted(tag_ids))]

            team_changed = routed_team and routed_team != ticket.team_id
            if team_changed:
                write_vals['team_id'] = routed_team.id
                if ticket.stage_id not in routed_team.stage_ids:
                    write_vals['stage_id'] = routed_team._determine_stage()[routed_team.id].id

            if routed_team and (team_changed or not ticket.user_id):
                user_id = ticket._assign_auto_routed_ticket(routed_team, tag_ids)
                if user_id:
                    write_vals['user_id'] = user_id
                elif team_changed and ticket.user_id not in routed_team.member_ids:
                    write_vals['user_id'] = False

            if write_vals:
                ticket.with_context(skip_helpdesk_auto_tag_route=True).sudo().write(write_vals)

    @api.model
    def _assign_vals_by_tags(self, vals_list):
        """Điền ``user_id`` vào dict values bằng rule phân công theo tag.

        ``vals_list`` chứa các tuple gồm team ID, tag IDs và một dict values có
        thể sửa. User khớp rule tag mạnh nhất được ưu tiên, sau đó xét lịch làm
        việc sớm nhất, số ticket mở và ID để kết quả ổn định.
        """
        if not vals_list:
            return

        vals_list = [(team_id, set(tag_ids), vals) for team_id, tag_ids, vals in vals_list]
        tagged_vals_list = [(team_id, tag_ids, vals) for team_id, tag_ids, vals in vals_list if tag_ids]
        assignments = self.env['helpdesk.tag.assignment']
        if tagged_vals_list:
            domain = Domain.OR(
                [('team_id', '=', team_id), ('tag_id', 'in', list(tag_ids))]
                for team_id, tag_ids, _vals in tagged_vals_list
            )
            assignments = assignments.sudo().search(domain)

        teams = self.env['helpdesk.team'].browse({team_id for team_id, _tag_ids, _vals in vals_list})
        team_by_id = {team.id: team for team in teams}
        user_scores_per_team_and_tag = defaultdict(lambda: defaultdict(int))
        all_possible_users_ids = set()
        for assignment in assignments:
            team = assignment.team_id
            team_member_ids = set(team.member_ids.ids)
            candidate_user_ids = set(
                assignment.user_ids.filtered(lambda user: user.active and not user.share).ids
            ) & team_member_ids
            for user_id in candidate_user_ids:
                user_scores_per_team_and_tag[(team.id, assignment.tag_id.id)][user_id] += assignment.route_weight or 1
            all_possible_users_ids.update(candidate_user_ids)

        all_possible_users = self.env['res.users'].browse(all_possible_users_ids)
        users_per_working_days = all_possible_users._get_working_users_per_first_working_day()
        working_rank_by_user_id = {
            user_id: rank
            for rank, user_ids in enumerate(users_per_working_days)
            for user_id in user_ids
        }

        tickets_per_user_per_team = defaultdict(dict)
        all_team_ids = set(team_by_id)
        for team_id in all_team_ids:
            for user_id in all_possible_users_ids:
                tickets_per_user_per_team[team_id][user_id] = 0
        ticket_count_data = self.env['helpdesk.ticket']._read_group(
            [('stage_id.fold', '=', False), ('user_id', 'in', all_possible_users.ids), ('team_id', 'in', list(all_team_ids))],
            ['user_id', 'team_id'],
            ['__count'],
        )
        for user, team, open_tickets in ticket_count_data:
            tickets_per_user_per_team[team.id][user.id] = open_tickets

        fallback_ticket_amount_per_team = defaultdict(int)
        fallback_vals_per_team_id = defaultdict(list)
        for team_id, tag_ids, vals in vals_list:
            score_per_user_id = defaultdict(int)
            for tag_id in tag_ids:
                for user_id, score in user_scores_per_team_and_tag.get((team_id, tag_id), {}).items():
                    score_per_user_id[user_id] += score

            possible_user_ids = [user_id for user_id in score_per_user_id if user_id in working_rank_by_user_id]
            if possible_user_ids:
                chosen_user_id = min(
                    possible_user_ids,
                    key=lambda user_id: (
                        -score_per_user_id[user_id],
                        working_rank_by_user_id[user_id],
                        tickets_per_user_per_team[team_id].get(user_id, 0),
                        user_id,
                    ),
                )
                vals['user_id'] = chosen_user_id
                tickets_per_user_per_team[team_id][chosen_user_id] += 1
            else:
                team = team_by_id.get(team_id)
                if team:
                    fallback_ticket_amount_per_team[team] += 1
                    fallback_vals_per_team_id[team_id].append(vals)

        fallback_assignees_per_team_id = self.env['helpdesk.team']._determine_user_to_assign(
            fallback_ticket_amount_per_team,
            force_method='balanced',
        )
        for team_id, vals_dicts in fallback_vals_per_team_id.items():
            assignee_ids = fallback_assignees_per_team_id.get(team_id, [])
            for vals, user_id in zip(vals_dicts, assignee_ids):
                if user_id:
                    vals['user_id'] = user_id

    @api.model_create_multi
    def create(self, vals_list):
        """Tạo ticket kèm auto-tag, điều hướng team, phân công và thiết lập SLA.

        Hàm chuẩn bị mặc định team/stage/user, tạo partner còn thiếu từ địa chỉ
        email, subscribe khách hàng và follower CC nội bộ, sinh portal token và
        áp dụng trạng thái SLA ban đầu.
        """
        now = fields.Datetime.now()
        self._prepare_auto_tag_route_vals(vals_list)

        team_ids = { vals['team_id'] for vals in vals_list if vals.get('team_id') }
        tickets_to_assign_by_tags = []
        teams = self.env['helpdesk.team'].browse(team_ids)

        default_stage_per_team_id = teams._determine_stage()

        team_per_team_id = {team.id: team for team in teams}
        ticket_amount_per_team = defaultdict(int)
        for vals in vals_list:
            if not (team_id := vals.get('team_id')):
                continue
            stage = self.env['helpdesk.stage'].browse(vals['stage_id']) if 'stage_id' in vals else default_stage_per_team_id[team_id]
            team = team_per_team_id[team_id]
            if stage.fold or vals.get('user_id') or not team.auto_assignment:
                continue
            if team.assign_method == 'tags':
                tag_ids = self._fields['tag_ids'].convert_to_cache(vals.get('tag_ids') or [], self)
                tickets_to_assign_by_tags.append((team.id, tag_ids, vals))
            else:
                ticket_amount_per_team[team] += 1

        self._assign_vals_by_tags(tickets_to_assign_by_tags)
        assignees_per_team_id = self.env['helpdesk.team']._determine_user_to_assign(ticket_amount_per_team)

        for vals in vals_list:
            partner_id = vals.get('partner_id', False)
            partner_name = vals.get('partner_name', False)
            partner_email = vals.get('partner_email', False)
            if partner_email and not partner_id:
                company_id = self.env['helpdesk.team'].browse(vals['team_id']).company_id.id if vals.get('team_id') else False
                suggested_name = tools.parse_contact_from_email(partner_name)[0] or tools.parse_contact_from_email(partner_email)[0]
                vals['partner_id'] = self.env['mail.thread']._partner_find_from_emails_single(
                    [partner_email], additional_values={tools.mail.email_normalize(partner_email) or partner_email: {'name': suggested_name, 'company_id': company_id}},
                    filter_found=lambda partner: not partner.company_id or partner.company_id.id == company_id,
                ).id

        partners = self.env['res.partner'].browse([vals['partner_id'] for vals in vals_list if 'partner_id' in vals and vals.get('partner_id') and 'partner_email' not in vals])
        partner_email_map = {partner.id: partner.email for partner in partners}
        partner_name_map = {partner.id: partner.name for partner in partners}
        company_per_team_id = {t.id: t.company_id for t in teams}
        for vals in vals_list:
            company = company_per_team_id.get(vals.get('team_id', False))
            vals['ticket_ref'] = self.env['ir.sequence'].with_company(company).sudo().next_by_code('helpdesk.ticket')
            if team_id := vals.get('team_id'):
                if 'stage_id' not in vals:
                    vals['stage_id'] = default_stage_per_team_id[team_id].id
                if self.env['helpdesk.stage'].browse(vals['stage_id']).fold:
                    vals['close_date'] = now
                if 'user_id' not in vals and team_id in assignees_per_team_id:
                    vals['user_id'] = assignees_per_team_id[team_id].pop()
                if vals.get('user_id'):
                    vals['assign_date'] = fields.Datetime.now()
                    vals['assign_hours'] = 0

            if vals.get('partner_id') in partner_email_map:
                vals['partner_email'] = partner_email_map.get(vals['partner_id'])
            if vals.get('partner_id') in partner_name_map:
                vals['partner_name'] = partner_name_map.get(vals['partner_id'])

            if vals.get('stage_id'):
                vals['date_last_stage_update'] = now

        tickets = super().create(vals_list)

        all_partner_emails = []
        for ticket in tickets:
            all_partner_emails += tools.email_normalize_all(ticket.email_cc)
        partners = self.env['res.partner'].search([('email', 'in', all_partner_emails)])
        partner_per_email = {
            partner.email: partner
            for partner in partners
            if not all(u.share for u in partner.user_ids)
        }

        for ticket in tickets:
            partner_ids = []
            if ticket.partner_id:
                partner_ids = ticket.partner_id.ids
            if ticket.email_cc:
                partners_with_internal_user = self.env['res.partner']
                for email in tools.email_normalize_all(ticket.email_cc):
                    new_partner = partner_per_email.get(email)
                    if new_partner:
                        partners_with_internal_user |= new_partner
                if partners_with_internal_user:
                    ticket._send_email_notify_to_cc(partners_with_internal_user)
                    partner_ids += partners_with_internal_user.ids
            if partner_ids:
                ticket.message_subscribe(partner_ids)

            ticket._portal_ensure_token()

        tickets.sudo()._sla_apply()

        return tickets

    def write(self, vals):
        """Cập nhật ticket đồng thời giữ đúng ngày vòng đời và trạng thái SLA.

        Ngày phân công, ngày đóng, ngày cập nhật stage gần nhất, tính lại SLA,
        subscribe follower khách hàng và phân công theo tag đều được xử lý ở đây
        để thao tác thủ công và write tự động có cùng hành vi.
        """
        assigned_tickets = closed_tickets = self.browse()
        if vals.get('user_id'):
            assigned_tickets = self.filtered(lambda ticket: not ticket.assign_date)

        if vals.get('stage_id'):
            if self.env['helpdesk.stage'].browse(vals.get('stage_id')).fold:
                closed_tickets = self.filtered(lambda ticket: not ticket.close_date)
            else:
                vals['closed_by_partner'] = False
                vals['close_date'] = False

        now = fields.Datetime.now()

        if 'stage_id' in vals:
            vals['date_last_stage_update'] = now
            if 'kanban_state' not in vals:
                vals['kanban_state'] = 'normal'

        if 'kanban_state' in vals:
            vals['date_last_stage_update'] = now

        old_tag_ids_per_ticket_id = {}
        if 'tag_ids' in vals:
            old_tag_ids_per_ticket_id = {t.id: set(t.tag_ids.ids) for t in self}

        res = super(HelpdeskTicket, self - assigned_tickets - closed_tickets).write(vals)
        res &= super(HelpdeskTicket, assigned_tickets - closed_tickets).write(dict(vals, **{
            'assign_date': now,
        }))
        res &= super(HelpdeskTicket, closed_tickets - assigned_tickets).write(dict(vals, **{
            'close_date': now,
        }))
        res &= super(HelpdeskTicket, assigned_tickets & closed_tickets).write(dict(vals, **{
            'assign_date': now,
            'close_date': now,
        }))

        if vals.get('partner_id'):
            self.message_subscribe([vals['partner_id']])

        sla_triggers = self._sla_reset_trigger()
        if any(field_name in sla_triggers for field_name in vals.keys()):
            self.sudo()._sla_apply(keep_reached=True)
        if 'stage_id' in vals:
            self.sudo()._sla_reach(vals['stage_id'])

        if 'stage_id' in vals and self.env['helpdesk.stage'].browse(vals['stage_id']).fold:
            odoobot_partner_id = self.env['ir.model.data']._xmlid_to_res_id('base.partner_root')
            for ticket in self:
                exceeded_hours = ticket.sla_status_ids.mapped('exceeded_hours')
                if exceeded_hours:
                    min_hours = min([hours for hours in exceeded_hours if hours > 0], default=min(exceeded_hours))
                    message = _("This ticket was successfully closed %s hours before its SLA deadline.", round(abs(min_hours))) if min_hours < 0 \
                        else _("This ticket was closed %s hours after its SLA deadline.", round(min_hours))
                    ticket.message_post(body=message, subtype_xmlid="mail.mt_note", author_id=odoobot_partner_id)
        elif old_tag_ids_per_ticket_id:
            unassigned_tickets_to_assign = self.filtered(
                lambda t: not t.user_id
                    and t.team_id.auto_assignment
                    and t.team_id.assign_method == 'tags'
                    and not t.stage_id.fold
            )
            if unassigned_tickets_to_assign:
                vals_list = [
                    (ticket.team_id.id, list(added_tags), {})
                    for ticket in unassigned_tickets_to_assign
                    if (added_tags := set(ticket.tag_ids.ids) - old_tag_ids_per_ticket_id[ticket.id])
                ]
                if vals_list:
                    self._assign_vals_by_tags(vals_list)
                    for ticket, vals_dict in zip(unassigned_tickets_to_assign, list(zip(*vals_list))[2]):
                        if vals_dict:
                            ticket.write(vals_dict)
        return res

    def copy_data(self, default=None):
        """Nhân bản ticket với hậu tố '(copy)' và giá trị assignee mặc định an toàn."""
        vals_list = super().copy_data(default=default)
        has_default_user = default and 'user_id' in default
        active_users = self.env['res.users']
        if not has_default_user:
            active_users = self.user_id.filtered('active')
        for ticket, vals in zip(self, vals_list):
            vals['name'] = self.env._("%s (copy)", ticket.name)
            if not has_default_user and ticket.user_id and ticket.user_id not in active_users:
                vals['user_id'] = False
        return vals_list

    def _unsubscribe_portal_users(self):
        """Gỡ portal user khỏi follower của ticket khi visibility chuyển sang private."""
        self.message_unsubscribe(partner_ids=self.message_partner_ids.filtered('user_ids.share').ids)

    # ------------------------------------------------------------
    # Action và phương thức nghiệp vụ
    # ------------------------------------------------------------

    @api.model
    def _sla_reset_trigger(self):
        """Trả về các field khiến trạng thái SLA cần được tính lại."""
        return ['team_id', 'priority', 'tag_ids', 'partner_id']

    def _sla_apply(self, keep_reached=False):
        """Áp dụng các SLA policy phù hợp cho ticket.

        Các dòng trạng thái hiện có sẽ được thay thế, trừ khi bật ``keep_reached``;
        khi đó các trạng thái SLA đã đạt sẽ được giữ lại để đảm bảo lịch sử đúng.
        """
        sla_per_tickets = self._sla_find()

        sla_status_value_list = []
        for tickets, slas in sla_per_tickets.items():
            sla_status_value_list += tickets._sla_generate_status_values(slas, keep_reached=keep_reached)

        sla_status_to_remove = self.mapped('sla_status_ids')
        if keep_reached:
            sla_status_to_remove = sla_status_to_remove.filtered(lambda status: not status.reached_datetime)

        sla_status_to_remove.unlink()
        return self.env['helpdesk.sla.status'].create(sla_status_value_list)

    @api.model
    def _sla_find_false_domain(self):
        """Trả về nhánh domain SLA cho policy không giới hạn theo khách hàng."""
        return [('partner_ids', '=', False)]

    def _sla_find_extra_domain(self):
        """Trả về nhánh domain SLA theo khách hàng của ticket này."""
        self.ensure_one()
        return [
            '|',
                ('partner_ids', 'parent_of', self.partner_id.ids),
                ('partner_ids', 'child_of', self.partner_id.ids),
        ]

    def _sla_find(self):
        """Nhóm ticket theo các field kích hoạt SLA và tìm policy phù hợp.

        Việc nhóm giúp tránh chạy một lần search SLA cho từng ticket khi nhiều
        ticket có chung team, priority, tag và tiêu chí khách hàng.
        """
        tickets_map = {}
        sla_domain_map = {}

        def _generate_key(ticket):
            """Tạo key có thể hash từ các field ảnh hưởng tới việc chọn SLA."""
            fields_list = self._sla_reset_trigger()
            key = list()
            for field_name in fields_list:
                if ticket._fields[field_name].type == 'many2one':
                    key.append(ticket[field_name].id)
                else:
                    key.append(ticket[field_name])
            return tuple(key)

        for ticket in self:
            if ticket.team_id.use_sla:
                key = _generate_key(ticket)
                tickets_map.setdefault(key, self.env['helpdesk.ticket'])
                tickets_map[key] |= ticket
                if key not in sla_domain_map:
                    sla_domain_map[key] = Domain.AND([[
                        ('team_id', '=', ticket.team_id.id), ('priority', '=', ticket.priority),
                        ('stage_id.sequence', '>=', ticket.stage_id.sequence),
                    ], Domain.OR([ticket._sla_find_extra_domain(), self._sla_find_false_domain()])])

        result = {}
        for key, tickets in tickets_map.items():
            domain = sla_domain_map[key]
            slas = self.env['helpdesk.sla'].search(domain)
            result[tickets] = slas.filtered(lambda s: not s.tag_ids or (tickets.tag_ids & s.tag_ids))
        return result

    def _sla_generate_status_values(self, slas, keep_reached=False):
        """Chuẩn bị values để tạo record trạng thái SLA cho các ticket này."""
        exclude_slas_per_ticket = {}
        if keep_reached:
            exclude_slas_per_ticket = dict(self.env['helpdesk.sla.status']._read_group(
                domain=[('reached_datetime', '!=', False), ('ticket_id', 'in', self.ids)],
                groupby=['ticket_id'],
                aggregates=['sla_id:recordset'],
            ))
        result = []
        for ticket in self:
            exclude_slas = exclude_slas_per_ticket.get(ticket, self.env['helpdesk.sla'])
            for sla in slas - exclude_slas:
                result.append({
                    'ticket_id': ticket.id,
                    'sla_id': sla.id,
                    'reached_datetime': fields.Datetime.now() if ticket.stage_id == sla.stage_id else False
               })
        return result

    def _sla_reach(self, stage_id):
        """Đánh dấu trạng thái SLA đã đạt khi ticket chuyển tới hoặc vượt qua một stage."""
        stage = self.env['helpdesk.stage'].browse(stage_id)
        stages = self.env['helpdesk.stage'].search([('sequence', '<=', stage.sequence), ('team_ids', 'in', self.mapped('team_id').ids)])
        sla_status = self.env['helpdesk.sla.status'].search([('ticket_id', 'in', self.ids)])
        sla_not_reached = sla_status.filtered(lambda sla: not sla.reached_datetime and sla.sla_stage_id in stages)
        sla_not_reached.write({'reached_datetime': fields.Datetime.now()})
        (sla_status - sla_not_reached).filtered(lambda x: x.sla_stage_id not in stages).write({'reached_datetime': False})

    def action_open_helpdesk_ticket(self):
        """Mở các ticket khác của cùng khách hàng/commercial partner."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("im_helpdesk.helpdesk_ticket_action_main_tree")
        action.update({
            'domain': [('id', '!=', self.id), ('id', 'in', self.partner_ticket_ids.ids)],
            'context': {
                **ast.literal_eval(action.get('context', {})),
                'create': False,
            },
        })
        return action

    def action_open_ratings(self):
        """Mở rating liên kết với ticket này; nếu chỉ có một rating thì mở thẳng form."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('im_helpdesk.rating_rating_action_helpdesk')
        if self.rating_count == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.rating_ids[0].id,
                'views': [(view_id, view_type) for view_id, view_type in action['views'] if view_type == 'form'],
            })
        return action

    # ------------------------------------------------------------
    # API tin nhắn
    # ------------------------------------------------------------

    def _get_customer_information(self):
        """Cung cấp giá trị fallback khách hàng dùng khi mail.thread tìm partner."""
        email_keys_to_values = super()._get_customer_information()
        for ticket in self:
            email_key = tools.email_normalize(ticket.partner_email) or ticket.partner_email
            if not email_key and len(self) > 1:
                continue
            email_keys_to_values.setdefault(email_key, {}).update({
                'company_id': ticket.company_id.id,
                'name': ticket.partner_name or tools.parse_contact_from_email(ticket.partner_email)[0] or ticket.partner_email,
                'phone': ticket.partner_phone,
            })
        return email_keys_to_values

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """Tạo ticket từ một email gửi vào.

        Người gửi trở thành email/tên khách hàng, các recipient và contact CC sẽ
        được subscribe nếu match được partner, và author partner được liên kết
        khi không có partner rõ ràng được truyền vào.
        """
        values = dict(custom_values or {}, partner_email=msg_dict.get('from'), partner_name=msg_dict.get('from'), partner_id=msg_dict.get('author_id'))
        ticket = super(HelpdeskTicket, self.with_context(mail_notify_author=True)).message_new(msg_dict, custom_values=values)
        partner_ids = ticket._partner_find_from_emails_single(tools.email_split((msg_dict.get('to') or '') + ',' + (msg_dict.get('cc') or ''))).ids
        customer_ids = ticket._partner_find_from_emails_single(tools.email_split(values['partner_email'])).ids
        partner_ids += customer_ids
        if customer_ids and not values.get('partner_id'):
            ticket.partner_id = customer_ids[0]
        if partner_ids:
            ticket.message_subscribe(partner_ids)
        return ticket

    def message_update(self, msg_dict, update_vals=None):
        """Subscribe các recipient đã biết khi email gửi vào cập nhật ticket."""
        for ticket in self:
            if partners := ticket._partner_find_from_emails_single(tools.email_split((msg_dict.get('to') or '') + ',' + (msg_dict.get('cc') or '')), no_create=True):
                self.message_subscribe(partners.ids)
        return super().message_update(msg_dict, update_vals=update_vals)

    def _message_compute_subject(self):
        """Dùng subject của ticket làm subject cho email thread."""
        self.ensure_one()
        return self.name

    def _message_post_after_hook(self, message, msg_vals):
        """Đồng bộ dữ liệu partner và mô tả sau khi post message.

        Khi email đầu tiên của khách hàng tạo ticket, body email sẽ trở thành mô
        tả ticket sau khi loại bỏ các chữ ký phổ biến. Nội dung đó sau đó được
        dùng để tự gắn tag, điều hướng team và phân công.
        """
        if not self.partner_email:
            return super()._message_post_after_hook(message, msg_vals)

        if self.partner_id and not self.partner_id.email:
            self.partner_id.email = self.partner_email

        if not self.partner_id:
            email_normalized = tools.email_normalize(self.partner_email)
            new_partner = message.partner_ids.filtered(
                lambda partner: partner.email == self.partner_email or (email_normalized and partner.email_normalized == email_normalized)
            )
            if new_partner:
                if new_partner[0].email_normalized:
                    email_domain = ('partner_email', 'in', [new_partner[0].email, new_partner[0].email_normalized])
                else:
                    email_domain = ('partner_email', '=', new_partner[0].email)
                self.search([
                    ('partner_id', '=', False), email_domain,
                ]).write({'partner_id': new_partner[0].id})
        if (
            not self.description
            and message.subtype_id == self._creation_subtype()
            and msg_vals.get('message_type') == 'email'
            and tools.email_normalize(self.partner_email) == tools.email_normalize(message.email_from)
            and msg_vals.get('body')
        ):
            source_html = msg_vals.get('body')
            doc = html.fromstring(source_html)

            signature_xpath = (
                '//*[@id="Signature"] | '
                '//*[@data-smartmail="gmail_signature"] | '
                '//span[normalize-space(.) = "--"]'
            )

            for element in doc.xpath(signature_xpath):
                element.getparent().remove(element)

            cleaned_html = html.tostring(doc, encoding='unicode').strip()
            self.description = html_sanitize(cleaned_html)
            self.sudo()._auto_tag_route_assign_from_content()

        return super()._message_post_after_hook(message, msg_vals)

    def _send_email_notify_to_cc(self, partners_to_notify):
        """Thông báo cho partner nội bộ trong CC rằng họ đã được subscribe."""
        self.ensure_one()
        template_id = self.env['ir.model.data']._xmlid_to_res_id('im_helpdesk.ticket_invitation_follower', raise_if_not_found=False)
        if not template_id:
            return
        ticket_model_description = self.env['ir.model']._get(self._name).display_name
        values = {
            'object': self,
        }
        for partner in partners_to_notify:
            values['partner_name'] = partner.name
            assignation_msg = self.env['ir.qweb']._render('im_helpdesk.ticket_invitation_follower', values, minimal_qcontext=True)
            self.message_notify(
                subject=_('You have been invited to follow %s', self.display_name),
                body=assignation_msg,
                partner_ids=partner.ids,
                email_layout_xmlid='mail.mail_notification_layout',
                model_description=ticket_model_description,
                mail_auto_delete=True,
            )

    def _track_template(self, changes):
        """Gửi email template của stage khi ticket đi tới stage đó."""
        res = super()._track_template(changes)
        ticket = self[0]
        if 'stage_id' in changes and ticket.stage_id.template_id and ticket.partner_email:
            res['stage_id'] = (ticket.stage_id.template_id, {
                'auto_delete_keep_log': False,
                'subtype_id': self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note'),
                'email_layout_xmlid': 'mail.mail_notification_light'
            }
        )
        return res

    def _creation_subtype(self):
        """Trả về subtype dùng cho message tạo ticket helpdesk mới."""
        return self.env.ref('im_helpdesk.mt_ticket_new')

    def _track_subtype(self, init_values):
        """Trả về subtype chatter cho thay đổi stage ticket được tracking."""
        self.ensure_one()
        if 'stage_id' in init_values:
            return self.env.ref('im_helpdesk.mt_ticket_stage')
        return super()._track_subtype(init_values)

    def _notify_get_reply_to(self, default=None, author_id=False):
        """Dùng alias của team làm địa chỉ reply-to cho email ticket."""
        aliases = self.mapped('team_id').sudo()._notify_get_reply_to(default=default, author_id=author_id)
        res = {ticket.id: aliases.get(ticket.team_id.id) for ticket in self}
        leftover = self.filtered(lambda rec: not rec.team_id)
        if leftover:
            res.update(super(HelpdeskTicket, leftover)._notify_get_reply_to(default=default, author_id=author_id))
        return res

    # ------------------------------------------------------------
    # Rating Mixin
    # ------------------------------------------------------------

    def _rating_apply_get_default_subtype_id(self):
        """Trả về subtype chatter dùng khi khách hàng đánh giá ticket."""
        return self.env['ir.model.data']._xmlid_to_res_id("im_helpdesk.mt_ticket_rated")

    def _rating_get_parent_field_name(self):
        """Cho rating.mixin biết rating sẽ được tổng hợp lên team helpdesk."""
        return 'team_id'
