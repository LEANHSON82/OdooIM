
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    default_app_id = fields.Many2one(
        'ir.ui.menu',
        string='Default App',
        domain="[('parent_id', '=', False)]",
        help='App that will be opened automatically after login.',
    )
    default_menu_id = fields.Many2one(
        'ir.ui.menu',
        string='Default Menu',
        domain="[('id', 'child_of', default_app_id), ('id', '!=', default_app_id)]",
        help='Specific menu inside the App that will be opened.',
    )

    @api.onchange('default_app_id')
    def _onchange_default_app_id(self):
        for user in self:
            user.default_menu_id = False

    def action_clear_default_app(self):
        """Bỏ app mặc định, quay lại hành vi gốc của Odoo.

        Ô many2one vốn xoá được bằng cách bôi đen rồi xoá chữ, nhưng gần như
        không ai đoán ra — nên đã chọn một app là coi như mắc kẹt, chỉ đổi được
        sang app khác. Nút này làm việc bỏ trở nên nhìn thấy được.
        """
        self.write({
            'default_app_id': False,
            'default_menu_id': False,
        })
        return True

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['default_app_id', 'default_menu_id']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['default_app_id', 'default_menu_id']

    def _get_app_landing_action(self, menu):
        menu = menu.sudo()
        if not menu:
            return self.env['ir.actions.actions'].browse()
        if menu.action:
            return menu.action
        for child in menu.child_id:
            action = self._get_app_landing_action(child)
            if action:
                return action
        return self.env['ir.actions.actions'].browse()

    def _sync_default_app_to_action(self):
        for user in self:
            target_menu = user.default_menu_id or user.default_app_id
            action = (
                user._get_app_landing_action(target_menu)
                if target_menu else False
            )
            user.action_id = action.id if action else False

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users.filtered(lambda u: u.default_app_id or u.default_menu_id)._sync_default_app_to_action()
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'default_app_id' in vals or 'default_menu_id' in vals:
            self._sync_default_app_to_action()
        return res
