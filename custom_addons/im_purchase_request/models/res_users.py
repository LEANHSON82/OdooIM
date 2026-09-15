from odoo import api, fields, models
from odoo.fields import Command

# Tab cấu hình cá nhân trên form người dùng
class ResUsers(models.Model):
    _inherit = 'res.users'

    im_approver_group_ids = fields.Many2many(
        'res.groups', string="Là người duyệt",
        compute='_compute_im_purchase_request_roles',
        inverse='_inverse_im_approver_group_ids',
        domain=[('im_is_approver_role', '=', True)])
    im_can_configure = fields.Boolean(
        string="Có quyền cấu hình",
        compute='_compute_im_purchase_request_roles',
        inverse='_inverse_im_can_configure')

    # Đọc vai trò từ các nhóm người dùng đang có
    @api.depends('group_ids')
    def _compute_im_purchase_request_roles(self):
        manager = self.env.ref('im_purchase_request.group_manager')
        for user in self:
            user.im_approver_group_ids = user.group_ids.filtered('im_is_approver_role')
            user.im_can_configure = manager in user.group_ids

    # Tick ô nào thì gán nhóm duyệt tương ứng
    def _inverse_im_approver_group_ids(self):
        for user in self:
            current = user.group_ids.filtered('im_is_approver_role')
            wanted = user.im_approver_group_ids
            commands = ([Command.unlink(group.id) for group in current - wanted]
                        + [Command.link(group.id) for group in wanted - current])
            if commands:
                user.group_ids = commands

    # Bật tắt nhóm quản trị đề nghị mua hàng
    def _inverse_im_can_configure(self):
        manager = self.env.ref('im_purchase_request.group_manager')
        for user in self:
            if user.im_can_configure and manager not in user.group_ids:
                user.group_ids = [Command.link(manager.id)]
            elif not user.im_can_configure and manager in user.group_ids:
                user.group_ids = [Command.unlink(manager.id)]
