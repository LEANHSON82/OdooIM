import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class ImCourseAssignment(models.Model):
    """A course assigned to an employee, with a deadline."""
    _name = 'im.course.assignment'
    _description = 'Khoá học được giao'
    _inherit = ['mail.thread']
    _order = 'date_deadline asc, id desc'
    _rec_name = 'channel_id'

    channel_id = fields.Many2one(
        'slide.channel', string='Khoá học', required=True, ondelete='cascade',
        index=True, tracking=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Nhân viên', required=True, ondelete='cascade',
        index=True, tracking=True)
    department_id = fields.Many2one(
        related='employee_id.department_id', string='Phòng ban', store=True)
    manager_id = fields.Many2one(
        related='employee_id.parent_id', string='Quản lý trực tiếp', store=True)
    partner_id = fields.Many2one(
        'res.partner', string='Liên hệ', compute='_compute_partner_id', store=True)

    date_assigned = fields.Date(
        'Ngày giao', required=True, default=fields.Date.context_today, tracking=True)
    date_deadline = fields.Date('Hạn hoàn thành', tracking=True)

    channel_partner_id = fields.Many2one(
        'slide.channel.partner', string='Ghi danh', readonly=True, ondelete='set null')
    completion = fields.Integer(
        'Tiến độ (%)', related='channel_partner_id.completion', store=True, readonly=True)
    member_status = fields.Selection(
        related='channel_partner_id.member_status', store=True, readonly=True)
    is_enrolled = fields.Boolean(
        'Còn ghi danh', related='channel_partner_id.active', store=True, readonly=True)
    certificate_id = fields.Many2one(
        'slide.certificate', string='Chứng chỉ', compute='_compute_certificate_id')

    state = fields.Selection([
        ('not_started', 'Chưa bắt đầu'),
        ('in_progress', 'Đang học'),
        ('overdue', 'Quá hạn'),
        ('done', 'Đã xong'),
        ('removed', 'Bị gỡ khỏi khoá'),
    ], string='Trạng thái', compute='_compute_state', search='_search_state')

    reminder_sent = fields.Boolean('Đã nhắc trước hạn', default=False, copy=False)
    overdue_notified = fields.Boolean('Đã báo quá hạn', default=False, copy=False)

    _unique_assignment = models.Constraint(
        'UNIQUE(channel_id, employee_id)',
        'Mỗi nhân viên chỉ được giao một lần cho mỗi khoá học.',
    )

    @api.depends('employee_id')
    def _compute_partner_id(self):
        for assignment in self:
            employee = assignment.employee_id
            assignment.partner_id = (
                employee.work_contact_id or employee.user_id.partner_id or False)

    @api.depends('channel_id', 'partner_id')
    def _compute_certificate_id(self):
        """Certificate this employee already holds for this course, if any."""
        held = self.env['slide.certificate']._map_by_learner_and_course(
            self.partner_id, self.channel_id)
        for assignment in self:
            assignment.certificate_id = held.get(
                (assignment.partner_id.id, assignment.channel_id.id), False)

    @api.depends('completion', 'member_status', 'date_deadline', 'is_enrolled',
                 'channel_partner_id')
    def _compute_state(self):
        """Derive the state, deliberately without storing it."""
        today = fields.Date.context_today(self)
        for assignment in self:
            if assignment.member_status == 'completed' or assignment.completion >= 100:
                assignment.state = 'done'
            elif assignment.channel_partner_id and not assignment.is_enrolled:
                assignment.state = 'removed'
            elif assignment.date_deadline and assignment.date_deadline < today:
                assignment.state = 'overdue'
            elif assignment.completion > 0:
                assignment.state = 'in_progress'
            else:
                assignment.state = 'not_started'

    def _search_state(self, operator, value):
        """Translate a state filter into a stored-field domain."""
        if operator not in ('in', 'not in', '=', '!='):
            raise UserError(_("Không hỗ trợ lọc trạng thái với toán tử %s.", operator))
        if operator in ('=', '!='):
            values = [value]
            negate = operator == '!='
        else:
            values = list(value)
            negate = operator == 'not in'

        today = fields.Date.context_today(self)
        done = Domain('member_status', '=', 'completed') | Domain('completion', '>=', 100)
        not_done = Domain('member_status', '!=', 'completed') & Domain('completion', '<', 100)
        enrolled = Domain('is_enrolled', '=', True)
        removed = Domain('channel_partner_id', '!=', False) & Domain('is_enrolled', '=', False)
        within_deadline = (
            Domain('date_deadline', '=', False) | Domain('date_deadline', '>=', today))

        branches = []
        if 'done' in values:
            branches.append(done)
        if 'removed' in values:
            branches.append(not_done & removed)
        if 'overdue' in values:
            branches.append(
                not_done & enrolled
                & Domain('date_deadline', '!=', False)
                & Domain('date_deadline', '<', today))
        if 'in_progress' in values:
            branches.append(
                not_done & enrolled & Domain('completion', '>', 0) & within_deadline)
        if 'not_started' in values:
            branches.append(
                not_done & enrolled & Domain('completion', '<=', 0) & within_deadline)

        combined = Domain.OR(branches) if branches else Domain.FALSE
        return ~combined if negate else combined

    @api.constrains('date_assigned', 'date_deadline')
    def _check_dates(self):
        for assignment in self:
            if assignment.date_deadline and assignment.date_deadline < assignment.date_assigned:
                raise ValidationError(_(
                    "Hạn hoàn thành không được sớm hơn ngày giao khoá học."))

    # Assigning a course also enrols the employee in it.
    @api.model_create_multi
    def create(self, vals_list):
        assignments = super().create(vals_list)
        assignments._ensure_enrolled()
        return assignments

    def _ensure_enrolled(self):
        """Assigning a course enrols the employee in it."""
        ChannelPartner = self.env['slide.channel.partner'].sudo()
        for assignment in self:
            if not assignment.partner_id:
                continue
            membership = ChannelPartner.with_context(active_test=False).search([
                ('channel_id', '=', assignment.channel_id.id),
                ('partner_id', '=', assignment.partner_id.id),
            ], limit=1)
            if membership and not membership.active:
                membership.action_unarchive()
            if not membership:
                membership = ChannelPartner.create({
                    'channel_id': assignment.channel_id.id,
                    'partner_id': assignment.partner_id.id,
                    'member_status': 'joined',
                })
            assignment.channel_partner_id = membership

    @api.model
    def _cron_remind_deadline(self, days_before=3):
        """Remind employees shortly before the deadline."""
        today = fields.Date.context_today(self)
        return self._notify_unfinished(
            [('date_deadline', '>=', today),
             ('date_deadline', '<=', fields.Date.add(today, days=days_before))],
            'assignment_reminder', 'reminder_sent')

    @api.model
    def _cron_notify_overdue(self):
        """Report overdue courses to the employee and their line manager."""
        today = fields.Date.context_today(self)
        return self._notify_unfinished(
            [('date_deadline', '<', today)],
            'assignment_overdue', 'overdue_notified')

    @api.model
    def _notify_unfinished(self, deadline_domain, template_key, flag):
        """Mail each unfinished assignment in *deadline_domain* exactly once.

        *flag* is the boolean that records the send. A failed send leaves it
        unset, so the next run retries that one assignment and nobody else
        waits for it. Without a template nothing is marked either, so a theme
        installed later still sends every pending mail.
        """
        template = self.env['slide.channel']._im_get_mail_template(template_key)
        if not template:
            _logger.warning(
                "im_elearning: no mail template '%s', assignments are not notified. "
                "Is im_theme installed?", template_key)
            return 0
        assignments = self.search(
            [(flag, '=', False), ('date_deadline', '!=', False)] + deadline_domain)
        sent = self.browse()
        for assignment in assignments:
            if assignment.state == 'done':
                continue
            if not assignment._send_template(template):
                continue
            sent |= assignment
        sent.write({flag: True})
        return len(sent)

    def _send_template(self, template):
        """Send one message, reporting whether it went out."""
        self.ensure_one()
        try:
            template.send_mail(self.id, force_send=False)
        except Exception:
            _logger.exception(
                "im_elearning: could not send %s for assignment #%s (%s)",
                template.name, self.id, self.employee_id.display_name)
            return False
        return True

    def action_reenroll(self):
        """Re-enrol someone CE removed from the course."""
        self._ensure_enrolled()
        return True

    def action_open_course(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.channel_id.website_url,
            'target': 'new',
        }


class ImCourseAssignmentWizard(models.TransientModel):
    """Assign one course to many employees, or to whole departments."""
    _name = 'im.course.assignment.wizard'
    _description = 'Giao khoá học hàng loạt'

    channel_id = fields.Many2one('slide.channel', string='Khoá học', required=True)
    employee_ids = fields.Many2many('hr.employee', string='Nhân viên')
    department_ids = fields.Many2many('hr.department', string='Phòng ban')
    date_deadline = fields.Date('Hạn hoàn thành')

    def action_assign(self):
        """Create the missing assignments and show the result."""
        self.ensure_one()
        employees = self.employee_ids
        if self.department_ids:
            employees |= self.env['hr.employee'].search([
                ('department_id', 'child_of', self.department_ids.ids)])
        if not employees:
            raise UserError(_("Chọn ít nhất một nhân viên hoặc một phòng ban."))

        Assignment = self.env['im.course.assignment']
        existing = Assignment.search([
            ('channel_id', '=', self.channel_id.id),
            ('employee_id', 'in', employees.ids),
        ])
        missing = employees - existing.employee_id
        Assignment.create([{
            'channel_id': self.channel_id.id,
            'employee_id': employee.id,
            'date_deadline': self.date_deadline,
        } for employee in missing])

        return {
            'type': 'ir.actions.act_window',
            'name': _('Khoá học được giao'),
            'res_model': 'im.course.assignment',
            'view_mode': 'list,form',
            'domain': [('channel_id', '=', self.channel_id.id)],
        }
