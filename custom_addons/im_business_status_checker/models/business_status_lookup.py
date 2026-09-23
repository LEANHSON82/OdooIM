import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BusinessStatusLookup(models.TransientModel):

    _name = 'business.status.lookup'
    _description = 'Tra cứu tình trạng doanh nghiệp'

    query = fields.Char(string='Mã số thuế hoặc tên doanh nghiệp', required=True)

    def action_lookup(self):
        self.ensure_one()
        query = (self.query or '').strip()
        digits = ''.join(character for character in query if character.isdigit())
        is_tax_code = len(digits) >= 8
        record = self.env['business.status.check'].search(
            [('vat', '=', query)] if is_tax_code else [('name', '=', query)], limit=1)
        if record:
            record.write({'state': 'queued'})
        else:
            record = self.env['business.status.check'].create({
                'vat': query if is_tax_code else False,
                'name': False if is_tax_code else query,
                'state': 'queued',
            })
        cron = self.env.ref('im_business_status_checker.ir_cron_lookup',
                            raise_if_not_found=False)
        if cron:
            # Wake the cron so the lookup starts now, not in five minutes.
            cron.sudo()._trigger()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tình trạng doanh nghiệp',
            'res_model': 'business.status.check',
            'view_mode': 'list',
            # Web client reads action.views at once, so keep it.
            'views': [(False, 'list')],
            'target': 'current',
        }
