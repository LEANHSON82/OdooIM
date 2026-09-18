from odoo import api, fields, models
from odoo.exceptions import UserError

# Fields locked once the request has been submitted
LOCKED_FIELDS = frozenset({
    'request_id', 'sequence', 'product_id', 'name',
    'product_qty', 'product_uom_id', 'selection_reason',
    'price_unit', 'partner_id',
})

# One item to buy, with its table of vendor quotes
class PurchaseRequestLine(models.Model):
    _name = 'im.purchase.request.line'
    _description = 'Dòng hàng đề nghị mua hàng'
    _order = 'request_id, sequence, id'

    request_id = fields.Many2one(
        'im.purchase.request', string="Phiếu đề nghị",
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        'product.product', string="Sản phẩm",
        domain=[('purchase_ok', '=', True)], required=True, ondelete='restrict')
    name = fields.Char(
        string="Mô tả", compute='_compute_from_product',
        store=True, readonly=False, required=True, precompute=True)
    product_qty = fields.Float(
        string="Số lượng", digits='Product Unit', default=1.0, required=True)
    product_uom_id = fields.Many2one(
        'uom.uom', string="Đơn vị", compute='_compute_from_product',
        store=True, readonly=False, required=True, precompute=True, ondelete='restrict')
    price_unit = fields.Float(
        string="Đơn giá dự toán", digits='Product Price',
        compute='_compute_price_vendor', store=True, readonly=False,
        help="Lấy theo nhà cung cấp đã chọn bên dưới; chỉ nhập thẳng khi thiết lập "
             "không bắt buộc báo giá.")
    price_subtotal = fields.Monetary(
        string="Thành tiền", compute='_compute_price_subtotal',
        store=True, currency_field='currency_id')
    quote_ids = fields.One2many(
        'im.purchase.request.quote', 'line_id', string="Nguồn mua", copy=True)
    quote_count = fields.Integer(string="Số NCC", compute='_compute_quote_summary', store=True)
    selected_quote_id = fields.Many2one(
        'im.purchase.request.quote', string="Nguồn đã chọn",
        compute='_compute_quote_summary', store=True)
    required_quote_count = fields.Integer(
        string="Số nhà cung cấp tối thiểu", compute='_compute_required_quote_count')
    extra_cost = fields.Monetary(
        string="Đắt hơn nguồn rẻ nhất", compute='_compute_extra_cost',
        store=True, currency_field='currency_id',
        help="Phần trả thêm vì không chọn nguồn rẻ nhất, đã nhân số lượng.")
    selection_reason = fields.Char(
        string="Lý do chọn",
        help="Bắt buộc khi không chọn nguồn rẻ nhất.")
    partner_id = fields.Many2one(
        'res.partner', string="NCC gợi ý",
        compute='_compute_price_vendor', store=True, readonly=False,
        help="Đơn mua gộp theo ô này. Lấy theo nhà cung cấp đã chọn bên dưới; chỉ "
             "nhập thẳng khi thiết lập không bắt buộc báo giá.")
    purchase_line_id = fields.Many2one(
        'purchase.order.line', string="Dòng đơn mua", readonly=True, ondelete='set null',
        copy=False)

    currency_id = fields.Many2one(related='request_id.currency_id')
    company_id = fields.Many2one(related='request_id.company_id', store=True)

    # Description and unit follow the product, and stay editable
    @api.depends('product_id')
    def _compute_from_product(self):
        for line in self:
            if not line.product_id:
                line.name = line.name or False
                line.product_uom_id = line.product_uom_id or False
                continue
            line.name = line.product_id.display_name
            line.product_uom_id = line.product_id.uom_id

    # A single vendor counts as already selected
    @api.depends('quote_ids', 'quote_ids.is_selected')
    def _compute_quote_summary(self):
        for line in self:
            quotes = line.quote_ids
            line.quote_count = len(quotes)
            chosen = quotes.filtered('is_selected')[:1]
            line.selected_quote_id = chosen or (quotes if len(quotes) == 1 else quotes.browse())

    # Minimum number of vendors, read from the settings
    @api.depends('request_id.company_id', 'product_qty', 'price_unit',
                 'quote_ids.price_unit', 'selected_quote_id')
    def _compute_required_quote_count(self):
        Config = self.env['im.purchase.request.config']
        for line in self:
            company = line.request_id.company_id or self.env.company
            config = Config._for_company(company)
            line.required_quote_count = config._min_quote_count_for(line._quote_basis_amount())

    # Subtotal decides which minimum-vendor band applies
    def _quote_basis_amount(self):
        self.ensure_one()
        if self.selected_quote_id:
            price = self.selected_quote_id.price_unit
        elif self.quote_ids:
            price = min(self.quote_ids.mapped('price_unit'))
        else:
            price = self.price_unit
        return self.product_qty * price

    # Selecting a vendor pulls that vendor's price
    @api.depends('selected_quote_id.partner_id', 'selected_quote_id.price_unit')
    def _compute_price_vendor(self):
        for line in self:
            chosen = line.selected_quote_id
            if not chosen:
                continue
            line.partner_id = chosen.partner_id
            line.price_unit = chosen.price_unit

    # Extra cost compared with the cheapest vendor
    @api.depends('product_qty', 'selected_quote_id.price_unit',
                 'quote_ids.price_unit')
    def _compute_extra_cost(self):
        for line in self:
            prices = line.quote_ids.mapped('price_unit')
            chosen = line.selected_quote_id
            if not chosen or not prices:
                line.extra_cost = 0.0
                continue
            line.extra_cost = (chosen.price_unit - min(prices)) * line.product_qty

    # Subtotal is quantity times unit price
    @api.depends('product_qty', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.product_qty * line.price_unit

    # Quotes missing an origin or payment terms
    def _missing_comparison_data(self):
        self.ensure_one()
        problems = []
        for quote in self.quote_ids:
            missing = []
            if not quote.origin_type:
                missing.append(self.env._("xuất xứ"))
            if not quote.payment_term_id:
                missing.append(self.env._("điều khoản thanh toán"))
            if missing:
                problems.append(self.env._(
                    "• %(line)s / %(vendor)s: thiếu %(missing)s",
                    line=self.name, vendor=quote.partner_id.display_name,
                    missing=", ".join(missing)))
        return problems

    # Lines are frozen once the request is submitted
    def _check_request_editable(self):
        for line in self:
            if line.request_id.state != 'draft':
                raise UserError(self.env._(
                    "Phiếu %s đã trình duyệt nên không sửa được dòng hàng.",
                    line.request_id.name))

    # Adding a line is an edit too, so the same guard applies.
    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_request_editable()
        return lines

    # Check before and after, because a line can move to another request
    def write(self, vals):
        if LOCKED_FIELDS.intersection(vals):
            self._check_request_editable()
            res = super().write(vals)
            self._check_request_editable()
            return res
        return super().write(vals)

    # Same guard when a line is removed.
    def unlink(self):
        self._check_request_editable()
        return super().unlink()
