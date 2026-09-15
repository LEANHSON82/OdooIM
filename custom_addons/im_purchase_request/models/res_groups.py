from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Nhóm hệ thống, không được dùng làm nhóm duyệt
PROTECTED_GROUPS = (
    'base.group_user', 'base.group_portal', 'base.group_public',
    'base.group_system', 'base.group_erp_manager', 'base.group_no_one',
)

# Đánh dấu nhóm nào là nhóm duyệt của module
class ResGroups(models.Model):
    _inherit = 'res.groups'

    im_is_approver_role = fields.Boolean(
        string="Nhóm duyệt đề nghị mua hàng",
        help="Hiện trong mục “Là người duyệt” trên người dùng và chọn được cho cấp duyệt.")

    # Nhóm hệ thống hoặc nhóm chia sẻ thì không dùng được
    def _im_is_protected(self):
        self.ensure_one()
        protected = [self.env.ref(xmlid, raise_if_not_found=False) for xmlid in PROTECTED_GROUPS]
        return self.share or self in protected

    # Chặn lấy nhóm hệ thống làm nhóm duyệt
    @api.constrains('im_is_approver_role')
    def _check_im_approver_role(self):
        for group in self:
            if group.im_is_approver_role and group._im_is_protected():
                raise ValidationError(self.env._(
                    "Nhóm “%s” là nhóm hệ thống, không dùng làm nhóm duyệt được.",
                    group.display_name))

    # Người có quyền cấu hình chỉ tạo được nhóm duyệt thường
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.has_group('base.group_erp_manager'):
            vals_list = [
                {'name': vals.get('name'), 'im_is_approver_role': True}
                for vals in vals_list
            ]
        return super().create(vals_list)

    # Gõ tên mới ở ô Nhóm duyệt thì tạo nhóm luôn
    @api.model
    def name_create(self, name):
        if not self.env.context.get('default_im_is_approver_role'):
            return super().name_create(name)
        group = self.create({'name': name, 'im_is_approver_role': True})
        return group.id, group.display_name
