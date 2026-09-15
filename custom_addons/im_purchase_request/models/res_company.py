from odoo import api, fields, models

# Công ty nào cũng có một thiết lập đề nghị mua hàng
class ResCompany(models.Model):
    _inherit = 'res.company'

    im_config_ids = fields.One2many(
        'im.purchase.request.config', 'company_id', string="Thiết lập đề nghị mua hàng")

    # Công ty mới được tạo thiết lập ngay
    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            self.env['im.purchase.request.config']._for_company(company)
        return companies
