from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

# Purchase orders born from a request, with the ceiling check
class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    im_request_id = fields.Many2one(
        'im.purchase.request', string="Đề nghị mua hàng",
        readonly=True, copy=False, ondelete='restrict', index='btree_not_null',
        help="Phiếu đã sinh ra đơn mua này.")

    # On confirm: the orders together must stay under the request ceiling
    def button_confirm(self):
        for order in self.filtered('im_request_id'):
            order._check_request_ceiling()
        return super().button_confirm()

    # Cancelling every order reopens the request for new ones
    def button_cancel(self):
        res = super().button_cancel()
        self.im_request_id.sudo()._reopen_if_orders_cancelled()
        return res

    # Sum every order that is not cancelled, in the request currency
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
