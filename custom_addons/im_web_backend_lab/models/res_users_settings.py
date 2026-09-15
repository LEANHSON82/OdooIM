from odoo import fields, models


class ResUsersSettings(models.Model):
    _inherit = 'res.users.settings'

    x_homemenu_config = fields.Json(
        string="Home Menu Config",
        readonly=True,
    )
    x_color_scheme = fields.Selection(
        selection=[
            ('system', 'System'),
            ('light', 'Light'),
            ('dark', 'Dark'),
        ],
        string="Color Scheme",
        default='system',
    )