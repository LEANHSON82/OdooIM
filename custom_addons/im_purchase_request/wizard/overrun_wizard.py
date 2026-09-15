from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

# Hộp thoại hỏi lý do trước khi cho hóa đơn vượt trần
class PurchaseRequestOverrun(models.TransientModel):
    _name = 'im.purchase.request.overrun'
    _description = 'Duyệt hóa đơn vượt dự toán'

    request_id = fields.Many2one(
        'im.purchase.request', string="Phiếu đề nghị", required=True, ondelete='cascade')
    detail = fields.Text(string="Chênh lệch", compute='_compute_detail')
    reason = fields.Text(string="Lý do duyệt vượt", required=True)

    # Hiện chênh lệch của từng hóa đơn vượt trần
    @api.depends('request_id')
    def _compute_detail(self):
        for wizard in self:
            wizard.detail = wizard.request_id.overrun_detail or self.env._(
                "Phiếu này không có hóa đơn nào vượt dự toán.")

    # Ghi lý do và người duyệt lên các hóa đơn vượt
    def action_confirm(self):
        self.ensure_one()
        request = self.request_id
        moves = request._pending_overrun_moves()
        if not moves:
            raise UserError(self.env._(
                "Phiếu này không có hóa đơn nào vượt dự toán cần duyệt."))
        for move in moves:
            error = request._overrun_approver_error(request._invoiced_total_with(move))
            if error:
                raise AccessError(error)
        moves.write({
            'im_overrun_reason': self.reason,
            'im_overrun_user_id': self.env.user.id,
        })
        request.message_post(body=self.env._(
            "%(user)s duyệt cho hóa đơn %(moves)s vượt dự toán. Lý do: %(reason)s",
            user=self.env.user.display_name,
            moves=", ".join(moves.mapped(lambda move: move.name or move.ref or '/')),
            reason=self.reason))
        return {'type': 'ir.actions.act_window_close'}
