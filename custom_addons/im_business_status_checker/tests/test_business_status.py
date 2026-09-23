import json
import os
import time
from unittest.mock import patch

import requests

from odoo.tests.common import BaseCase, TransactionCase, tagged

from odoo.addons.im_business_status_checker.tools import dkkd_portal

PREFIX = 'im_business_status_checker.'
PARAMETERS = (
    'captcha_provider', 'captcha_api_key', 'captcha_timeout',
    'request_delay', 'batch_size', 'portal_timeout', 'portal_retries',
)

ORDER_PAGE = """
<html><body><div>
Doanh nghiệp đã chọn Mã số doanh nghiệp: 5400530931, Tên doanh nghiệp: CÔNG TY CỔ PHẦN TẬP ĐOÀN ĐẦU TƯ ĐỊA ỐC ĐÔNG DƯƠNG LƯƠNG SƠN, Tình trạng doanh nghiệp: Tạm ngừng kinh doanh, Địa chỉ trụ sở chính: Số nhà 20, ngách 40, tổ 2, Phường Tân Hòa, Thành phố Hoà Bình, Tỉnh Hòa Bình, Việt Nam, Tên người đại diện theo pháp luật: PHẠM KIM OANH
</div></body></html>
"""

CATALOG_PAGE = """
<html><body>
<form id="aspnetForm" action="./ProductCatalog.aspx?h=226a" method="post">
  <input type="hidden" name="__VIEWSTATE" value="/wEPDwUK"/>
  <input type="hidden" name="ctl00$hdParameter" value="tok-1"/>
  <input type="text" name="ctl00$C$UC_ENT_LIST1$ENTERPRISE_GDT_CODEFilterFld" value=""/>
  <input type="text" name="ctl00$C$UC_ENT_LIST1$NAMEFilterFld" value=""/>
  <select name="ctl00$C$UC_ENT_LIST1$CITY_IDFld">
    <option value="">Tất cả</option><option value="105">Hòa Bình</option>
  </select>
  <div class="g-recaptcha" data-sitekey="6LewYU4UAAAAAD9dQ51Cj_A_1uHLOXw9wJIxi9x0"></div>
  <input type="submit" name="ctl00$C$UC_ENT_LIST1$BtnFilter" value="Tìm kiếm"/>
</form>
</body></html>
"""

FILTER_PAGE = """
<html><body>
<form id="aspnetForm" action="./ProductCatalog.aspx?h=226a" method="post">
  <input type="hidden" name="__VIEWSTATE" value="v2"/>
  <table id="ctl00_C_UC_ENT_LIST1_CtlList">
    <tr><td>5400530931</td><td>
      <a href="javascript:__doPostBack('ctl00$C$UC_ENT_LIST1$CtlList$ctl02$Cmd1','')">Chọn</a>
    </td></tr>
  </table>
</form>
</body></html>
"""

SITEKEY = '6LewYU4UAAAAAD9dQ51Cj_A_1uHLOXw9wJIxi9x0'

ORDER_PAGE_OTHER = ORDER_PAGE.replace(
    '5400530931', '0100109106').replace(
    'CÔNG TY CỔ PHẦN TẬP ĐOÀN ĐẦU TƯ ĐỊA ỐC ĐÔNG DƯƠNG LƯƠNG SƠN',
    'CÔNG TY TNHH NHÀ NƯỚC MỘT THÀNH VIÊN CÔNG NGHIỆP TÀU THỦY')

TWO_ROWS_PAGE = """
<html><body>
<table id="ctl00_C_UC_ENT_LIST1_CtlList">
  <tr><td>0100109106</td><td>
    <a href="javascript:__doPostBack('ctl00$C$UC_ENT_LIST1$CtlList$ctl01$Cmd1','')">Chọn</a>
  </td></tr>
  <tr><td>5400530931</td><td>
    <a href="javascript:__doPostBack('ctl00$C$UC_ENT_LIST1$CtlList$ctl02$Cmd1','')">Chọn</a>
  </td></tr>
</table>
</body></html>
"""

EMPTY_PAGE = """
<html><body>
<form id="aspnetForm" action="./ProductCatalog.aspx?h=226a" method="post">
  <div class="g-recaptcha" data-sitekey="6LewYU4UAAAAAD9dQ51Cj_A_1uHLOXw9wJIxi9x0"></div>
  <p>Danh sách trống</p>
</form>
</body></html>
"""

BROKEN_PAGE = """
<html><body><div>
Báo lỗi! Lỗi không thể xử lí đã xảy ra. Lỗi đã được ghi nhận để tiếp tục giải quyết.
Lỗi không duy nhất : 444824822 Mô tả lỗi : ORA-20000: INF.GPCR_ENTERPRISE_LIST_VW
ORA-01006: bind variable does not exist !!!
Parameters: i_NAME_IDX:[SỮA VIỆT NAM]
</div></body></html>
"""


class _FakeResponse:

    def __init__(self, text, status_code=200, url='https://example.test/page',
                 headers=None):
        self.text = text
        self.status_code = status_code
        self.url = url
        self.encoding = 'utf-8'
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


def _reopen_responses():
    return [
        _FakeResponse(CATALOG_PAGE),
        _FakeResponse('', status_code=302,
                      headers={'Location': './ProductCatalog.aspx?h=226a'}),
        _FakeResponse(CATALOG_PAGE),
    ]


class _FakeSession:
    headers = {}

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.sent = []

    def request(self, method, url, **kwargs):
        self.calls += 1
        self.sent.append({'method': method, 'url': url, 'data': kwargs.get('data')})
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


class _FakeSolver:

    def __init__(self):
        self.calls = 0

    def solve_recaptcha(self, sitekey, page_url):
        self.calls += 1
        return 'TOKEN-%s' % self.calls


class TestReadingThePage(BaseCase):

    def test_map_status(self):
        self.assertEqual(dkkd_portal.map_status('Tạm ngừng kinh doanh'), 'suspended')
        self.assertEqual(dkkd_portal.map_status('Đang hoạt động'), 'active')
        self.assertEqual(dkkd_portal.map_status('Ngừng hoạt động'), 'inactive')
        self.assertEqual(dkkd_portal.map_status('Đã giải thể'), 'inactive')
        self.assertEqual(dkkd_portal.map_status('Không rõ'), 'other')
        self.assertEqual(dkkd_portal.map_status(''), 'unknown')

    def test_read_from_the_order_sentence(self):
        info = dkkd_portal.parse_basic_info(ORDER_PAGE)
        self.assertEqual(info.status_text, 'Tạm ngừng kinh doanh')
        self.assertEqual(info.business_status, 'suspended')
        self.assertEqual(info.fields['tax_code'], '5400530931')
        self.assertEqual(
            info.fields['name'],
            'CÔNG TY CỔ PHẦN TẬP ĐOÀN ĐẦU TƯ ĐỊA ỐC ĐÔNG DƯƠNG LƯƠNG SƠN')

    def test_an_operating_company(self):
        info = dkkd_portal.parse_basic_info(
            ORDER_PAGE.replace('Tạm ngừng kinh doanh', 'Đang hoạt động'))
        self.assertEqual(info.business_status, 'active')

    def test_the_portal_error_page_is_not_a_busy_portal(self):
        self.assertTrue(dkkd_portal.looks_broken(BROKEN_PAGE))
        self.assertFalse(dkkd_portal.looks_busy(BROKEN_PAGE))
        self.assertFalse(dkkd_portal.looks_broken(ORDER_PAGE))
        self.assertFalse(dkkd_portal.looks_broken(FILTER_PAGE))

    def test_only_a_tax_code_is_treated_as_one(self):
        self.assertTrue(dkkd_portal.is_tax_code('5400530931'))
        self.assertTrue(dkkd_portal.is_tax_code('Mã số thuế 5400530931'))
        self.assertFalse(dkkd_portal.is_tax_code('CÔNG TY SỮA VIỆT NAM'))
        self.assertFalse(dkkd_portal.is_tax_code('12345'))

    def test_find_sitekey(self):
        self.assertEqual(dkkd_portal.find_sitekey(CATALOG_PAGE), SITEKEY)
        self.assertEqual(dkkd_portal.find_sitekey(ORDER_PAGE), '')

    def test_looks_busy(self):
        self.assertTrue(dkkd_portal.looks_busy('ErrorThe server is busy now'))
        self.assertFalse(dkkd_portal.looks_busy(ORDER_PAGE))

    def test_has_result_rows(self):
        self.assertTrue(dkkd_portal.has_result_rows(FILTER_PAGE))
        self.assertFalse(dkkd_portal.has_result_rows('<p>Danh sách trống</p>'))

    def test_matches_term_refuses_another_company(self):
        info = dkkd_portal.BasicInfo(
            status_text='Tạm ngừng kinh doanh',
            fields={'tax_code': '5400530931', 'name': 'CÔNG TY A'})
        self.assertTrue(dkkd_portal.matches_term(info, '5400530931'))
        self.assertFalse(dkkd_portal.matches_term(info, '0100109106'))


class TestTalkingToThePortal(BaseCase):

    def _portal(self, responses, **kwargs):
        session = _FakeSession(responses)
        portal = dkkd_portal.DkkdPortal(session=session, retries=0, retry_delay=0,
                                        **kwargs)
        portal.catalog_url = 'https://x/ProductCatalog.aspx?h=226a'
        portal.catalog_fields = {'__VIEWSTATE': 'v1'}
        portal.catalog_opened_at = time.monotonic()
        portal.captcha_sitekey = SITEKEY
        return portal, session

    def test_retries_after_a_timeout(self):
        session = _FakeSession([
            requests.exceptions.ReadTimeout('chậm'),
            requests.exceptions.ReadTimeout('chậm'),
            _FakeResponse('<html>ok</html>'),
        ])
        portal = dkkd_portal.DkkdPortal(session=session, retries=2, retry_delay=0)
        self.assertEqual(portal._get('https://x').text, '<html>ok</html>')
        self.assertEqual(session.calls, 3)

    def test_gives_up_with_a_readable_error(self):
        session = _FakeSession([requests.exceptions.ReadTimeout('chậm')])
        portal = dkkd_portal.DkkdPortal(session=session, retries=1, retry_delay=0)
        with self.assertRaises(dkkd_portal.DkkdError):
            portal._get('https://x')
        self.assertEqual(session.calls, 2)

    def test_form_fields_keep_values_and_drop_buttons(self):
        fields = dkkd_portal.DkkdPortal._form_fields(CATALOG_PAGE)
        self.assertEqual(fields['__VIEWSTATE'], '/wEPDwUK')
        self.assertEqual(fields[dkkd_portal.CATALOG_TAX_FIELD], '')
        self.assertNotIn(dkkd_portal.CATALOG_FILTER_BUTTON, fields)

    def test_submit_filter_sends_the_tax_code_and_the_token(self):
        portal, session = self._portal([_FakeResponse(FILTER_PAGE)])
        portal.submit_filter('5400530931', 'TOKEN-X')
        data = session.sent[-1]['data']
        self.assertEqual(data[dkkd_portal.CATALOG_TAX_FIELD], '5400530931')
        self.assertEqual(data[dkkd_portal.CATALOG_FILTER_BUTTON], 'Tìm kiếm')
        self.assertEqual(data['g-recaptcha-response'], 'TOKEN-X')

    def test_submit_filter_uses_the_name_field_for_a_name(self):
        portal, session = self._portal([_FakeResponse(FILTER_PAGE)])
        portal.submit_filter('CÔNG TY SỮA VIỆT NAM', 'TOKEN-X')
        data = session.sent[-1]['data']
        self.assertEqual(data[dkkd_portal.CATALOG_NAME_FIELD], 'CÔNG TY SỮA VIỆT NAM')
        self.assertEqual(data[dkkd_portal.CATALOG_TAX_FIELD], '')

    def test_open_catalog_reuses_a_fresh_session(self):
        portal, session = self._portal([_FakeResponse(FILTER_PAGE)])
        portal.open_catalog()
        self.assertEqual(session.calls, 0)

    def test_reading_the_result_opens_the_company_row(self):
        portal, session = self._portal([_FakeResponse(ORDER_PAGE)])
        info = portal.read_status_from_results(FILTER_PAGE, 'https://x', '5400530931')
        self.assertEqual(info.status_text, 'Tạm ngừng kinh doanh')
        self.assertEqual(session.calls, 1)

    def test_a_row_for_another_company_is_not_opened(self):
        portal, session = self._portal([_FakeResponse(FILTER_PAGE)])
        info = portal.read_status_from_results(FILTER_PAGE, 'https://x', '0100109106')
        self.assertEqual(info.status_text, '')
        self.assertEqual(session.calls, 0)

    def test_a_name_lookup_on_a_broken_portal_explains_itself(self):
        # Portal procedure bug: name filters raise ORA-01006.
        portal, session = self._portal([_FakeResponse(BROKEN_PAGE)])
        with self.assertRaises(dkkd_portal.DkkdBroken) as caught:
            portal.fetch_basic_info(
                dkkd_portal.Enterprise(name='CÔNG TY SỮA VIỆT NAM'),
                solver=_FakeSolver())
        self.assertIn('mã số thuế', str(caught.exception))
        self.assertTrue(portal.is_broken)
        self.assertEqual(session.calls, 1)

    def test_a_broken_portal_on_a_tax_code_asks_to_retry_later(self):
        portal, _session = self._portal([_FakeResponse(BROKEN_PAGE)])
        with self.assertRaises(dkkd_portal.DkkdBroken) as caught:
            portal.fetch_basic_info(
                dkkd_portal.Enterprise(tax_code='5400530931'),
                solver=_FakeSolver())
        self.assertIn('Thử lại sau', str(caught.exception))

    def test_lookup_without_a_solver_asks_for_configuration(self):
        portal, _session = self._portal([_FakeResponse(FILTER_PAGE)])
        with self.assertRaises(dkkd_portal.CaptchaNeeded):
            portal.fetch_basic_info(
                dkkd_portal.Enterprise(tax_code='5400530931'), solver=None)

    def test_lookup_solves_then_reads_the_status(self):
        portal, _session = self._portal([
            _FakeResponse(FILTER_PAGE), _FakeResponse(ORDER_PAGE)])
        solver = _FakeSolver()
        info = portal.fetch_basic_info(
            dkkd_portal.Enterprise(tax_code='5400530931'), solver=solver)
        self.assertEqual(solver.calls, 1)
        self.assertEqual(info.status_text, 'Tạm ngừng kinh doanh')

    def test_lookup_reports_a_company_the_portal_does_not_have(self):
        portal, _session = self._portal([
            _FakeResponse('<html>Danh sách trống</html>')])
        with self.assertRaises(dkkd_portal.DkkdNotFound):
            portal.fetch_basic_info(
                dkkd_portal.Enterprise(tax_code='0100109106'), solver=_FakeSolver())

    def test_the_second_lookup_reuses_the_captcha_of_the_session(self):
        # Second lookup must reopen the form, not solve captcha again.
        portal, session = self._portal(
            [_FakeResponse(FILTER_PAGE), _FakeResponse(ORDER_PAGE)]
            + _reopen_responses()
            + [_FakeResponse(FILTER_PAGE), _FakeResponse(ORDER_PAGE)])
        solver = _FakeSolver()
        first = portal.fetch_basic_info(
            dkkd_portal.Enterprise(tax_code='5400530931'), solver=solver)
        opened_after = session.calls
        second = portal.fetch_basic_info(
            dkkd_portal.Enterprise(tax_code='5400530931'), solver=solver)
        self.assertEqual(solver.calls, 1)
        self.assertEqual(first.status_text, 'Tạm ngừng kinh doanh')
        self.assertEqual(second.status_text, 'Tạm ngừng kinh doanh')
        self.assertEqual(session.calls - opened_after, 5)

    def test_a_rerendered_answer_of_another_company_is_not_kept(self):
        # A stale answer must never store another company.
        portal, _session = self._portal(
            _reopen_responses()
            + [_FakeResponse(ORDER_PAGE), _FakeResponse(ORDER_PAGE_OTHER)])
        portal.remember_captcha('TOKEN-CU')
        solver = _FakeSolver()
        info = portal.fetch_basic_info(
            dkkd_portal.Enterprise(tax_code='0100109106'), solver=solver)
        self.assertEqual(info.fields['tax_code'], '0100109106')
        self.assertEqual(solver.calls, 1)

    def test_a_stale_captcha_pass_is_solved_again(self):
        portal, _session = self._portal([
            _FakeResponse(FILTER_PAGE), _FakeResponse(ORDER_PAGE)])
        portal.remember_captcha('TOKEN-CU')
        portal.captcha_passed_at = time.monotonic() - dkkd_portal.CAPTCHA_TTL - 1
        solver = _FakeSolver()
        info = portal.fetch_basic_info(
            dkkd_portal.Enterprise(tax_code='5400530931'), solver=solver)
        self.assertEqual(solver.calls, 1)
        self.assertEqual(info.status_text, 'Tạm ngừng kinh doanh')

    def test_an_empty_answer_on_a_reused_pass_solves_a_new_captcha(self):
        portal, _session = self._portal(
            _reopen_responses()
            + [_FakeResponse(EMPTY_PAGE),
               _FakeResponse(FILTER_PAGE), _FakeResponse(ORDER_PAGE)])
        portal.remember_captcha('TOKEN-CU')
        solver = _FakeSolver()
        info = portal.fetch_basic_info(
            dkkd_portal.Enterprise(tax_code='5400530931'), solver=solver)
        self.assertEqual(solver.calls, 1)
        self.assertEqual(info.status_text, 'Tạm ngừng kinh doanh')

    def test_the_matching_row_is_opened_before_the_others(self):
        targets = dkkd_portal.DkkdPortal._result_row_targets(
            TWO_ROWS_PAGE, '5400530931')
        self.assertEqual(len(targets), 2)
        self.assertIn('ctl02', targets[0][0])
        self.assertIn('ctl01', targets[1][0])


@tagged('post_install', '-at_install')
class TestTheRecord(TransactionCase):

    def test_is_operating_follows_the_status(self):
        record = self.env['business.status.check'].create({
            'name': 'X', 'vat': '5400530931', 'status': 'active'})
        self.assertTrue(record.is_operating)
        record.status = 'suspended'
        self.assertFalse(record.is_operating)

    def test_lookup_writes_the_status(self):
        record = self.env['business.status.check'].create({'vat': '5400530931'})
        info = dkkd_portal.BasicInfo(
            status_text='Tạm ngừng kinh doanh',
            fields={'name': 'CÔNG TY X', 'tax_code': '5400530931'})
        with patch.object(dkkd_portal.DkkdPortal, 'fetch_basic_info', return_value=info):
            record._lookup_one()
        self.assertEqual(record.status, 'suspended')
        self.assertFalse(record.is_operating)
        self.assertEqual(record.state, 'done')
        self.assertEqual(record.name, 'CÔNG TY X')
        self.assertTrue(record.checked_on)

    def test_lookup_reports_a_missing_company(self):
        record = self.env['business.status.check'].create({'vat': '999999999'})
        with patch.object(dkkd_portal.DkkdPortal, 'fetch_basic_info',
                          side_effect=dkkd_portal.DkkdNotFound('không thấy')):
            record._lookup_one()
        self.assertEqual(record.state, 'not_found')
        self.assertEqual(record.status, 'unknown')

    def test_lookup_without_a_captcha_key_tells_the_admin(self):
        record = self.env['business.status.check'].create({'vat': '5400530931'})
        with patch.object(dkkd_portal.DkkdPortal, 'fetch_basic_info',
                          side_effect=dkkd_portal.CaptchaNeeded('u', 'k', {})):
            record._lookup_one()
        self.assertEqual(record.state, 'error')
        self.assertIn('captcha', (record.note or '').lower())

    def test_the_lookup_button_is_always_visible(self):
        view = self.env.ref('im_business_status_checker.view_business_status_list')
        self.assertIn('display="always"', view.arch)

    def test_one_column_carries_the_state_and_the_status(self):
        # The widget reads state and note, so both live in the list arch.
        view = self.env.ref('im_business_status_checker.view_business_status_list')
        self.assertIn('widget="lookup_status"', view.arch)
        self.assertIn('name="state" optional="hide"', view.arch)
        self.assertIn('name="note" optional="hide"', view.arch)

    def test_an_empty_queue_starts_no_worker(self):
        self.env['business.status.check'].search(
            [('state', '=', 'queued')]).write({'state': 'done'})
        self.assertEqual(self.env['business.status.check'].process_queue(), 0)

    def test_the_batch_handles_every_queued_record(self):
        # The screen calls this, so the queue never waits for the cron.
        self.env['ir.config_parameter'].sudo().set_param(
            PREFIX + 'request_delay', '0')
        for tax_code in ('5400530931', '0100109106'):
            self.env['business.status.check'].create({'vat': tax_code})
        info = dkkd_portal.BasicInfo(
            status_text='Đang hoạt động',
            fields={'name': 'CÔNG TY X', 'tax_code': '5400530931'})
        with patch.object(dkkd_portal.DkkdPortal, 'fetch_basic_info', return_value=info):
            processed = self.env['business.status.check'].process_queue()
        self.assertEqual(processed, 2)
        self.assertFalse(self.env['business.status.check'].search_count(
            [('state', '=', 'queued')]))

    def test_one_worker_at_a_time_keeps_the_captcha_bill_low(self):
        # A second worker would solve a second captcha for the same rows.
        checks = self.env['business.status.check']
        key = self.env['ir.model']._get_id('business.status.check')
        self.assertTrue(checks._queue_is_free())
        with self.registry.cursor() as other:
            other.execute("SELECT pg_try_advisory_xact_lock(%s)", [key])
            self.assertFalse(other.fetchone()[0])

    def test_the_batch_uses_one_portal_client(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'im_business_status_checker.request_delay', '0')
        for tax_code in ('5400530931', '0100109106', '0300588560'):
            self.env['business.status.check'].create({'vat': tax_code})
        info = dkkd_portal.BasicInfo(
            status_text='Đang hoạt động',
            fields={'name': 'CÔNG TY X', 'tax_code': '5400530931'})
        with patch.object(dkkd_portal, 'DkkdPortal') as factory:
            factory.return_value.fetch_basic_info.return_value = info
            factory.return_value.is_broken = False
            self.assertEqual(
                self.env['business.status.check'].process_queue(), 3)
        self.assertEqual(factory.call_count, 1)

    def test_the_batch_rebuilds_the_session_after_a_broken_portal(self):
        # A broken session must not infect the next record.
        self.env['ir.config_parameter'].sudo().set_param(
            'im_business_status_checker.request_delay', '0')
        for tax_code in ('5400530931', '0100109106', '0300588560'):
            self.env['business.status.check'].create({'vat': tax_code})
        with patch.object(dkkd_portal, 'DkkdPortal') as factory:
            factory.return_value.fetch_basic_info.side_effect = (
                dkkd_portal.DkkdBroken('cổng lỗi'))
            factory.return_value.is_broken = True
            self.env['business.status.check'].process_queue()
        self.assertEqual(factory.call_count, 3)
        self.assertEqual(
            self.env['business.status.check'].search_count(
                [('state', '=', 'error')]), 3)

    def test_the_captcha_provider_can_come_from_the_environment(self):
        # Hosting sets the provider by environment, not in the settings screen.
        record = self.env['business.status.check']
        env = {'CAPTCHA_PROVIDER': '2captcha', 'CAPTCHA_API_KEY': 'env-key'}
        with patch.dict(os.environ, env):
            self.assertEqual(record._solver().provider, '2captcha')
        self.env['ir.config_parameter'].sudo().set_param(
            PREFIX + 'captcha_provider', 'capsolver')
        with patch.dict(os.environ, env):
            self.assertEqual(record._solver().provider, 'capsolver')

    def test_the_portal_client_follows_the_settings(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'im_business_status_checker.portal_timeout', '20')
        self.env['ir.config_parameter'].sudo().set_param(
            'im_business_status_checker.portal_retries', '0')
        client = self.env['business.status.check']._portal_client()
        self.assertEqual(client.timeout, 20)
        self.assertEqual(client.retries, 0)

    def test_every_parameter_has_a_settings_field(self):
        # One settings field per parameter, so the two never drift apart.
        keys = {
            field.config_parameter
            for field in self.env['res.config.settings']._fields.values()
            if getattr(field, 'config_parameter', '')
            and field.config_parameter.startswith(PREFIX)
        }
        self.assertEqual(keys, {PREFIX + name for name in PARAMETERS})

    def test_a_parameter_value_reaches_the_code(self):
        params = self.env['ir.config_parameter'].sudo()
        record = self.env['business.status.check']
        key = PREFIX + 'batch_size'
        params.set_param(key, '5')
        self.assertEqual(record._setting_int('batch_size', 10), 5)
        params.search([('key', '=', key)]).unlink()
        self.assertEqual(record._setting_int('batch_size', 10), 10)

    def test_wizard_creates_the_record_and_queues_it(self):
        action = self.env['business.status.lookup'].create(
            {'query': '5400530931'}).action_lookup()
        record = self.env['business.status.check'].search(
            [('vat', '=', '5400530931')])
        self.assertEqual(len(record), 1)
        self.assertEqual(record.state, 'queued')
        self.assertEqual(action['res_model'], 'business.status.check')
        self.assertEqual(action['view_mode'], 'list')

    def test_wizard_reuses_the_record_of_the_same_tax_code(self):
        record = self.env['business.status.check'].create(
            {'vat': '5400530931', 'state': 'done', 'status': 'active'})
        self.env['business.status.lookup'].create(
            {'query': '5400530931'}).action_lookup()
        self.assertEqual(record.state, 'queued')
        self.assertEqual(self.env['business.status.check'].search_count(
            [('vat', '=', '5400530931')]), 1)

    def test_wizard_keeps_a_company_name(self):
        self.env['business.status.lookup'].create(
            {'query': 'CÔNG TY ABC'}).action_lookup()
        record = self.env['business.status.check'].search([('name', '=', 'CÔNG TY ABC')])
        self.assertTrue(record)
        self.assertFalse(record.vat)

    def test_wizard_opens_the_list_without_a_message(self):
        # No notification: the list itself shows the queued record.
        action = self.env['business.status.lookup'].create(
            {'query': '5400530931'}).action_lookup()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertTrue(action.get('views'))
        self.assertNotIn('tag', action)

    def test_wizard_wakes_the_cron(self):
        before = self.env['ir.cron.trigger'].search_count([])
        self.env['business.status.lookup'].create(
            {'query': '5400530931'}).action_lookup()
        self.assertGreater(self.env['ir.cron.trigger'].search_count([]), before)
