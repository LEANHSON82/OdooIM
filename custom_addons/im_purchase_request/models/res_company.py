from odoo import api, fields, models

# Every company owns one purchase request settings record
class ResCompany(models.Model):
    _inherit = 'res.company'

    im_config_ids = fields.One2many(
        'im.purchase.request.config', 'company_id', string="Thiết lập đề nghị mua hàng")

    # A new company gets its settings straight away
    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            self.env['im.purchase.request.config']._for_company(company)
        return companies
