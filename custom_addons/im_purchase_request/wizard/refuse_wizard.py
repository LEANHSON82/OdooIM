from odoo import fields, models

# Hộp thoại hỏi lý do trước khi từ chối phiếu
class PurchaseRequestRefuse(models.TransientModel):
    _name = 'im.purchase.request.refuse'
    _description = 'Từ chối đề nghị mua hàng'

    request_id = fields.Many2one(
        'im.purchase.request', string="Phiếu đề nghị", required=True, ondelete='cascade')
    reason = fields.Text(string="Lý do từ chối", required=True)

    # Ghi lý do rồi chuyển phiếu sang Từ chối
    def action_confirm(self):
        self.ensure_one()
        self.request_id._apply_refusal(self.reason)
        return {'type': 'ir.actions.act_window_close'}
