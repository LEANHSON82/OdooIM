import logging
import os
import time

from odoo import api, fields, models

from odoo.addons.im_business_status_checker.tools import captcha_solver, dkkd_portal

_logger = logging.getLogger(__name__)


class BusinessStatusCheck(models.Model):

    _name = 'business.status.check'
    _description = 'Tình trạng doanh nghiệp'
    _order = 'checked_on desc, id desc'

    name = fields.Char(string='Tên doanh nghiệp')
    vat = fields.Char(string='Mã số thuế')
    is_operating = fields.Boolean(
        string='Còn hoạt động', compute='_compute_is_operating', store=True)
    status = fields.Selection(
        [('active', 'Đang hoạt động'),
         ('suspended', 'Tạm ngừng kinh doanh'),
         ('inactive', 'Ngừng hoạt động'),
         ('other', 'Khác'),
         ('unknown', 'Chưa rõ')],
        string='Tình trạng', default='unknown')
    checked_on = fields.Date(string='Ngày tra cứu')
    state = fields.Selection(
        [('queued', 'Chờ tra cứu'),
         ('done', 'Đã tra cứu'),
         ('not_found', 'Không tìm thấy'),
         ('error', 'Lỗi tra cứu')],
        string='Trạng thái', default='queued', required=True)
    note = fields.Text(string='Ghi chú')

    @api.depends('status')
    def _compute_is_operating(self):
        for record in self:
            record.is_operating = record.status == 'active'

    @api.model
    def _setting(self, key, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(
            'im_business_status_checker.' + key, default)

    @api.model
    def _setting_int(self, key, default=0):
        return int(self._setting(key, default) or 0)

    @api.model
    def _solver(self):
        # Settings win, environment is the fallback for hosting.
        provider = (self._setting('captcha_provider', '')
                    or os.environ.get('CAPTCHA_PROVIDER', '')
                    or 'none').strip().lower()
        if provider == 'none':
            return None
        key = (self._setting('captcha_api_key', '')
               or os.environ.get('CAPTCHA_API_KEY', '')).strip()
        if not key:
            _logger.warning('No captcha service key for %s', provider)
            return None
        try:
            timeout = self._setting_int('captcha_timeout', 180)
            return captcha_solver.CaptchaSolver(provider, key, timeout=timeout)
        except captcha_solver.CaptchaSolveError as error:
            _logger.warning('Cannot build the captcha solver: %s', error)
            return None

    @api.model
    def _portal_client(self):
        # One session per batch, so the captcha is charged once.
        return dkkd_portal.DkkdPortal(
            timeout=self._setting_int('portal_timeout', 45),
            retries=self._setting_int('portal_retries', 1))

    def action_lookup(self):
        solver = self._solver()
        client = None
        for record in self:
            # Replace a broken session so the next record starts clean.
            if client is None or client.is_broken:
                client = self._portal_client()
            record._lookup_one(client=client, solver=solver)
        return True

    def _lookup_one(self, client=None, solver=None):
        self.ensure_one()
        term = (self.vat or self.name or '').strip()
        if not term:
            self.write({'state': 'error', 'note': 'Thiếu mã số thuế và tên.'})
            return
        client = client or self._portal_client()
        enterprise = dkkd_portal.Enterprise(tax_code=self.vat or '', name=self.name or '')
        try:
            info = client.fetch_basic_info(enterprise, solver=solver or self._solver())
        except dkkd_portal.CaptchaNeeded:
            self.write({
                'state': 'error',
                'note': 'Cần khóa captcha ở Cài đặt',
            })
            return
        except dkkd_portal.DkkdNotFound as error:
            self.write({'state': 'not_found', 'note': str(error)})
            return
        except dkkd_portal.DkkdError as error:
            self.write({'state': 'error', 'note': str(error)})
            return
        values = {
            'status': info.business_status,
            'checked_on': fields.Date.today(),
            'state': 'done',
            'note': False,
        }
        if info.fields.get('name'):
            values['name'] = info.fields['name']
        if not self.vat and info.fields.get('tax_code'):
            values['vat'] = info.fields['tax_code']
        self.write(values)

    @api.model
    def process_queue(self):
        # The list view drains the queue, so a slow cron cannot block it.
        return self._cron_lookup()

    @api.model
    def _queue_is_free(self):
        # One worker at a time, or two lookups pay for two captchas.
        key = self.env['ir.model']._get_id('business.status.check')
        self.env.cr.execute("SELECT pg_try_advisory_xact_lock(%s)", [key])
        return self.env.cr.fetchone()[0]

    @api.model
    def _cron_lookup(self):
        if not self._queue_is_free():
            return 0
        records = self.search(
            [('state', '=', 'queued')],
            limit=self._setting_int('batch_size', 10), order='id')
        if not records:
            return 0
        _logger.info('Looking up %s queued records', len(records))
        delay = self._setting_int('request_delay', 3)
        client = None
        solver = self._solver()
        for index, record in enumerate(records):
            if index and delay:
                time.sleep(delay)
            # Rebuild the session after the portal broke it.
            if client is None or client.is_broken:
                client = self._portal_client()
            try:
                record._lookup_one(client=client, solver=solver)
            except Exception:  # pragma: no cover
                _logger.exception('Lookup failed for %s', record.display_name)
                record.write({'state': 'error', 'note': 'Lỗi không mong đợi.'})
        return len(records)
