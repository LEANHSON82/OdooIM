from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


# Số tiền có nằm trong dải Từ – Đến hay không
def amount_in_band(amount, lower, upper, rounding):
    if float_compare(amount, lower, precision_rounding=rounding) <= 0:
        return False
    return not upper or float_compare(amount, upper, precision_rounding=rounding) <= 0


# Một cấp phải ký, chọn theo tổng dự toán của phiếu
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

    # Tiền tệ lấy theo công ty của cấp duyệt
    @api.depends('company_id')
    def _compute_currency_id(self):
        for level in self:
            level.currency_id = (level.company_id or self.env.company).currency_id

    # Chặn dải ngược: Đến phải lớn hơn Từ
    @api.constrains('amount_threshold', 'amount_max')
    def _check_amount_range(self):
        for level in self:
            if level.amount_max and level.amount_max <= level.amount_threshold:
                raise ValidationError(self.env._(
                    "Cấp “%s”: số “Đến” phải lớn hơn số “Từ”.", level.name))

    # Cấp duyệt chỉ nhận nhóm đã đánh dấu là nhóm duyệt
    @api.constrains('group_id')
    def _check_group_is_approver_role(self):
        # Bỏ qua khi hệ thống tự chép cấp giữa các công ty
        if self.env.context.get('im_skip_level_group_check'):
            return
        for level in self:
            if not level.group_id.im_is_approver_role:
                raise ValidationError(self.env._(
                    "Cấp “%(level)s”: nhóm “%(group)s” không phải nhóm duyệt. Chọn một nhóm "
                    "duyệt có sẵn hoặc gõ tên mới để tạo nhóm duyệt.",
                    level=level.name, group=level.group_id.display_name))

    # Cấp đã có lịch sử ký thì chỉ được tắt, không xoá
    def unlink(self):
        used = self.env['im.purchase.request.approval'].sudo().search(
            [('level_id', 'in', self.ids)]).level_id
        if used:
            raise UserError(self.env._(
                "Cấp %s đã có lịch sử duyệt nên không xoá được. Tắt “Đang dùng” để ngừng "
                "áp dụng cho phiếu mới.", ", ".join("“%s”" % name for name in used.mapped('name'))))
        return super().unlink()

    # Cấp nằm trong thiết lập nào thì lấy công ty của thiết lập đó
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('config_id'):
                vals['company_id'] = self.env['im.purchase.request.config'].browse(
                    vals['config_id']).company_id.id
        return super().create(vals_list)

    # Cấp này có phải ký cho số tiền này không
    def _applies_to(self, amount, rounding):
        self.ensure_one()
        return amount_in_band(amount, self.amount_threshold, self.amount_max, rounding)
