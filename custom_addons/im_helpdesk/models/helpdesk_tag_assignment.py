"""Quy tắc phân công theo tag cho IM Helpdesk.

Mỗi record liên kết một tag, một team tùy chọn và các user có thể nhận ticket
chứa tag đó. Khi tạo ticket, hệ thống dùng các rule này để route theo tag và
chọn người xử lý theo tag.
"""

from odoo import fields, models


class HelpdeskTagAssignment(models.Model):
    """Ánh xạ tag của ticket tới các nhân viên đủ điều kiện trong một team helpdesk."""

    _name = 'helpdesk.tag.assignment'
    _description = "Helpdesk Tag Assignment"

    team_id = fields.Many2one('helpdesk.team', export_string_translation=False)
    tag_id = fields.Many2one('helpdesk.tag', "Ticket Tag", required=True)
    user_ids = fields.Many2many('res.users', string="Team Members", required=True)
    route_weight = fields.Integer(
        "Routing Weight",
        default=1,
        help="Score added when this tag matches. Higher values make this team and these users more likely to be selected.")

    _tag_team_unique = models.Constraint(
        'UNIQUE(team_id, tag_id)',
        "A tag can only be used once per team.",
    )
    _route_weight_positive = models.Constraint(
        'CHECK(route_weight > 0)',
        "Routing weight must be positive.",
    )
