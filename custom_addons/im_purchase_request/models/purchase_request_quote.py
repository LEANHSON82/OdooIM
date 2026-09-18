from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Buying channel: official, parallel import, OEM
ORIGIN_TYPES = [
    ('original', "Chính hãng / đại lý"),
    ('imported', "Xách tay"),
    ('oem', "OEM"),
    ('other', "Khác"),
]

# New, refurbished or used goods
CONDITIONS = [
    ('new', "Mới"),
    ('refurbished', "Tân trang"),
    ('used', "Hàng cũ"),
]

# One vendor quote for a request line
class PurchaseRequestQuote(models.Model):
    _name = 'im.purchase.request.quote'
    _description = 'Nguồn mua của đề nghị mua hàng'
    _order = 'line_id, price_unit, id'
    _rec_name = 'partner_id'

    line_id = fields.Many2one(
        'im.purchase.request.line', string="Dòng hàng",
        required=True, ondelete='cascade', index=True)
    request_id = fields.Many2one(
        related='line_id.request_id', string="Phiếu đề nghị", store=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string="Nhà cung cấp", required=True, ondelete='restrict')
    price_unit = fields.Float(
        string="Đơn giá", digits='Product Price', required=True)
    origin_type = fields.Selection(
        ORIGIN_TYPES, string="Nguồn gốc",
        help="Mua qua kênh nào.\n"
             "• Chính hãng / đại lý: mua của hãng hoặc đại lý ủy quyền, "
             "bảo hành hãng.\n"
             "• Xách tay: hàng thật nhưng nhập không chính thức, "
             "người bán tự bảo hành.\n"
             "• OEM: cùng nhà máy nhưng không mang thương hiệu bán lẻ.")
    condition = fields.Selection(
        CONDITIONS, string="Tình trạng", default='new', required=True,
        help="Hàng mới hay hàng cũ.\n"
             "• Tân trang: đã thay linh kiện và có bảo hành.\n"
             "• Hàng cũ: đã qua tay người dùng, thường không còn bảo hành. "
             "Con số “như mới 99%” là lời tự khai của người bán, "
             "ghi ở ô Ghi chú chất lượng chứ đừng tin vào nhãn.")
    warranty_months = fields.Integer(
        string="Bảo hành (tháng)",
        help="Số tháng bảo hành. Để 0 nếu mặt hàng không bảo hành.")
    quality_note = fields.Char(
        string="Ghi chú chất lượng",
        help="Phần chất lượng không quy ra số được: cấu hình, tiêu chuẩn, đời máy.")
    payment_term_id = fields.Many2one(
        'account.payment.term', string="Điều khoản thanh toán",
        compute='_compute_payment_term_id', store=True, readonly=False,
        help="Trả ngay hay công nợ mấy ngày. "
             "Tự lấy theo hồ sơ nhà cung cấp, sửa lại được.")
    note = fields.Char(string="Ghi chú")
    attachment_ids = fields.Many2many(
        'ir.attachment', string="File báo giá")
    is_selected = fields.Boolean(
        string="Chọn", help="Nguồn sẽ đặt hàng. Mỗi dòng chọn một.")
    is_chosen = fields.Boolean(
        string="Đã chọn", compute='_compute_is_chosen',
        help="Nguồn sẽ đặt hàng: nguồn bật Chọn, hoặc nguồn duy nhất của dòng.")
    is_cheapest = fields.Boolean(
        string="Rẻ nhất", compute='_compute_price_comparison',
        help="Chọn nguồn không rẻ nhất thì phải ghi lý do.")
    price_diff = fields.Monetary(
        string="Đắt hơn rẻ nhất", compute='_compute_price_comparison',
        currency_field='currency_id',
        help="Đơn giá này hơn đơn giá của nguồn rẻ nhất bao nhiêu.")
    price_diff_pct = fields.Float(
        string="Chênh %", compute='_compute_price_comparison', digits=(5, 1))

    currency_id = fields.Many2one(related='line_id.currency_id')
    company_id = fields.Many2one(related='line_id.company_id', store=True)

    # Marks the quote that will be ordered
    @api.depends('line_id.selected_quote_id')
    def _compute_is_chosen(self):
        for quote in self:
            quote.is_chosen = quote.line_id.selected_quote_id == quote

    # Taken from the vendor record, and stays editable
    @api.depends('partner_id')
    def _compute_payment_term_id(self):
        for quote in self:
            quote.payment_term_id = (
                quote.payment_term_id
                or quote.partner_id.property_supplier_payment_term_id)

    # Compare with the cheapest quote on the same line
    @api.depends('price_unit', 'line_id.quote_ids.price_unit')
    def _compute_price_comparison(self):
        for line, quotes in self.grouped('line_id').items():
            prices = line.quote_ids.mapped('price_unit')
            cheapest = min(prices) if prices else 0.0
            for quote in quotes:
                quote.is_cheapest = bool(prices) and quote.price_unit <= cheapest
                quote.price_diff = quote.price_unit - cheapest
                quote.price_diff_pct = (
                    quote.price_diff / cheapest * 100.0 if cheapest else 0.0)

    # Only one vendor can be selected per line
    @api.constrains('is_selected', 'line_id')
    def _check_single_selection(self):
        for line in self.line_id:
            if len(line.quote_ids.filtered('is_selected')) > 1:
                raise ValidationError(self.env._(
                    "Dòng “%s” đang chọn nhiều nguồn. Mỗi dòng chỉ chọn một.",
                    line.name))

    # The same vendor cannot be quoted twice on one line
    @api.constrains('partner_id', 'line_id')
    def _check_distinct_vendor(self):
        for line in self.line_id:
            partners = line.quote_ids.mapped('partner_id')
            if len(partners) != len(line.quote_ids):
                raise ValidationError(self.env._(
                    "Dòng “%s” có hai nguồn trùng nhà cung cấp.", line.name))

    # Quotes are frozen once the request is submitted
    def _check_request_editable(self):
        for quote in self:
            if quote.request_id.state != 'draft':
                raise UserError(self.env._(
                    "Phiếu %s đã trình duyệt nên không sửa được nguồn mua.",
                    quote.request_id.name))

    # Adding a source is an edit too, so the same guard applies.
    @api.model_create_multi
    def create(self, vals_list):
        quotes = super().create(vals_list)
        quotes._check_request_editable()
        return quotes

    # Checked before and after, because a quote can move to another request.
    def write(self, vals):
        self._check_request_editable()
        res = super().write(vals)
        self._check_request_editable()
        return res

    # Same guard when a source is removed.
    def unlink(self):
        self._check_request_editable()
        return super().unlink()
