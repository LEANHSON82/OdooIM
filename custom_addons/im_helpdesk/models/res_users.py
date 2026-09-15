"""Phần mở rộng user cho chỉ tiêu dashboard Helpdesk và helper lịch làm việc."""

from collections import defaultdict

from dateutil import relativedelta
from pytz import timezone

from odoo import fields, models


class ResUsers(models.Model):
    """Thêm chỉ tiêu KPI Helpdesk theo từng user và tiện ích tính thời gian làm việc."""

    _inherit = 'res.users'

    helpdesk_target_closed = fields.Integer(export_string_translation=False, default=1)
    helpdesk_target_rating = fields.Float(export_string_translation=False, default=4.5)
    helpdesk_target_success = fields.Float(export_string_translation=False, default=85)

    _target_closed_not_zero = models.Constraint(
        'CHECK(helpdesk_target_closed > 0)',
        "You cannot have negative targets",
    )
    _target_rating_not_zero = models.Constraint(
        'CHECK(helpdesk_target_rating > 0)',
        "You cannot have negative targets",
    )
    _target_success_not_zero = models.Constraint(
        'CHECK(helpdesk_target_success > 0)',
        "You cannot have negative targets",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        """Cho phép user đọc các field chỉ tiêu KPI helpdesk của chính họ."""
        return super().SELF_READABLE_FIELDS + [
            'helpdesk_target_closed',
            'helpdesk_target_rating',
            'helpdesk_target_success',
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        """Cho phép user cập nhật các field chỉ tiêu KPI helpdesk của chính họ."""
        return super().SELF_WRITEABLE_FIELDS + [
            'helpdesk_target_closed',
            'helpdesk_target_rating',
            'helpdesk_target_success',
        ]

    def _get_working_user_interval(self, start_dt, end_dt, calendar, compute_leaves=True):
        """Trả về các khoảng thời gian làm việc của resource user trên một calendar."""
        return calendar._work_intervals_batch(
            start_dt,
            end_dt,
            resources=self.resource_ids,
            compute_leaves=compute_leaves
        )

    def _get_working_users_per_first_working_day(self):
        """Nhóm user theo ngày làm việc sớm nhất tiếp theo của họ.

        Auto-assignment dùng danh sách đã sắp xếp này để ưu tiên user đi làm
        sớm hơn, đồng thời vẫn tôn trọng calendar cá nhân nếu user có cấu hình.
        """
        tz = timezone(self.env.context.get('tz') or 'UTC')
        start_dt = fields.Datetime.now().astimezone(tz)
        end_dt = start_dt + relativedelta.relativedelta(days=7, hour=23, minute=59, second=59)
        workers_per_first_working_date = defaultdict(list)
        users_per_calendar = defaultdict(lambda: self.env['res.users'])
        company_calendar = self.env.company.resource_calendar_id
        for user in self:
            calendar = user.resource_calendar_id or company_calendar
            users_per_calendar[calendar] |= user
        for calendar, users in users_per_calendar.items():
            work_intervals_per_resource = users._get_working_user_interval(start_dt, end_dt, calendar)
            for user in users:
                for resource_id in user.resource_ids.ids:
                    intervals = work_intervals_per_resource[resource_id]
                    if intervals:
                        workers_per_first_working_date[(intervals._items)[0][0].date()].append(user.id)
                        break
                if user.id and not user.resource_ids:
                    intervals = work_intervals_per_resource[False]
                    if intervals:
                        workers_per_first_working_date[(intervals._items)[0][0].date()].append(user.id)
        return [value for _key, value in sorted(workers_per_first_working_date.items())]
