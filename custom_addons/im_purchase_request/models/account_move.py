from odoo import api, fields, models
from odoo.exceptions import UserError

# Vendor bills and vendor refunds
VENDOR_MOVES = ('in_invoice', 'in_refund')

# Block a bill that passes the request's estimated total
class AccountMove(models.Model):
    _inherit = 'account.move'

    im_over_budget = fields.Boolean(
        string="Vượt dự toán", compute='_compute_im_over_budget')
    im_overrun_reason = fields.Text(
        string="Lý do duyệt vượt dự toán", readonly=True, copy=False)
    im_overrun_user_id = fields.Many2one(
        'res.users', string="Người duyệt vượt", readonly=True, copy=False)

    # The requests behind the purchase order lines of this bill
    def _related_requests(self):
        self.ensure_one()
        return self.sudo().invoice_line_ids.purchase_line_id.order_id.im_request_id

    # Flag raising the red warning on the bill form
    @api.depends('invoice_line_ids.purchase_line_id', 'im_overrun_reason',
                 'invoice_line_ids.balance')
    def _compute_im_over_budget(self):
        for move in self:
            move.im_over_budget = bool(move._ceiling_errors())

    # Empty while the bill stays under the ceiling, or was already approved
    def _ceiling_errors(self):
        self.ensure_one()
        if self.move_type not in VENDOR_MOVES or self.im_overrun_reason:
            return []
        errors = []
        for request in self._related_requests():
            error = request._invoice_ceiling_error(self)
            if error:
                errors.append(error)
        return errors

    # Without an overrun approval the bill cannot be posted
    def _post(self, soft=True):
        for move in self:
            errors = move._ceiling_errors()
            if errors:
                raise UserError("\n\n".join(errors))
        return super()._post(soft=soft)
