"""Model trạng thái SLA theo từng ticket.

Các record trong model này liên kết ticket với SLA policy đang áp dụng, lưu hạn
xử lý đã tính và theo dõi ticket có đạt stage mục tiêu đúng hạn hay không.
"""

import math

from odoo import fields, models, api
from odoo.fields import Domain


class HelpdeskSlaStatus(models.Model):
    """Theo dõi tiến độ của một SLA policy trên một ticket."""

    _name = 'helpdesk.sla.status'
    _description = "Ticket SLA Status"
    _table = 'helpdesk_sla_status'
    _order = 'deadline ASC, sla_stage_id'
    _rec_name = 'sla_id'

    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', required=True, ondelete='cascade', index=True)
    sla_id = fields.Many2one('helpdesk.sla', required=True, ondelete='cascade')
    sla_stage_id = fields.Many2one('helpdesk.stage', related='sla_id.stage_id', store=True, export_string_translation=False)
    deadline = fields.Datetime("Deadline", compute='_compute_deadline', compute_sudo=True, store=True)
    reached_datetime = fields.Datetime("Reached Date", help="Datetime at which the SLA stage was reached for the first time")
    status = fields.Selection([('failed', 'Failed'), ('reached', 'Reached'), ('ongoing', 'Ongoing')], string="Status", compute='_compute_status', compute_sudo=True, search='_search_status')
    color = fields.Integer("Color Index", compute='_compute_color')
    exceeded_hours = fields.Float("Exceeded Working Hours", compute='_compute_exceeded_hours', compute_sudo=True, store=True, help="Working hours exceeded for reached SLAs compared with deadline.")

    @api.depends('ticket_id.create_date', 'sla_id', 'ticket_id.stage_id')
    def _compute_deadline(self):
        """Tính deadline theo giờ làm việc cho từng trạng thái SLA.

        Các stage bị exclude sẽ tạm dừng đồng hồ SLA. Nếu ticket hiện đang nằm
        trong stage bị exclude, deadline sẽ tạm thời được xóa cho tới khi ticket
        quay lại stage được tính vào SLA.
        """
        for status in self:
            if (status.deadline and status.reached_datetime) or (status.deadline and not status.sla_id.exclude_stage_ids) or (status.status == 'failed'):
                continue
            deadline = status.ticket_id.create_date
            working_calendar = status.ticket_id.team_id.resource_calendar_id
            if not working_calendar:
                status.deadline = deadline
                continue

            if status.sla_id.exclude_stage_ids:
                if status.ticket_id.stage_id in status.sla_id.exclude_stage_ids:
                    status.deadline = False
                    continue

            avg_hour = working_calendar.hours_per_day or 8
            time_days = math.floor(status.sla_id.time / avg_hour)
            if time_days > 0:
                deadline = working_calendar.plan_days(time_days + 1, deadline, compute_leaves=True)
                create_dt = working_calendar.plan_hours(0, status.ticket_id.create_date)
                deadline = deadline and deadline.replace(hour=create_dt.hour, minute=create_dt.minute, second=create_dt.second, microsecond=create_dt.microsecond)

            sla_hours = status.sla_id.time % avg_hour

            if status.sla_id.exclude_stage_ids:
                sla_hours += status._get_freezed_hours(working_calendar)

            deadline_for_working_cal = working_calendar.plan_hours(0, deadline)
            if deadline_for_working_cal and deadline.day < deadline_for_working_cal.day and time_days > 0:
                deadline = deadline.replace(hour=0, minute=0, second=0, microsecond=0)
            status.deadline = deadline and working_calendar.plan_hours(sla_hours, deadline, compute_leaves=True)

    @api.depends('deadline', 'reached_datetime')
    def _compute_status(self):
        """Hiển thị trạng thái SLA là failed, reached hoặc ongoing."""
        for status in self:
            if status.reached_datetime and status.deadline:
                status.status = 'reached' if status.reached_datetime < status.deadline else 'failed'
            else:
                status.status = 'ongoing' if not status.deadline or status.deadline > fields.Datetime.now() else 'failed'

    @api.model
    def _search_status(self, operator, value):
        """Chuyển tìm kiếm status ảo thành domain theo deadline/reached."""
        if operator != 'in':
            return NotImplemented
        datetime_now = fields.Datetime.now()
        domains = []
        if 'failed' in value:
            domains.append(['|', '&', ('reached_datetime', '=', True), ('deadline', '<=', 'reached_datetime'), '&', ('reached_datetime', '=', False), ('deadline', '<=', datetime_now)])
        if 'reached' in value:
            domains.append(['&', ('reached_datetime', '=', True), ('reached_datetime', '<', 'deadline')])
        if 'ongoing' in value:
            domains.append(['|', ('deadline', '=', False), '&', ('reached_datetime', '=', False), ('deadline', '>', datetime_now)])
        return Domain.OR(domains)

    @api.depends('status')
    def _compute_color(self):
        """Ánh xạ trạng thái SLA sang mã màu trên kanban/list."""
        for status in self:
            if status.status == 'failed':
                status.color = 1
            elif status.status == 'reached':
                status.color = 10
            else:
                status.color = 0

    @api.depends('deadline', 'reached_datetime')
    def _compute_exceeded_hours(self):
        """Tính số giờ làm việc sớm hoặc trễ so với deadline SLA.

        Giá trị âm nghĩa là ticket vẫn còn trước deadline hoặc đã đạt mục tiêu
        sớm. Giá trị dương nghĩa là ticket đã vượt quá deadline.
        """
        for status in self:
            if status.deadline and status.ticket_id.team_id.resource_calendar_id:
                reached_datetime = status.reached_datetime or fields.Datetime.now()
                if reached_datetime <= status.deadline:
                    start_dt = reached_datetime
                    end_dt = status.deadline
                    factor = -1
                else:
                    start_dt = status.deadline
                    end_dt = reached_datetime
                    factor = 1
                duration_data = status.ticket_id.team_id.resource_calendar_id.get_work_duration_data(start_dt, end_dt, compute_leaves=True)
                status.exceeded_hours = duration_data['hours'] * factor
            else:
                status.exceeded_hours = False

    def _get_freezed_hours(self, working_calendar):
        """Trả về số giờ làm việc ticket nằm trong các stage bị exclude khỏi SLA.

        Hàm đọc tracking line của stage để dựng lại thời điểm ticket ở trong các
        stage bị exclude, rồi cộng khoảng thời gian đó ngược lại vào deadline.
        """
        self.ensure_one()
        hours_freezed = 0

        field_stage = self.env['ir.model.fields']._get(self.ticket_id._name, "stage_id")
        freeze_stages = self.sla_id.exclude_stage_ids.ids
        tracking_lines = self.ticket_id.message_ids.tracking_value_ids.filtered(lambda tv: tv.field_id == field_stage).sorted(key="create_date")

        if not tracking_lines:
            return 0

        old_time = self.ticket_id.create_date
        for tracking_line in tracking_lines:
            if tracking_line.old_value_integer in freeze_stages:
                hours_freezed += working_calendar.get_work_hours_count(old_time, tracking_line.create_date)
            old_time = tracking_line.create_date
        if tracking_lines[-1].new_value_integer in freeze_stages:
            hours_freezed += working_calendar.get_work_hours_count(old_time, fields.Datetime.now())
        return hours_freezed
