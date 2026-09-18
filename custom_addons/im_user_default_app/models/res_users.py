
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
        # The submenu belongs to the old app, so drop it on app change.
        for user in self:
            user.default_menu_id = False

    def action_clear_default_app(self):
        """Clear the default app and restore stock Odoo behaviour.

        A many2one is cleared by selecting the text and deleting it,
        which almost nobody discovers, so users felt stuck with the
        first app they picked. This button makes clearing visible.
        """
        self.write({
            'default_app_id': False,
            'default_menu_id': False,
        })
        return True

    # Without these two, a plain user opening Preferences hits AccessError.
    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['default_app_id', 'default_menu_id']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['default_app_id', 'default_menu_id']

    def _get_app_landing_action(self, menu):
        """Walk down the menu tree to the first child holding an action."""
        # sudo() only to read the menu tree; the action checks rights itself.
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
        """Translate the chosen app/menu into core's action_id.

        Odoo itself only knows action_id; the two fields above are just a
        friendlier way to pick one. Synced on create and write so RPC
        callers get the same behaviour as the form.
        """
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
