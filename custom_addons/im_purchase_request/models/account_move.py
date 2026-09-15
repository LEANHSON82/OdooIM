from odoo import api, fields, models
from odoo.exceptions import UserError

# Hóa đơn mua và hóa đơn hoàn của nhà cung cấp
VENDOR_MOVES = ('in_invoice', 'in_refund')

# Chặn hóa đơn vượt dự toán của phiếu đề nghị
class AccountMove(models.Model):
    _inherit = 'account.move'

    im_over_budget = fields.Boolean(
        string="Vượt dự toán", compute='_compute_im_over_budget')
    im_overrun_reason = fields.Text(
        string="Lý do duyệt vượt dự toán", readonly=True, copy=False)
    im_overrun_user_id = fields.Many2one(
        'res.users', string="Người duyệt vượt", readonly=True, copy=False)

    # Các phiếu đề nghị đứng sau dòng đơn mua của hóa đơn
    def _related_requests(self):
        self.ensure_one()
        return self.sudo().invoice_line_ids.purchase_line_id.order_id.im_request_id

    # Cờ bật cảnh báo đỏ trên form hóa đơn
    @api.depends('invoice_line_ids.purchase_line_id', 'im_overrun_reason',
                 'invoice_line_ids.balance')
    def _compute_im_over_budget(self):
        for move in self:
            move.im_over_budget = bool(move._ceiling_errors())

    # Rỗng khi hóa đơn còn trong trần, hoặc đã có lý do duyệt vượt
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

    # Chưa duyệt vượt thì không cho vào sổ
    def _post(self, soft=True):
        for move in self:
            errors = move._ceiling_errors()
            if errors:
                raise UserError("\n\n".join(errors))
        return super()._post(soft=soft)
