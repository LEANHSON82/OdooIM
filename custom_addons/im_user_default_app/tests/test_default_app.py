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
                        "Chọn app mặc định phải đặt hành động khi đăng nhập")

    def test_clearing_app_restores_default_behaviour(self):
        """Bỏ app mặc định phải trả về hành vi gốc của Odoo.

        Trước đây chỉ đổi được sang app khác chứ không bỏ được, vì ô many2one
        muốn xoá phải bôi đen rồi xoá chữ — gần như không ai đoán ra.
        """
        self.user.write({'default_app_id': self.app.id})
        self.assertTrue(self.user.action_id)

        self.user.action_clear_default_app()

        self.assertFalse(self.user.default_app_id)
        self.assertFalse(self.user.default_menu_id)
        self.assertFalse(self.user.action_id,
                         "Bỏ app mặc định thì không được để sót hành động cũ")

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
            self.skipTest("Không có menu con nào có action để thử")

        self.user.write({
            'default_app_id': self.app.id,
            'default_menu_id': submenu.id,
        })
        self.user.action_clear_default_app()
        self.assertFalse(self.user.default_menu_id)

    def test_changing_app_still_works(self):
        """Không được phá đường đổi sang app khác."""
        other = self.env['ir.ui.menu'].search([
            ('parent_id', '=', False), ('id', '!=', self.app.id),
        ], limit=1)
        if not other:
            self.skipTest("Chỉ có một app gốc trong cơ sở dữ liệu")

        self.user.write({'default_app_id': self.app.id})
        self.user.write({'default_app_id': other.id})
        self.assertEqual(self.user.default_app_id, other)
