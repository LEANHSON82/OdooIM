import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)

# Ai cũng được, hoặc giới hạn theo bảng quyền
PERMISSION_MODES = [
    ('all', "Ai cũng được"),
    ('limited', "Giới hạn"),
]


# Màn hình thiết lập chung, mỗi công ty một bản ghi
class PurchaseRequestConfig(models.Model):
    _name = 'im.purchase.request.config'
    _description = 'Thiết lập đề nghị mua hàng'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', string="Công ty", required=True, readonly=True,
        default=lambda self: self.env.company, ondelete='cascade')
    currency_id = fields.Many2one(related='company_id.currency_id')

    level_ids = fields.One2many(
        'im.purchase.request.approval.level', 'config_id', string="Cấp duyệt",
        context={'active_test': False})

    po_creator_mode = fields.Selection(
        PERMISSION_MODES, string="Ai được tạo đơn mua", default='all', required=True)
    po_creator_rule_ids = fields.One2many(
        'im.purchase.request.permission', 'config_id', string="Giới hạn tạo đơn mua",
        domain=[('permission_type', '=', 'po_creator')])

    overrun_approval_mode = fields.Selection(
        PERMISSION_MODES, string="Ai được duyệt vượt dự toán", default='all', required=True)
    overrun_rule_ids = fields.One2many(
        'im.purchase.request.permission', 'config_id', string="Giới hạn duyệt vượt dự toán",
        domain=[('permission_type', '=', 'overrun')])
    overrun_tolerance_pct = fields.Float(
        string="Cho phép vượt dự toán (%)", default=10.0,
        help="Tổng hóa đơn vượt dự toán quá mức này thì phải có người duyệt vượt.")

    quote_count_mode = fields.Selection(
        [('fixed', "Cố định"), ('by_amount', "Theo giá trị")],
        string="Số nhà cung cấp tối thiểu", default='fixed', required=True,
        help="Cố định: mọi dòng hàng dùng chung một số. Theo giá trị: số nhà cung cấp "
             "tối thiểu tùy thành tiền của từng dòng hàng.")
    min_quote_count = fields.Integer(
        string="Số nhà cung cấp tối thiểu mỗi dòng hàng",
        default=lambda self: self._default_min_quote_count(),
        help="Mỗi dòng hàng phải nhập ít nhất ngần này nhà cung cấp mới trình duyệt được. "
             "0 là không bắt buộc: nhập thẳng đơn giá và nhà cung cấp gợi ý. "
             "Ở chế độ Theo giá trị, số này dùng cho dòng không rơi vào dải nào.")
    quote_rule_ids = fields.One2many(
        'im.purchase.request.quote.rule', 'config_id',
        string="Số nhà cung cấp tối thiểu theo thành tiền dòng hàng")

    product_creation = fields.Boolean(
        string="Người đề nghị tạo được sản phẩm mới",
        compute='_compute_product_creation', inverse='_inverse_product_creation',
        help="Mọi nhân viên được tạo nhanh sản phẩm mới (chỉ tạo, không sửa, không xoá) "
             "ngay trong ô Sản phẩm của dòng hàng. Áp cho mọi công ty.")
    vendor_creation = fields.Boolean(
        string="Người đề nghị tạo được nhà cung cấp mới",
        compute='_compute_vendor_creation', inverse='_inverse_vendor_creation',
        help="Mọi nhân viên được tạo liên hệ mới (không sửa, không xoá) để thêm "
             "NCC gợi ý ngay trên phiếu. Áp cho mọi công ty.")

    _company_uniq = models.Constraint(
        'unique(company_id)', 'Mỗi công ty chỉ có một thiết lập đề nghị mua hàng.')

    # Dòng quyền mới nhận đúng loại theo danh sách chứa nó
    @api.model
    def _with_permission_types(self, vals):
        vals = dict(vals)
        for field_name, permission_type in (('po_creator_rule_ids', 'po_creator'),
                                            ('overrun_rule_ids', 'overrun')):
            if not vals.get(field_name):
                continue
            commands = []
            for command in vals[field_name]:
                if command[0] == Command.CREATE:
                    command = (command[0], command[1],
                               dict(command[2], permission_type=permission_type))
                commands.append(command)
            vals[field_name] = commands
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._with_permission_types(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._with_permission_types(vals))

    # Bật hoặc tắt một nhóm cho toàn bộ nhân viên
    def _toggle_employee_implied(self, xmlid, wanted):
        employee = self.env.ref('base.group_user').sudo()
        group = self.env.ref(xmlid)
        if wanted and group not in employee.implied_ids:
            employee.implied_ids = [Command.link(group.id)]
        elif not wanted and group in employee.implied_ids:
            employee.implied_ids = [Command.unlink(group.id)]

    # Công tắc cho nhân viên tạo sản phẩm mới
    def _compute_product_creation(self):
        employee = self.env.ref('base.group_user').sudo()
        creator = self.env.ref('im_purchase_request.group_product_creator')
        for config in self:
            config.product_creation = creator in employee.implied_ids

    def _inverse_product_creation(self):
        self._toggle_employee_implied(
            'im_purchase_request.group_product_creator', any(self.mapped('product_creation')))

    # Công tắc cho nhân viên tạo nhà cung cấp mới
    def _compute_vendor_creation(self):
        employee = self.env.ref('base.group_user').sudo()
        creator = self.env.ref('im_purchase_request.group_vendor_creator')
        for config in self:
            config.vendor_creation = creator in employee.implied_ids

    def _inverse_vendor_creation(self):
        employee = self.env.ref('base.group_user').sudo()
        creator = self.env.ref('im_purchase_request.group_vendor_creator')
        wanted = any(self.mapped('vendor_creation'))
        if wanted and creator not in employee.implied_ids:
            employee.implied_ids = [Command.link(creator.id)]
        elif not wanted and creator in employee.implied_ids:
            employee.implied_ids = [Command.unlink(creator.id)]

    # Lấy thiết lập của công ty, chưa có thì chép từ công ty khác
    @api.model
    def _for_company(self, company):
        Config = self.sudo()
        config = Config.search([('company_id', '=', company.id)], limit=1)
        if config:
            return config
        template = Config.search([('company_id', '!=', company.id)], order='id', limit=1)
        config = Config.create({
            'company_id': company.id,
            'overrun_tolerance_pct': template.overrun_tolerance_pct if template
            else self._default_tolerance(),
            'min_quote_count': template.min_quote_count if template
            else self._default_min_quote_count(),
        })
        for level in template.with_context(active_test=False).level_ids:
            level.with_context(im_skip_level_group_check=True).copy(
                {'config_id': config.id, 'company_id': company.id})
        return config

    # Số nhà cung cấp mặc định, lấy từ tham số hệ thống
    @api.model
    def _default_min_quote_count(self):
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'im_purchase_request.min_quote_count', '3')
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 3

    # Số nhà cung cấp tối thiểu không được âm
    @api.constrains('min_quote_count')
    def _check_min_quote_count(self):
        for config in self:
            if config.min_quote_count < 0:
                raise ValidationError(self.env._("Số nhà cung cấp tối thiểu không được âm."))

    # Số nhà cung cấp tối thiểu cho dòng hàng có thành tiền này
    def _min_quote_count_for(self, amount):
        self.ensure_one()
        if self.quote_count_mode == 'by_amount':
            rounding = self.currency_id.rounding
            for rule in self.quote_rule_ids:
                if rule._applies_to(amount, rounding):
                    return max(0, rule.min_quote_count)
        return max(0, self.min_quote_count)

    # Mức cho phép vượt mặc định, lấy từ tham số hệ thống
    @api.model
    def _default_tolerance(self):
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'im_purchase_request.overrun_tolerance_pct', '10')
        try:
            return float(raw or 0.0)
        except (TypeError, ValueError):
            return 10.0

    # Menu Thiết lập mở thẳng bản ghi của công ty hiện tại
    @api.model
    def action_open(self):
        config = self._for_company(self.env.company)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Thiết lập đề nghị mua hàng"),
            'res_model': self._name,
            'res_id': config.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # Chạy khi cài và khi nâng cấp, gom dữ liệu cũ về thiết lập
    @api.model
    def _ensure_company_configs(self):
        cr = self.env.cr
        previous_modes = {}
        # Hai chế độ này từng nằm trên res.company
        if column_exists(cr, 'res_company', 'im_po_creator_mode'):
            cr.execute("SELECT id, im_po_creator_mode, im_overrun_approval_mode FROM res_company")
            previous_modes = {row[0]: row[1:] for row in cr.fetchall()}

        # Nhóm đang dùng ở cấp duyệt cũ được đánh dấu là nhóm duyệt
        level_groups = self.env['im.purchase.request.approval.level'].sudo().with_context(
            active_test=False).search([]).group_id
        for group in level_groups.filtered(lambda group: not group.im_is_approver_role):
            if group._im_is_protected():
                _logger.warning(
                    "Approval level group %s is a system group and was not turned into an "
                    "approver role; pick an approver group for that level.", group.full_name)
            else:
                group.im_is_approver_role = True

        Config = self.sudo()
        # Mỗi công ty một thiết lập, công ty chính làm mẫu
        main = self.env.ref('base.main_company', raise_if_not_found=False)
        companies = self.env['res.company'].sudo().search([])
        companies = (main & companies) | companies if main else companies
        configs = {}
        for company in companies:
            config = Config.search([('company_id', '=', company.id)], limit=1)
            if not config:
                valid = dict(PERMISSION_MODES)
                po_mode, overrun_mode = previous_modes.get(company.id, (None, None))
                config = Config.create({
                    'company_id': company.id,
                    'po_creator_mode': po_mode if po_mode in valid else 'all',
                    'overrun_approval_mode': overrun_mode if overrun_mode in valid else 'all',
                    'overrun_tolerance_pct': self._default_tolerance(),
                })
            configs[company.id] = config

        # Cấp duyệt cũ chưa gắn thiết lập thì gắn vào đây
        levels = self.env['im.purchase.request.approval.level'].sudo().with_context(
            active_test=False).search([('config_id', '=', False)])
        for level in levels:
            if level.company_id:
                level.config_id = configs[level.company_id.id]
                continue
            targets = list(configs.values())
            level.write({'config_id': targets[0].id, 'company_id': targets[0].company_id.id})
            for config in targets[1:]:
                level.with_context(im_skip_level_group_check=True).copy(
                    {'config_id': config.id, 'company_id': config.company_id.id})

        # Công ty chưa có cấp nào thì chép cấp của công ty mẫu
        template = configs.get(main.id) if main else None
        template = template or next(iter(configs.values()), Config)
        template_levels = template.with_context(active_test=False).level_ids
        for config in configs.values():
            if config == template or not template_levels:
                continue
            if not config.with_context(active_test=False).level_ids:
                for level in template_levels:
                    level.with_context(im_skip_level_group_check=True).copy(
                        {'config_id': config.id, 'company_id': config.company_id.id})

        # Dòng quyền cũ từng tick “người ký cấp duyệt” đã bỏ
        legacy_signers = set()
        if column_exists(cr, 'im_purchase_request_permission', 'include_level_signers'):
            cr.execute("SELECT id FROM im_purchase_request_permission "
                       "WHERE include_level_signers AND config_id IS NULL")
            legacy_signers = {row[0] for row in cr.fetchall()}

        rules = self.env['im.purchase.request.permission'].sudo().search([('config_id', '=', False)])
        for rule in rules:
            config = configs.get(rule.company_id.id)
            if not config:
                continue
            rule.config_id = config
            if rule.id in legacy_signers:
                levels = config.level_ids.filtered(lambda level: level.active and (
                    not rule.amount_max or level.amount_threshold < rule.amount_max) and (
                    not level.amount_max or level.amount_max > rule.amount_threshold))
                if levels:
                    lowest = min(levels.mapped('sequence'))
                    signers = config.level_ids.filtered(
                        lambda level: level.active and level.sequence >= lowest)
                    rule.group_ids = [Command.link(group.id) for group in signers.group_id]
            # Dòng quyền không còn ai thì xóa và ghi log
            if not (rule.group_ids or rule.user_ids):
                _logger.warning(
                    "Purchase request permission %s (%s, %s-%s) allowed nobody after the "
                    "move to group/user rules and was removed.",
                    rule.id, rule.permission_type, rule.amount_threshold, rule.amount_max)
                rule.unlink()
