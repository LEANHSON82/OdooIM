from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

# Đơn mua sinh từ phiếu đề nghị, kèm kiểm tra trần chi
class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    im_request_id = fields.Many2one(
        'im.purchase.request', string="Đề nghị mua hàng",
        readonly=True, copy=False, ondelete='restrict', index='btree_not_null',
        help="Phiếu đã sinh ra đơn mua này.")

    # Xác nhận đơn: tổng các đơn không được vượt trần của phiếu
    def button_confirm(self):
        for order in self.filtered('im_request_id'):
            order._check_request_ceiling()
        return super().button_confirm()

    # Hủy hết đơn thì mở lại phiếu để tạo đơn khác
    def button_cancel(self):
        res = super().button_cancel()
        self.im_request_id.sudo()._reopen_if_orders_cancelled()
        return res

    # Cộng mọi đơn chưa hủy, quy về tiền tệ của phiếu
    def _check_request_ceiling(self):
        self.ensure_one()
        request = self.im_request_id
        currency = request.currency_id
        ceiling = request._overrun_ceiling()
        total = sum(
            order.currency_id._convert(
                order.amount_untaxed, currency, order.company_id,
                order.date_order or fields.Date.context_today(order))
            for order in request.purchase_order_ids
            if order.state != 'cancel')

        if float_compare(total, ceiling, precision_rounding=currency.rounding) > 0:
            raise UserError(self.env._(
                "Tổng đơn mua %(total)s vượt %(pct)s%% so với phiếu %(name)s "
                "đã duyệt (%(approved)s). Sửa lại giá trên đơn.",
                total=currency.format(total),
                pct=request._overrun_tolerance(),
                name=request.name,
                approved=currency.format(request.amount_total)))
