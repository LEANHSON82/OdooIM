from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools import float_compare

# Các trường khóa lại khi phiếu rời trạng thái Nháp
LOCKED_FIELDS = frozenset({
    'requester_id', 'department_id', 'name', 'date_request',
    'date_required', 'company_id', 'note',
})

# Hóa đơn mua và hóa đơn hoàn của nhà cung cấp
VENDOR_BILL_TYPES = ('in_invoice', 'in_refund')

# Vòng đời phiếu: nháp, chờ duyệt, đã duyệt, tạo đơn mua
STATES = [
    ('draft', "Nháp"),
    ('to_approve', "Chờ duyệt"),
    ('approved', "Đã duyệt"),
    ('refused', "Từ chối"),
    ('po_created', "Đã tạo đơn mua"),
]

# Phiếu đề nghị mua hàng, ký nhiều cấp trước khi ra đơn mua
class PurchaseRequest(models.Model):
    _name = 'im.purchase.request'
    _description = 'Đề nghị mua hàng'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_request desc, id desc'
    _mail_post_access = 'read'

    name = fields.Char(
        string="Số phiếu", default='/', copy=False, readonly=True, index='trigram')
    requester_id = fields.Many2one(
        'res.users', string="Người đề nghị", required=True, tracking=True, readonly=True,
        default=lambda self: self.env.user, ondelete='restrict')
    department_id = fields.Many2one(
        'hr.department', string="Bộ phận", tracking=True, ondelete='restrict',
        compute='_compute_department_id', store=True, precompute=True,
        help="Lấy theo hồ sơ nhân viên của người đề nghị, quyết định ai ký cấp theo phòng.")
    date_request = fields.Date(
        string="Ngày đề nghị", default=fields.Date.context_today, required=True,
        copy=False)
    date_required = fields.Date(string="Ngày cần hàng")
    note = fields.Text(string="Lý do đề nghị")

    company_id = fields.Many2one(
        'res.company', string="Công ty", required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string="Tiền tệ")

    state = fields.Selection(
        STATES, string="Trạng thái", default='draft', required=True,
        copy=False, tracking=True, index=True)
    active = fields.Boolean(
        string="Đang dùng", default=True,
        help="Bỏ đánh dấu để lưu trữ. Phiếu đã ký chỉ lưu trữ, không xoá.")

    line_ids = fields.One2many(
        'im.purchase.request.line', 'request_id', string="Dòng hàng", copy=True)
    amount_total = fields.Monetary(
        string="Tổng dự toán", compute='_compute_amount_total',
        store=True, tracking=True, currency_field='currency_id')

    quote_ids = fields.One2many(
        'im.purchase.request.quote', 'request_id',
        string="Bảng so sánh nguồn mua", readonly=True,
        help="Mọi nguồn mua của phiếu gom về một chỗ để cấp duyệt kiểm tra.")

    extra_cost_total = fields.Monetary(
        string="Đắt hơn phương án rẻ nhất", compute='_compute_extra_cost_total',
        store=True, currency_field='currency_id',
        help="Cộng phần trả thêm của mọi dòng hàng vì không chọn nguồn rẻ nhất.")

    approval_ids = fields.One2many(
        'im.purchase.request.approval', 'request_id', string="Lịch sử duyệt", copy=False)
    refuse_reason = fields.Text(string="Lý do từ chối", readonly=True, copy=False)

    purchase_order_ids = fields.One2many(
        'purchase.order', 'im_request_id', string="Đơn mua", readonly=True, copy=False)
    purchase_order_count = fields.Integer(compute='_compute_purchase_order_count')

    invoice_count = fields.Integer(string="Số hóa đơn", compute='_compute_invoice')
    amount_invoiced = fields.Monetary(
        string="Đã xuất hóa đơn", compute='_compute_invoice',
        currency_field='currency_id',
        help="Phần tiền của phiếu này trong các hóa đơn đã vào sổ, "
             "đã trừ hóa đơn hoàn.")
    invoice_status = fields.Selection(
        [('no', "Chưa tới lượt"),
         ('to invoice', "Chờ hóa đơn"),
         ('invoiced', "Đã có hóa đơn")],
        string="Tình trạng hóa đơn", compute='_compute_invoice')
    payment_state = fields.Selection(
        [('no', "Chưa có hóa đơn"),
         ('not_paid', "Chưa thanh toán"),
         ('partial', "Thanh toán một phần"),
         ('paid', "Đã thanh toán")],
        string="Tình trạng thanh toán", compute='_compute_invoice')
    required_level_count = fields.Integer(
        string="Số cấp cần duyệt", compute='_compute_required_level_count')
    is_my_turn = fields.Boolean(
        string="Đến lượt tôi duyệt", compute='_compute_is_my_turn',
        search='_search_is_my_turn',
        help="Phiếu này có đang chờ chính bạn ký không.")
    is_requester = fields.Boolean(compute='_compute_user_permissions')
    can_create_purchase_orders = fields.Boolean(compute='_compute_user_permissions')
    can_approve_overrun = fields.Boolean(compute='_compute_user_permissions')
    overrun_pending = fields.Boolean(
        string="Có hóa đơn vượt dự toán chờ duyệt", compute='_compute_overrun_pending')
    overrun_detail = fields.Text(compute='_compute_overrun_pending')

    # Bộ phận lấy từ hồ sơ nhân viên của người đề nghị
    @api.depends('requester_id', 'company_id')
    def _compute_department_id(self):
        for request in self:
            request.department_id = request._requester_department()

    # Dùng sudo vì nhân viên thường không đọc được hồ sơ người khác
    def _requester_department(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        employee = self.requester_id.sudo().with_company(company).employee_id
        return employee.department_id.sudo(False)

    # Tổng dự toán bằng tổng thành tiền các dòng hàng
    @api.depends('line_ids.price_subtotal')
    def _compute_amount_total(self):
        for request in self:
            request.amount_total = sum(request.line_ids.mapped('price_subtotal'))

    # Tổng tiền trả thêm vì không chọn nguồn rẻ nhất
    @api.depends('line_ids.extra_cost')
    def _compute_extra_cost_total(self):
        for request in self:
            request.extra_cost_total = sum(request.line_ids.mapped('extra_cost'))

    # Dùng sudo vì người đề nghị không có quyền xem đơn mua
    @api.depends('purchase_order_ids')
    def _compute_purchase_order_count(self):
        for request in self.sudo():
            request.purchase_order_count = len(request.purchase_order_ids)

    # Số hóa đơn, tiền đã xuất, tình trạng hóa đơn và thanh toán
    @api.depends('purchase_order_ids.invoice_ids.state',
                 'purchase_order_ids.invoice_ids.payment_state',
                 'purchase_order_ids.invoice_status')
    def _compute_invoice(self):
        for request in self:
            orders = request.sudo().purchase_order_ids
            moves = orders.invoice_ids
            posted = moves.filtered(lambda move: move.state == 'posted')
            request.invoice_count = len(moves)
            request.amount_invoiced = request._invoiced_total(posted)
            request.invoice_status = request._aggregate_invoice_status(orders)
            request.payment_state = request._aggregate_payment_state(posted)

    # Gộp tình trạng hóa đơn của nhiều đơn mua thành một
    def _aggregate_invoice_status(self, orders):
        statuses = set(orders.mapped('invoice_status'))
        if 'to invoice' in statuses:
            return 'to invoice'
        if statuses == {'invoiced'}:
            return 'invoiced'
        return 'no'

    # Gộp tình trạng thanh toán của các hóa đơn đã vào sổ
    def _aggregate_payment_state(self, posted_moves):
        if not posted_moves:
            return 'no'
        states = set(posted_moves.mapped('payment_state'))
        if states <= {'paid', 'reversed'}:
            return 'paid'
        if states & {'paid', 'partial', 'in_payment', 'reversed'}:
            return 'partial'
        return 'not_paid'

    # Chỉ cộng dòng hóa đơn thuộc đơn mua của phiếu này
    def _invoiced_total(self, moves):
        self.ensure_one()
        order_lines = self.sudo().purchase_order_ids.order_line
        return sum(
            line.balance
            for line in moves.sudo().invoice_line_ids
            if line.purchase_line_id in order_lines)

    # Phần trăm cho phép vượt, lấy từ thiết lập
    def _overrun_tolerance(self):
        self.ensure_one()
        return self._config().overrun_tolerance_pct

    # Trần chi: tổng đã duyệt cộng phần trăm cho phép vượt
    def _overrun_ceiling(self):
        self.ensure_one()
        return self.amount_total * (1.0 + self._overrun_tolerance() / 100.0)

    # Tổng đã xuất nếu tính thêm hóa đơn này
    def _invoiced_total_with(self, move):
        self.ensure_one()
        others = self.sudo().purchase_order_ids.invoice_ids.filtered(
            lambda other: other.state == 'posted' and other != move)
        return self._invoiced_total(others) + self._invoiced_total(move)

    # Câu lỗi khi hóa đơn này làm phiếu vượt trần
    def _invoice_ceiling_error(self, move):
        self.ensure_one()
        total = self._invoiced_total_with(move)
        ceiling = self._overrun_ceiling()
        currency = self.currency_id
        if float_compare(total, ceiling, precision_rounding=currency.rounding) <= 0:
            return None
        return self.env._(
            "Hóa đơn này đưa tổng đã xuất của phiếu %(name)s lên %(total)s, "
            "vượt trần %(ceiling)s (đã duyệt %(approved)s, cho phép vượt "
            "%(pct)s%%).\n"
            "Cần %(approver)s bấm “Duyệt vượt dự toán” trên phiếu %(name)s.",
            name=self.name,
            total=currency.format(total),
            ceiling=currency.format(ceiling),
            approved=currency.format(self.amount_total),
            pct=self._overrun_tolerance(),
            approver=self._overrun_approver_label(total))

    # Hóa đơn nháp đang bị chặn vì vượt trần
    def _pending_overrun_moves(self):
        self.ensure_one()
        return self.sudo().purchase_order_ids.invoice_ids.filtered(
            lambda move: move.state == 'draft'
            and move.move_type in VENDOR_BILL_TYPES
            and not move.im_overrun_reason
            and self._invoice_ceiling_error(move))

    # Thiết lập của công ty, chưa có thì tạo mới
    def _config(self):
        self.ensure_one()
        return self.env['im.purchase.request.config']._for_company(self.company_id)

    # Các dòng quyền có dải chứa số tiền này
    def _permission_rules(self, permission_type, amount):
        self.ensure_one()
        config = self._config()
        rules = (config.po_creator_rule_ids if permission_type == 'po_creator'
                 else config.overrun_rule_ids)
        rounding = self.currency_id.rounding
        return rules.filtered(lambda rule: rule._applies_to(amount, rounding))

    # Trả None nếu được phép, ngược lại trả câu lỗi
    def _permission_error(self, permission_type, amount, action_label):
        self.ensure_one()
        rules = self._permission_rules(permission_type, amount)
        if not rules:
            return self.env._(
                "Chưa cấu hình ai được %(action)s cho số tiền %(amount)s. "
                "Nhờ người có quyền cấu hình thêm dòng ở Đề nghị mua hàng / Cấu hình / Thiết lập.",
                action=action_label, amount=self.currency_id.format(amount))
        if any(rule._allows(self.env.user) for rule in rules):
            return None
        return self.env._(
            "Với số tiền %(amount)s, chỉ %(who)s mới %(action)s.",
            amount=self.currency_id.format(amount), action=action_label,
            who="; ".join(rule._describe() for rule in rules))

    # Tên người được duyệt vượt, để ghi vào câu lỗi
    def _overrun_approver_label(self, amount):
        self.ensure_one()
        if self._config().overrun_approval_mode == 'all':
            return self.env._("người mở được phiếu")
        rules = self._permission_rules('overrun', amount)
        if not rules:
            return self.env._("người được cấu hình duyệt vượt dự toán")
        return "; ".join(rule._describe() for rule in rules)

    # Không ai được tự duyệt vượt cho phiếu của mình
    def _overrun_approver_error(self, amount):
        self.ensure_one()
        if self._config().overrun_approval_mode == 'all':
            return None
        if self.env.user in (self.requester_id | self.create_uid):
            return self.env._("Không tự duyệt vượt dự toán cho phiếu của mình.")
        return self._permission_error('overrun', amount, self.env._("duyệt vượt dự toán"))

    # Kiểm tra quyền bấm nút Tạo đơn mua
    def _po_creator_error(self):
        self.ensure_one()
        if self.env.su or self._config().po_creator_mode == 'all':
            return None
        return self._permission_error(
            'po_creator', self.amount_total, self.env._("tạo đơn mua"))

    # Quyết định ẩn hiện các nút trên form
    @api.depends_context('uid')
    @api.depends('state', 'company_id', 'requester_id')
    def _compute_user_permissions(self):
        for request in self:
            request.is_requester = request.requester_id == request.env.user
            request.can_create_purchase_orders = (
                request.state == 'approved' and not request._po_creator_error())
            moves = request._pending_overrun_moves() if request.state == 'po_created' else []
            request.can_approve_overrun = any(
                not request._overrun_approver_error(request._invoiced_total_with(move))
                for move in moves)

    # Cảnh báo đỏ trên phiếu khi có hóa đơn vượt trần
    def _compute_overrun_pending(self):
        for request in self:
            moves = request._pending_overrun_moves() if request.state == 'po_created' else []
            request.overrun_pending = bool(moves)
            request.overrun_detail = "\n\n".join(
                "%s: %s" % (move.name or move.ref or '/', request._invoice_ceiling_error(move))
                for move in moves) or False

    # Hủy hết đơn mua thì phiếu quay lại Đã duyệt
    def _reopen_if_orders_cancelled(self):
        for request in self:
            if request.state != 'po_created':
                continue
            orders = request.sudo().purchase_order_ids
            if orders and all(order.state == 'cancel' for order in orders):
                request.state = 'approved'
                request.message_post(body=request.env._(
                    "Mọi đơn mua đã bị hủy, phiếu mở lại để tạo đơn khác."))

    # Đếm số cấp phải ký, gom cấp theo công ty cho nhanh
    @api.depends('amount_total', 'requester_id', 'department_id')
    def _compute_required_level_count(self):
        levels_by_company = {}
        for request in self:
            company_id = request.company_id.id
            if company_id not in levels_by_company:
                levels_by_company[company_id] = request._get_levels()
            request.required_level_count = len(
                request._build_approval_chain(levels_by_company[company_id]))

    # Phiếu có đang chờ chính người đang xem ký không
    @api.depends_context('uid')
    @api.depends('state', 'approval_ids.state')
    def _compute_is_my_turn(self):
        for request in self:
            approval = request._current_approval()
            request.is_my_turn = bool(
                request.state == 'to_approve' and approval
                and not request._approver_error(approval))

    # Cho lọc “Chờ tôi duyệt” trên danh sách
    def _search_is_my_turn(self, operator, value):
        if operator != 'in':
            return NotImplemented
        waiting = self.search([('state', '=', 'to_approve')]).filtered('is_my_turn')
        return [('id', 'in' if True in value else 'not in', waiting.ids)]

    # Tham số hệ thống: có cho tự duyệt phiếu của mình không
    def _allow_self_approval(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'im_purchase_request.allow_self_approval') in ('1', 'True', 'true')

    # Người đề nghị là người duy nhất ký được cấp này
    def _requester_is_approver(self, level):
        self.ensure_one()
        approvers = self._level_approver_users(level)
        return bool(approvers) and approvers == self.requester_id

    # Cấp duyệt của công ty phiếu, kèm cấp dùng chung
    def _get_levels(self):
        return self.env['im.purchase.request.approval.level'].search([
            ('company_id', 'in', [False, self.company_id.id]),
        ])

    # Các cấp phải ký với số tiền này, theo thứ tự
    def _build_approval_chain(self, levels=None, amount=None):
        self.ensure_one()
        levels = self._get_levels() if levels is None else levels
        amount = self.amount_total if amount is None else amount
        rounding = self.currency_id.rounding
        return levels.filtered(lambda level: level._applies_to(amount, rounding))

    # Cấp đang chờ ký, tức dòng chờ đầu tiên
    def _current_approval(self):
        self.ensure_one()
        pending = self.approval_ids.filtered(lambda a: a.state == 'pending')
        return pending.sorted('sequence')[:1]

    # Ai ký được cấp này: thành viên nhóm, lọc theo phòng nếu cần
    def _level_approver_users(self, level):
        self.ensure_one()
        members = self.env['res.users'].sudo().search([
            ('all_group_ids', 'in', level.group_id.ids),
            ('active', '=', True),
        ])
        manager = self.department_id.manager_id.user_id
        if level.scope == 'department' and manager:
            return manager & members
        return members

    # Liệt kê cấp chưa có ai ký được, nêu tên cụ thể
    def _missing_approver_errors(self, levels):
        self.ensure_one()
        problems = []
        manager = self.department_id.manager_id.user_id
        for level in levels:
            if self._level_approver_users(level):
                continue
            if level.scope == 'department' and manager:
                problems.append(self.env._(
                    "• %(level)s: trưởng bộ phận %(dept)s là %(user)s nhưng chưa thuộc nhóm %(group)s",
                    level=level.name, dept=self.department_id.display_name,
                    user=manager.display_name, group=level.group_id.display_name))
            else:
                problems.append(self.env._(
                    "• %(level)s: nhóm %(group)s chưa có ai",
                    level=level.name, group=level.group_id.display_name))
        return problems

    # Trả None nếu người đang xem ký được cấp này
    def _approver_error(self, approval):
        self.ensure_one()
        user = self.env.user
        level = approval.level_id

        if level.group_id not in user.all_group_ids:
            return self.env._(
                "Cấp duyệt “%(level)s” chỉ dành cho nhóm %(group)s.",
                level=level.name, group=level.group_id.display_name)

        if level.scope == 'department':
            manager = self.department_id.manager_id.user_id
            if manager and user != manager:
                return self.env._(
                    "Cấp duyệt “%(level)s” dành cho trưởng bộ phận %(dept)s.",
                    level=level.name, dept=self.department_id.display_name)

        is_own = user in (self.requester_id | self.create_uid)
        sole_approver = user == self.requester_id and approval.is_self_approved
        if is_own and not sole_approver and not self._allow_self_approval():
            return self.env._(
                "Không tự duyệt phiếu của mình. Nhờ người khác trong nhóm %s ký.",
                level.group_id.display_name)

        return None

    # Giao việc cần làm cho người ký cấp tiếp theo
    def _activity_next_approver(self):
        self.ensure_one()
        approval = self._current_approval()
        if not approval:
            return
        level = approval.level_id
        users = self._level_approver_users(level)
        for user in users:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                summary=self.env._("Duyệt %(name)s — %(level)s",
                                   name=self.name, level=level.name),
                user_id=user.id)
        if not users:
            self.message_post(body=self.env._(
                "Chờ %(level)s ký, nhưng nhóm %(group)s chưa có ai.",
                level=level.name, group=level.group_id.display_name))

    # Nút Trình duyệt: kiểm tra đủ điều kiện rồi dựng chuỗi ký
    def action_submit(self):
        for request in self:
            request._check_is_requester()
            if request.state != 'draft':
                raise UserError(request.env._("Chỉ phiếu Nháp mới trình duyệt được."))
            if not request.line_ids:
                raise UserError(request.env._(
                    "Thêm ít nhất một dòng hàng."))
            if request.currency_id.is_zero(request.amount_total):
                raise UserError(request.env._(
                    "Tổng dự toán bằng 0."))

            request._check_sources_compared()
            request._check_lines_complete()

            # Bộ phận có thể đã đổi bên nhân sự từ lúc lập nháp
            department = request._requester_department()
            if request.department_id != department:
                request.department_id = department

            all_levels = request._get_levels()
            levels = request._build_approval_chain(all_levels)
            if not levels:
                raise UserError(request._no_level_error(all_levels))
            request._check_department_known(levels)
            problems = request._missing_approver_errors(levels)
            if problems:
                raise UserError(request.env._(
                    "Chưa có người ký được các cấp sau:\n%s\n"
                    "Nhờ quản trị tick “Là người duyệt” cho đúng người rồi trình lại.",
                    "\n".join(problems)))

            # Xóa chuỗi cũ rồi dựng lại, mỗi cấp một dòng chờ ký
            request.approval_ids.sudo().unlink()
            self.env['im.purchase.request.approval'].sudo().create([
                {
                    'request_id': request.id,
                    'level_id': level.id,
                    'sequence': level.sequence,
                    'is_self_approved': request._requester_is_approver(level),
                }
                for level in levels
            ])
            request.write({'state': 'to_approve', 'refuse_reason': False})
            request.message_post(body=request.env._(
                "Đã trình duyệt, cần %(count)s cấp ký: %(levels)s.",
                count=len(levels), levels=", ".join(levels.mapped('name'))))
            request._activity_next_approver()
        return True

    # Chỉ người đề nghị mới thao tác được trên phiếu
    def _check_is_requester(self):
        self.ensure_one()
        if not self.env.su and self.env.user != self.requester_id:
            raise UserError(self.env._(
                "Chỉ người đề nghị (%s) mới làm được thao tác này trên phiếu.",
                self.requester_id.display_name))

    # Câu lỗi khi số tiền không rơi vào cấp duyệt nào
    def _no_level_error(self, all_levels):
        self.ensure_one()
        if all_levels:
            return self.env._(
                "Tổng dự toán %(total)s không nằm trong dải của cấp duyệt nào "
                "(ngưỡng “Từ” thấp nhất là %(lowest)s) nên chưa có ai phải ký. "
                "Sửa dải ở Đề nghị mua hàng / Cấu hình / Thiết lập.",
                total=self.currency_id.format(self.amount_total),
                lowest=self.currency_id.format(
                    min(all_levels.mapped('amount_threshold'))))
        return self.env._(
            "Chưa cấu hình cấp duyệt nào cho công ty này. "
            "Thêm ở Đề nghị mua hàng / Cấu hình / Thiết lập.")

    # Có cấp theo phòng thì phiếu phải biết bộ phận
    def _check_department_known(self, levels):
        self.ensure_one()
        by_dept = levels.filtered(lambda level: level.scope == 'department')
        if by_dept and not self.department_id:
            raise UserError(self.env._(
                "%(user)s chưa có bộ phận trong hồ sơ nhân viên nên không biết ai ký "
                "cấp %(levels)s. Nhờ nhân sự cập nhật bộ phận rồi trình lại.",
                user=self.requester_id.display_name,
                levels=", ".join(by_dept.mapped('name'))))

    # Mỗi dòng phải có đơn giá và nhà cung cấp gợi ý
    def _check_lines_complete(self):
        self.ensure_one()
        problems = []
        for line in self.line_ids:
            missing = []
            if line.price_unit <= 0:
                missing.append(self.env._("đơn giá dự toán"))
            if not line.partner_id:
                missing.append(self.env._("NCC gợi ý"))
            if missing:
                problems.append(self.env._(
                    "• %(name)s: thiếu %(missing)s",
                    name=line.name, missing=", ".join(missing)))
        if problems:
            raise UserError(self.env._(
                "Dòng hàng chưa đủ thông tin:\n%s", "\n".join(problems)))

    # Đủ nhà cung cấp, đã chọn một, có lý do nếu không rẻ nhất
    def _check_sources_compared(self):
        self.ensure_one()
        problems = []
        for line in self.line_ids:
            minimum = line.required_quote_count
            if not minimum and not line.quote_ids:
                continue
            if line.quote_count < minimum:
                problems.append(self.env._(
                    "• %(name)s: mới %(got)s nhà cung cấp, cần ít nhất %(need)s",
                    name=line.name, got=line.quote_count, need=minimum))
                continue
            elif not line.selected_quote_id:
                problems.append(self.env._(
                    "• %(name)s: có nhiều nhà cung cấp, chưa chọn nhà cung cấp nào",
                    name=line.name))
            elif not line.selected_quote_id.is_cheapest and not line.selection_reason:
                problems.append(self.env._(
                    "• %(name)s: chọn nhà cung cấp không rẻ nhất, cần ghi lý do",
                    name=line.name))
            problems.extend(line._missing_comparison_data())
        if problems:
            raise UserError(self.env._(
                "Thông tin nhà cung cấp chưa đủ:\n%s", "\n".join(problems)))

    # Lấy cấp đang chờ, không ký được thì báo lỗi
    def _pending_approval_for_me(self):
        self.ensure_one()
        approval = self._current_approval()
        if self.state != 'to_approve' or not approval:
            raise UserError(self.env._("Phiếu không ở trạng thái chờ duyệt."))
        error = self._approver_error(approval)
        if error:
            raise AccessError(error)
        return approval

    # Nút Duyệt: ký cấp hiện tại rồi chuyển sang cấp sau
    def action_approve(self):
        for request in self:
            approval = request._pending_approval_for_me()
            approval.sudo().write({
                'state': 'approved',
                'user_id': request.env.user.id,
                'date': fields.Datetime.now(),
            })
            request.sudo().activity_unlink(['mail.mail_activity_data_todo'])
            request.message_post(body=request.env._(
                "%(user)s đã duyệt cấp %(level)s.",
                user=request.env.user.display_name, level=approval.level_id.name))

            if request._current_approval():
                request._activity_next_approver()
            else:
                request.sudo().state = 'approved'
        return True

    # Nút Từ chối: mở hộp thoại hỏi lý do
    def action_refuse(self):
        self._pending_approval_for_me()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Từ chối %s", self.name),
            'res_model': 'im.purchase.request.refuse',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    # Hộp thoại từ chối gọi vào đây để ghi lý do
    def _apply_refusal(self, reason):
        approval = self._pending_approval_for_me()
        approval.sudo().write({
            'state': 'refused',
            'user_id': self.env.user.id,
            'date': fields.Datetime.now(),
            'note': reason,
        })
        self.sudo().write({'state': 'refused', 'refuse_reason': reason})
        self.sudo().activity_unlink(['mail.mail_activity_data_todo'])
        self.message_post(body=self.env._(
            "%(user)s đã từ chối ở cấp %(level)s: %(reason)s",
            user=self.env.user.display_name, level=approval.level_id.name,
            reason=reason))

    # Phiếu bị từ chối quay về Nháp để sửa lại
    def action_reset_to_draft(self):
        for request in self:
            request._check_is_requester()
            if request.state != 'refused':
                raise UserError(request.env._(
                    "Chỉ phiếu bị từ chối mới đưa về Nháp được."))
            request.approval_ids.sudo().unlink()
            request.state = 'draft'
            request.message_post(body=request.env._(
                "Đưa về Nháp, đã xoá chuỗi ký cũ."))
        return True

    # Người đề nghị rút phiếu khi chưa cấp nào ký
    def action_withdraw(self):
        for request in self:
            if request.state != 'to_approve':
                raise UserError(request.env._("Chỉ rút được phiếu đang chờ duyệt."))
            if request.env.user != request.requester_id:
                raise UserError(request.env._("Chỉ người đề nghị mới rút được phiếu."))
            if request.approval_ids.filtered(lambda a: a.state != 'pending'):
                raise UserError(request.env._(
                    "Đã có cấp ký nên không rút được. Nhờ cấp duyệt bấm Từ chối."))
            request.approval_ids.sudo().unlink()
            request.sudo().activity_unlink(['mail.mail_activity_data_todo'])
            request.state = 'draft'
            request.message_post(body=request.env._("Người đề nghị đã rút phiếu."))
        return True

    # Nút Tạo đơn mua: gộp dòng hàng theo nhà cung cấp
    def action_create_purchase_orders(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(self.env._(
                "Chỉ tạo đơn mua khi phiếu đã duyệt đủ cấp."))
        error = self._po_creator_error()
        if error:
            raise AccessError(error)
        if self.sudo().purchase_order_ids.filtered(
                lambda order: order.state != 'cancel'):
            raise UserError(self.env._(
                "Phiếu %s đã tạo đơn mua rồi.", self.name))

        missing = self.line_ids.filtered(lambda line: not line.partner_id)
        if missing:
            raise UserError(self.env._(
                "Các dòng sau chưa có nhà cung cấp nên không gộp được:\n%s\n"
                "Phiếu cũ thiếu dữ liệu nguồn mua, lập phiếu mới thay thế.",
                "\n".join("• " + line.name for line in missing)))

        date_planned = (fields.Datetime.to_datetime(self.date_required)
                        or fields.Datetime.now())
        # Gộp dòng hàng theo nhà cung cấp, mỗi nhà cung cấp một đơn
        lines_by_vendor = self.line_ids.grouped('partner_id')

        orders = self.env['purchase.order'].sudo().create([
            {
                'partner_id': partner.id,
                'currency_id': self.currency_id.id,
                'origin': self.name,
                'im_request_id': self.id,
                'company_id': self.company_id.id,
                'user_id': False,
                'order_line': [
                    Command.create({
                        'product_id': line.product_id.id,
                        'name': line.name,
                        'product_qty': line.product_qty,
                        'product_uom_id': line.product_uom_id.id,
                        'price_unit': line.price_unit,
                        'date_planned': date_planned,
                    })
                    for line in lines
                ],
            }
            for partner, lines in lines_by_vendor.items()
        ])

        # Nối dòng phiếu với dòng đơn để theo dõi hóa đơn sau này
        for lines, order in zip(lines_by_vendor.values(), orders):
            for request_line, order_line in zip(lines, order.order_line):
                request_line.sudo().purchase_line_id = order_line

        self.sudo().state = 'po_created'
        names = ", ".join(orders.mapped('name'))
        self.message_post(body=self.env._(
            "Đã tạo %(count)s đơn mua: %(orders)s", count=len(orders), orders=names))

        # Không có quyền xem đơn mua thì chỉ hiện thông báo
        if self.env['purchase.order'].has_access('read'):
            return self.action_view_purchase_orders()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': self.env._("Đã tạo %s đơn mua", len(orders)),
                'message': self.env._(
                    "%(orders)s — người phụ trách mua hàng đàm phán giá rồi xác nhận.",
                    orders=names),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    # Nút Duyệt vượt dự toán: mở hộp thoại hỏi lý do
    def action_open_overrun_wizard(self):
        self.ensure_one()
        if not self.can_approve_overrun:
            moves = self._pending_overrun_moves()
            error = moves and self._overrun_approver_error(self._invoiced_total_with(moves[0]))
            raise AccessError(error or self.env._(
                "Phiếu này không có hóa đơn nào vượt dự toán cần duyệt."))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Duyệt vượt dự toán %s", self.name),
            'res_model': 'im.purchase.request.overrun',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    # Nút thông minh mở các đơn mua của phiếu
    def action_view_purchase_orders(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': self.env._("Đơn mua từ %s", self.name),
            'res_model': 'purchase.order',
            'domain': [('id', 'in', self.purchase_order_ids.ids)],
            'view_mode': 'list,form',
        }
        if len(self.purchase_order_ids) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.purchase_order_ids.id,
            })
        return action

    # Hóa đơn của mọi đơn mua thuộc phiếu
    def _invoices(self):
        self.ensure_one()
        return self.sudo().purchase_order_ids.invoice_ids

    # Nút thông minh mở các hóa đơn của phiếu
    def action_view_invoices(self):
        self.ensure_one()
        moves = self._invoices()
        action = {
            'type': 'ir.actions.act_window',
            'name': self.env._("Hóa đơn từ %s", self.name),
            'res_model': 'account.move',
            'domain': [('id', 'in', moves.ids)],
            'view_mode': 'list,form',
            'context': {'create': False},
        }
        if len(moves) == 1:
            action.update({'view_mode': 'form', 'res_id': moves.id})
        return action

    # Chặn sửa trạng thái trực tiếp, bắt buộc bấm nút
    def _check_state_transition(self, previous_states):
        for request in self:
            before = previous_states[request.id]
            after = request.state
            if before == after:
                continue
            approvals = request.approval_ids
            reason = None
            if after == 'to_approve':
                if before != 'draft':
                    reason = self.env._("chỉ phiếu Nháp mới trình duyệt được")
                elif not approvals or any(a.state != 'pending' for a in approvals):
                    reason = self.env._("chuỗi duyệt chưa được dựng đúng")
            elif after == 'approved':
                orders = request.sudo().purchase_order_ids
                if before == 'po_created':
                    if not orders or any(o.state != 'cancel' for o in orders):
                        reason = self.env._("còn đơn mua chưa hủy")
                elif before != 'to_approve':
                    reason = self.env._("chỉ phiếu đang chờ duyệt mới thành Đã duyệt")
                elif not approvals or any(a.state != 'approved' for a in approvals):
                    reason = self.env._("còn cấp chưa ký")
            elif after == 'refused':
                if before != 'to_approve':
                    reason = self.env._("chỉ phiếu đang chờ duyệt mới bị từ chối")
                elif not any(a.state == 'refused' for a in approvals):
                    reason = self.env._("chưa cấp nào từ chối")
            elif after == 'draft':
                if before not in ('to_approve', 'refused'):
                    reason = self.env._("không quay về Nháp từ trạng thái này được")
                elif approvals:
                    reason = self.env._("chuỗi duyệt cũ chưa được xoá")
            elif after == 'po_created':
                if before != 'approved':
                    reason = self.env._("chỉ phiếu đã duyệt mới sinh được đơn mua")
                elif not request.sudo().purchase_order_ids:
                    reason = self.env._("chưa có đơn mua nào được sinh ra")
            if reason:
                raise UserError(self.env._(
                    "Không chuyển phiếu %(name)s sang “%(state)s”: %(reason)s. "
                    "Dùng nút trên phiếu.",
                    name=request.name, state=dict(STATES)[after], reason=reason))

    # Khóa nội dung sau khi trình duyệt, canh cả trạng thái
    def write(self, vals):
        if 'requester_id' in vals and not self.env.su and any(
                request.requester_id.id != vals['requester_id'] for request in self):
            raise UserError(self.env._(
                "Không đổi được người đề nghị. Mỗi người tự lập phiếu của mình."))
        if vals.get('active') is False:
            pending = self.filtered(lambda request: request.state == 'to_approve')
            if pending:
                raise UserError(self.env._(
                    "Phiếu %s đang chờ duyệt nên chưa lưu trữ được. "
                    "Rút về Nháp hoặc để cấp duyệt từ chối trước.",
                    ", ".join(pending.mapped('name'))))
        if LOCKED_FIELDS.intersection(vals):
            locked = self.filtered(lambda request: request.state != 'draft')
            if locked:
                raise UserError(self.env._(
                    "Phiếu %s đã trình duyệt nên không sửa được nội dung.",
                    ", ".join(locked.mapped('name'))))
        previous_states = ({request.id: request.state for request in self}
                           if 'state' in vals else None)
        res = super().write(vals)
        if previous_states is not None:
            self._check_state_transition(previous_states)
        return res

    # Phiếu mới luôn là Nháp, người tạo là người đề nghị
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['state'] = 'draft'
            if not self.env.su:
                vals['requester_id'] = self.env.uid
            if vals.get('name', '/') == '/':
                company_id = vals.get('company_id') or self.env.company.id
                vals['name'] = self.env['ir.sequence'].with_company(
                    company_id).next_by_code('im.purchase.request') or '/'
        return super().create(vals_list)

    # Chỉ xóa được phiếu Nháp, phiếu đã trình thì lưu trữ
    def unlink(self):
        if any(request.state != 'draft' for request in self):
            raise UserError(self.env._(
                "Chỉ xoá được phiếu Nháp. Phiếu đã trình thì lưu trữ, không xoá."))
        return super().unlink()
