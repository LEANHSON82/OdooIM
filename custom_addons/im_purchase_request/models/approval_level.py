from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


# Whether the amount falls inside the from-to band
def amount_in_band(amount, lower, upper, rounding):
    if float_compare(amount, lower, precision_rounding=rounding) <= 0:
        return False
    return not upper or float_compare(amount, upper, precision_rounding=rounding) <= 0


# One level to sign, selected by the estimated total
class PurchaseRequestApprovalLevel(models.Model):
    _name = 'im.purchase.request.approval.level'
    _description = 'Cấp duyệt đề nghị mua hàng'
    _order = 'sequence, id'

    config_id = fields.Many2one(
        'im.purchase.request.config', string="Thiết lập", index=True, ondelete='cascade')
    name = fields.Char(string="Tên cấp", required=True, translate=True)
    sequence = fields.Integer(string="Thứ tự", default=10)
    group_id = fields.Many2one(
        'res.groups', string="Nhóm duyệt", required=True, ondelete='restrict',
        domain=[('im_is_approver_role', '=', True)],
        context={'default_im_is_approver_role': True},
        help="Chỉ người được tick nhóm này ở “Là người duyệt” mới ký được cấp này. "
             "Gõ tên mới để tạo nhóm duyệt mới.")
    amount_threshold = fields.Monetary(
        string="Từ (trên)", currency_field='currency_id',
        help="Cấp này ký khi tổng dự toán lớn hơn số này. 0 là mọi phiếu.")
    amount_max = fields.Monetary(
        string="Đến (tối đa)", currency_field='currency_id',
        help="Cấp này chỉ ký khi tổng dự toán không vượt số này. "
             "Để 0 là không giới hạn, tức phiếu lớn hơn vẫn phải qua cấp này.")
    scope = fields.Selection(
        [('company', "Toàn công ty"),
         ('department', "Theo phòng của người đề nghị")],
        string="Phạm vi", default='company', required=True,
        help="Toàn công ty: ai trong nhóm cũng ký được.\n"
             "Theo phòng: phải là trưởng bộ phận của người đề nghị.")
    company_id = fields.Many2one(
        'res.company', string="Công ty", default=lambda self: self.env.company,
        help="Để trống là áp dụng mọi công ty.")
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')
    active = fields.Boolean(string="Đang dùng", default=True)

    # Currency follows the company of the approval level
    @api.depends('company_id')
    def _compute_currency_id(self):
        for level in self:
            level.currency_id = (level.company_id or self.env.company).currency_id

    # Reject a backwards band: "to" must be above "from"
    @api.constrains('amount_threshold', 'amount_max')
    def _check_amount_range(self):
        for level in self:
            if level.amount_max and level.amount_max <= level.amount_threshold:
                raise ValidationError(self.env._(
                    "Cấp “%s”: số “Đến” phải lớn hơn số “Từ”.", level.name))

    # A level only accepts a group marked as an approver role
    @api.constrains('group_id')
    def _check_group_is_approver_role(self):
        # Skipped while the system copies levels between companies
        if self.env.context.get('im_skip_level_group_check'):
            return
        for level in self:
            if not level.group_id.im_is_approver_role:
                raise ValidationError(self.env._(
                    "Cấp “%(level)s”: nhóm “%(group)s” không phải nhóm duyệt. Chọn một nhóm "
                    "duyệt có sẵn hoặc gõ tên mới để tạo nhóm duyệt.",
                    level=level.name, group=level.group_id.display_name))

    # A level with approval history can only be archived, never deleted
    def unlink(self):
        used = self.env['im.purchase.request.approval'].sudo().search(
            [('level_id', 'in', self.ids)]).level_id
        if used:
            raise UserError(self.env._(
                "Cấp %s đã có lịch sử duyệt nên không xoá được. Tắt “Đang dùng” để ngừng "
                "áp dụng cho phiếu mới.", ", ".join("“%s”" % name for name in used.mapped('name'))))
        return super().unlink()

    # A level takes the company of the settings holding it
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('config_id'):
                vals['company_id'] = self.env['im.purchase.request.config'].browse(
                    vals['config_id']).company_id.id
        return super().create(vals_list)

    # Does this level have to sign for that amount
    def _applies_to(self, amount, rounding):
        self.ensure_one()
        return amount_in_band(amount, self.amount_threshold, self.amount_max, rounding)
