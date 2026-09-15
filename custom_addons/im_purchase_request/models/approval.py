from odoo import fields, models

# Một dòng lịch sử duyệt: cấp nào, ai ký, kết quả ra sao
class PurchaseRequestApproval(models.Model):
    _name = 'im.purchase.request.approval'
    _description = 'Lịch sử duyệt đề nghị mua hàng'
    _order = 'request_id, sequence, id'

    request_id = fields.Many2one(
        'im.purchase.request', string="Phiếu đề nghị",
        required=True, ondelete='cascade', index=True)
    level_id = fields.Many2one(
        'im.purchase.request.approval.level', string="Cấp duyệt",
        required=True, ondelete='restrict')
    sequence = fields.Integer(string="Thứ tự", default=10)
    state = fields.Selection(
        [('pending', "Chờ ký"),
         ('approved', "Đã duyệt"),
         ('refused', "Từ chối")],
        string="Kết quả", default='pending', required=True)
    user_id = fields.Many2one('res.users', string="Người duyệt", readonly=True)
    date = fields.Datetime(string="Thời điểm", readonly=True)
    note = fields.Char(string="Ghi chú / lý do")
    is_self_approved = fields.Boolean(
        string="Tự duyệt", readonly=True,
        help="Người đề nghị cũng là người duy nhất ký được cấp này.")
    company_id = fields.Many2one(related='request_id.company_id', store=True)
