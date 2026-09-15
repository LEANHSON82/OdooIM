from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    x_color_scheme = fields.Selection(
        related='res_users_settings_id.x_color_scheme',
        readonly=False,
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['x_color_scheme']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['x_color_scheme']