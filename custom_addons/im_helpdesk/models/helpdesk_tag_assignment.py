"""Tag-based assignment rules for IM Helpdesk.

Each record ties a tag, an optional team and the users allowed to take tickets carrying
that tag. On ticket creation these rules drive both routing by tag and the choice of
assignee.
"""

from odoo import fields, models


class HelpdeskTagAssignment(models.Model):
    """Map a ticket tag to the eligible agents of a helpdesk team."""

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
