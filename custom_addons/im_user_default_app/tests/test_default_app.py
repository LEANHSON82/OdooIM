from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestUserDefaultApp(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Người dùng thử',
            'login': 'im_default_app_test',
        })
        cls.app = cls.env['ir.ui.menu'].search([('parent_id', '=', False)], limit=1)

    def test_setting_app_sets_landing_action(self):
        self.user.write({'default_app_id': self.app.id})
        self.assertTrue(self.user.action_id,
                        "Picking a default app must set the login action")

    def test_clearing_app_restores_default_behaviour(self):
        """Clearing the default app must restore stock Odoo behaviour.

        Users could only switch to another app, never clear it: a many2one
        is cleared by selecting the text and deleting it, which almost
        nobody discovers.
        """
        self.user.write({'default_app_id': self.app.id})
        self.assertTrue(self.user.action_id)

        self.user.action_clear_default_app()

        self.assertFalse(self.user.default_app_id)
        self.assertFalse(self.user.default_menu_id)
        self.assertFalse(self.user.action_id,
                         "Clearing the default app must leave no stale action behind")

    def test_clearing_twice_does_not_raise(self):
        self.user.action_clear_default_app()
        self.user.action_clear_default_app()
        self.assertFalse(self.user.action_id)

    def test_clearing_also_drops_submenu(self):
        submenu = self.env['ir.ui.menu'].search([
            ('id', 'child_of', self.app.id),
            ('id', '!=', self.app.id),
            ('action', '!=', False),
        ], limit=1)
        if not submenu:
            self.skipTest("No submenu with an action to test against")

        self.user.write({
            'default_app_id': self.app.id,
            'default_menu_id': submenu.id,
        })
        self.user.action_clear_default_app()
        self.assertFalse(self.user.default_menu_id)

    def test_changing_app_still_works(self):
        """Switching to another app must keep working."""
        other = self.env['ir.ui.menu'].search([
            ('parent_id', '=', False), ('id', '!=', self.app.id),
        ], limit=1)
        if not other:
            self.skipTest("Only one root app in this database")

        self.user.write({'default_app_id': self.app.id})
        self.user.write({'default_app_id': other.id})
        self.assertEqual(self.user.default_app_id, other)
