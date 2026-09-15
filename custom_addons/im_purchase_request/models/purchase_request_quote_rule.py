from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

from .approval_level import amount_in_band


# Số nhà cung cấp tối thiểu theo dải thành tiền dòng hàng
class PurchaseRequestQuoteRule(models.Model):
    _name = 'im.purchase.request.quote.rule'
    _description = 'Số nhà cung cấp tối thiểu theo thành tiền dòng hàng'
    _order = 'sequence, amount_threshold, id'

    config_id = fields.Many2one(
        'im.purchase.request.config', string="Thiết lập", required=True,
        index=True, ondelete='cascade')
    company_id = fields.Many2one(related='config_id.company_id', store=True)
    currency_id = fields.Many2one(related='config_id.currency_id')
    sequence = fields.Integer(default=10)
    amount_threshold = fields.Monetary(
        string="Từ (trên)", currency_field='currency_id',
        help="Áp khi thành tiền dòng hàng lớn hơn số này. 0 là mọi dòng.")
    amount_max = fields.Monetary(
        string="Đến (tối đa)", currency_field='currency_id',
        help="Áp khi thành tiền dòng hàng không vượt số này. 0 là không giới hạn.")
    min_quote_count = fields.Integer(
        string="Số NCC tối thiểu", default=1,
        help="0 là không bắt buộc báo giá cho dải này.")

    # Dải phải thuận và số nhà cung cấp không được âm
    @api.constrains('amount_threshold', 'amount_max', 'min_quote_count')
    def _check_values(self):
        for rule in self:
            if rule.amount_max and rule.amount_max <= rule.amount_threshold:
                raise ValidationError(self.env._("Số “Đến” phải lớn hơn số “Từ”."))
            if rule.min_quote_count < 0:
                raise ValidationError(self.env._("Số nhà cung cấp tối thiểu không được âm."))

    # Dải bắt đầu từ 0 áp cho cả dòng chưa có tiền
    def _applies_to(self, amount, rounding):
        self.ensure_one()
        if not self.amount_threshold and float_compare(amount, 0.0, precision_rounding=rounding) <= 0:
            return True
        return amount_in_band(amount, self.amount_threshold, self.amount_max, rounding)
