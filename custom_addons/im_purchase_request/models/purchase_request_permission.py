from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .approval_level import amount_in_band

# The two rights that are configurable by amount band
PERMISSION_TYPES = [
    ('po_creator', "Tạo đơn mua"),
    ('overrun', "Duyệt vượt dự toán"),
]


# One permission row: an amount band and who it allows
class PurchaseRequestPermission(models.Model):
    _name = 'im.purchase.request.permission'
    _description = 'Quyền theo dải giá trị của đề nghị mua hàng'
    _order = 'permission_type, sequence, amount_threshold, id'

    config_id = fields.Many2one(
        'im.purchase.request.config', string="Thiết lập", index=True, ondelete='cascade')
    permission_type = fields.Selection(
        PERMISSION_TYPES, string="Quyền", required=True, index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', string="Công ty", index=True,
        default=lambda self: self.env.company, ondelete='cascade')
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount_threshold = fields.Monetary(
        string="Từ (trên)", currency_field='currency_id',
        help="Dòng này áp khi số tiền lớn hơn số này. 0 là mọi số tiền.")
    amount_max = fields.Monetary(
        string="Đến (tối đa)", currency_field='currency_id',
        help="Dòng này áp khi số tiền không vượt số này. 0 là không giới hạn.")
    group_ids = fields.Many2many(
        'res.groups', 'im_purchase_request_permission_group_rel', 'permission_id', 'group_id',
        string="Nhóm")
    user_ids = fields.Many2many(
        'res.users', 'im_purchase_request_permission_user_rel', 'permission_id', 'user_id',
        string="Người cụ thể", domain=[('share', '=', False)])

    # Reject a backwards band: "to" must be above "from"
    @api.constrains('amount_threshold', 'amount_max')
    def _check_amount_range(self):
        for rule in self:
            if rule.amount_max and rule.amount_max <= rule.amount_threshold:
                raise ValidationError(self.env._("Số “Đến” phải lớn hơn số “Từ”."))

    # Every row must name at least one group or one user
    @api.constrains('permission_type', 'group_ids', 'user_ids')
    def _check_someone_selected(self):
        for rule in self:
            if not (rule.group_ids or rule.user_ids):
                raise ValidationError(self.env._(
                    "Mỗi dòng giới hạn phải chọn ít nhất một nhóm hoặc một người."))

    # A row takes the company of the settings holding it
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('config_id'):
                vals['company_id'] = self.env['im.purchase.request.config'].browse(
                    vals['config_id']).company_id.id
        return super().create(vals_list)

    # Does this row apply to that amount
    def _applies_to(self, amount, rounding):
        self.ensure_one()
        return amount_in_band(amount, self.amount_threshold, self.amount_max, rounding)

    # Is the user in one of the groups, or named directly
    def _allows(self, user):
        self.ensure_one()
        return bool(user in self.user_ids or self.group_ids & user.all_group_ids)

    # Join group and user names for the error message
    def _describe(self):
        self.ensure_one()
        return ", ".join(self.group_ids.mapped('display_name') + self.user_ids.mapped('name'))
