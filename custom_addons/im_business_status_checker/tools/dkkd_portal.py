import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urljoin

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    from lxml import html as lxml_html
except ImportError:  # pragma: no cover
    lxml_html = None

# The public homepage links here, so the lookup starts at this portal.
INFO_ORIGIN = 'https://dichvuthongtin.dkkd.gov.vn'
DEFAULT_PAGE_URL = INFO_ORIGIN + '/inf/default.aspx'
USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36')

CATALOG_POSTBACK_TARGET = 'ctl00$C$RptProdGroups$ctl02$LnkActiveProdGroup'
CATALOG_TAX_FIELD = 'ctl00$C$UC_ENT_LIST1$ENTERPRISE_GDT_CODEFilterFld'
CATALOG_NAME_FIELD = 'ctl00$C$UC_ENT_LIST1$NAMEFilterFld'
CATALOG_FILTER_BUTTON = 'ctl00$C$UC_ENT_LIST1$BtnFilter'
CATALOG_FILTER_VALUE = 'Tìm kiếm'
CATALOG_RESULT_TABLE = 'ctl00_C_UC_ENT_LIST1_CtlList'
CATALOG_FORM_ID = 'aspnetForm'
# Catalog page stays usable this long inside one session.
CATALOG_TTL = 240
# Portal checks captcha once per session, pass dies after a few minutes.
CAPTCHA_TTL = 180

STATUS_LABELS = ('Tình trạng hoạt động', 'Tình trạng doanh nghiệp')

STATUS_KEYWORDS = (
    ('active', ('đang hoạt động', 'hoạt động bình thường')),
    ('suspended', ('tạm ngừng', 'tạm dừng')),
    ('inactive', ('ngừng hoạt động', 'chấm dứt', 'giải thể', 'phá sản', 'thu hồi')),
)

# Portal sheds load with these phrases, so wait and retry.
BUSY_MARKERS = ('server is busy', 'error processing', 'quá tải',
                'vượt quá hạn mức')

# Portal reports its own procedure failure, retrying cannot help.
BROKEN_MARKERS = ('lỗi không thể xử lí', 'mô tả lỗi')
_ORA_CODE = re.compile(r'ORA-\d{4,5}')


class DkkdError(Exception):
    pass


class DkkdNotFound(DkkdError):
    pass


class CaptchaNeeded(DkkdError):
    pass


class DkkdBroken(DkkdError):
    pass


@dataclass
class Enterprise:

    tax_code: str = ''
    name: str = ''


@dataclass
class BasicInfo:

    status_text: str = ''
    fields: dict = field(default_factory=dict)
    page_url: str = ''

    @property
    def business_status(self):
        return map_status(self.status_text)


def clean_text(value):
    if value is None:
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()


def strip_accents(value):
    text = clean_text(value).lower().replace('đ', 'd')
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')


def map_status(status_text):
    text = strip_accents(status_text)
    for value, keywords in STATUS_KEYWORDS:
        if any(strip_accents(keyword) in text for keyword in keywords):
            return value
    return 'unknown' if not text else 'other'


def looks_busy(html_text):
    lowered = strip_accents(html_text)
    return any(strip_accents(marker) in lowered for marker in BUSY_MARKERS)


def looks_broken(html_text):
    # An ORA code alone already means the portal procedure failed.
    lowered = strip_accents(html_text)
    if any(strip_accents(marker) in lowered for marker in BROKEN_MARKERS):
        return True
    return bool(_ORA_CODE.search(html_text or ''))


def is_tax_code(term):
    # Eight digits or more counts as a tax code.
    digits = ''.join(character for character in (term or '')
                     if character.isdigit())
    return bool(digits) and len(digits) >= 8


def broken_message(term):
    if is_tax_code(term):
        return "Cổng lỗi (ORA-01006). Thử lại sau."
    return "Cổng lỗi khi tra bằng tên (ORA-01006). Dùng mã số thuế."


def has_result_rows(html_text):
    return bool(re.search(r'UC_ENT_LIST1\$CtlList\$ctl\d+\$Cmd', html_text or ''))


def matches_term(info, term):
    # Portal re-renders old rows, so never store another company.
    wanted = re.sub(r'\D', '', term or '')
    found = re.sub(r'\D', '', (info.fields or {}).get('tax_code', ''))
    if wanted and found:
        return found == wanted
    wanted_name = strip_accents(term)
    found_name = strip_accents((info.fields or {}).get('name', ''))
    if not wanted_name or not found_name:
        return True
    return wanted_name in found_name or found_name in wanted_name


def _require_libs():
    if requests is None or lxml_html is None:
        raise DkkdError("Cần cài thư viện Python 'requests' và 'lxml'")


def _field(text, *labels):
    for label in labels:
        match = re.search(re.escape(label) + r'\s*:\s*([^,]+)', text, re.I)
        if match:
            value = clean_text(match.group(1))
            if value:
                return value
    return ''


def parse_basic_info(html_text, page_url=''):
    _require_libs()
    text = clean_text(lxml_html.fromstring(html_text).text_content())
    return BasicInfo(
        status_text=_field(text, *STATUS_LABELS),
        fields={
            'name': _field(text, 'Tên doanh nghiệp'),
            'tax_code': _field(text, 'Mã số doanh nghiệp'),
        },
        page_url=page_url,
    )


def find_sitekey(html_text):
    patterns = (
        r'data-sitekey=["\']([^"\']+)["\']',
        r'sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, html_text, re.I)
        if match:
            return match.group(1).strip()
    return ''


class DkkdPortal:

    def __init__(self, timeout=90, session=None, retries=2, retry_delay=5):
        _require_libs()
        self.timeout = timeout
        self.retries = max(int(retries or 0), 0)
        self.retry_delay = max(int(retry_delay or 0), 0)
        self.session = session or requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
        })
        self.catalog_url = ''
        self.catalog_fields = {}
        self.catalog_opened_at = 0.0
        self.captcha_sitekey = ''
        self.captcha_token = ''
        self.captcha_passed_at = 0.0
        self.is_broken = False

    @property
    def captcha_is_reusable(self):
        # Only trust the pass while the portal still accepts it.
        return bool(self.captcha_token) and (
            time.monotonic() - self.captcha_passed_at < CAPTCHA_TTL)

    def remember_captcha(self, token):
        self.captcha_token = token or ''
        self.captcha_passed_at = time.monotonic()

    def forget_captcha(self):
        self.captcha_token = ''
        self.captcha_passed_at = 0.0

    def _send(self, method, url, data=None, referer=None, allow_redirects=True):
        headers = {'Referer': referer} if referer else {}
        last_error = ''
        for attempt in range(self.retries + 1):
            try:
                response = self.session.request(
                    method, url, data=data, timeout=self.timeout,
                    headers=headers, allow_redirects=allow_redirects)
            except requests.RequestException as error:
                last_error = '%s: %s' % (type(error).__name__, error)
            else:
                response.encoding = 'utf-8'
                # A broken page kills the session, so retrying is pointless.
                if looks_broken(response.text):
                    self.is_broken = True
                    raise DkkdBroken("Cổng trả trang lỗi.")
                if response.status_code < 400 and not looks_busy(response.text):
                    return response
                last_error = ('HTTP %s' % response.status_code
                              if response.status_code >= 400 else 'portal overload')
            _logger.info("Portal did not answer (%s), attempt %s/%s",
                         last_error, attempt + 1, self.retries + 1)
            if attempt < self.retries:
                time.sleep(self.retry_delay)
        raise DkkdError("Cổng bận hoặc không phản hồi.")

    def _get(self, url, referer=None, allow_redirects=True):
        return self._send('GET', url, referer=referer, allow_redirects=allow_redirects)

    def _post(self, url, data, referer=None, allow_redirects=True):
        return self._send('POST', url, data=data, referer=referer,
                          allow_redirects=allow_redirects)

    @staticmethod
    def _hidden_fields(root):
        return {element.get('name'): (element.get('value') or '')
                for element in root.xpath('//input[@type="hidden"]')
                if element.get('name')}

    @staticmethod
    def _form_fields(html_text, form_id=CATALOG_FORM_ID):
        _require_libs()
        root = lxml_html.fromstring(html_text)
        forms = root.xpath('//form[@id=$form_id]', form_id=form_id) or root.xpath('//form')
        if not forms:
            return {}
        fields = {}
        for element in forms[0].xpath('.//input | .//select | .//textarea'):
            name = element.get('name')
            if not name:
                continue
            kind = (element.get('type') or element.tag).lower()
            if kind in ('submit', 'button', 'image', 'file', 'reset',
                        'checkbox', 'radio'):
                continue
            if element.tag == 'select':
                selected = element.xpath('.//option[@selected]/@value') or \
                    element.xpath('.//option/@value')
                fields[name] = selected[0] if selected else ''
            elif element.tag == 'textarea':
                fields[name] = element.text or ''
            else:
                fields[name] = element.get('value') or ''
        return fields

    def open_catalog(self, force=False):
        # A warm page is reused unless the caller forces a reload.
        fresh = (self.catalog_fields and self.catalog_url
                 and time.monotonic() - self.catalog_opened_at < CATALOG_TTL)
        if fresh and not force:
            return ''
        root = self._get(DEFAULT_PAGE_URL)
        data = self._hidden_fields(lxml_html.fromstring(root.text))
        data['__EVENTTARGET'] = CATALOG_POSTBACK_TARGET
        data['__EVENTARGUMENT'] = ''
        posted = self._post(str(root.url), data, referer=str(root.url),
                            allow_redirects=False)
        location = posted.headers.get('Location', '')
        if not location:
            raise DkkdError("Cổng không mở được trang tra cứu.")
        page = self._get(urljoin(INFO_ORIGIN, location), referer=str(root.url))
        self.catalog_url = str(page.url)
        self.catalog_fields = self._form_fields(page.text)
        self.catalog_opened_at = time.monotonic()
        self.captcha_sitekey = find_sitekey(page.text)
        return page.text

    def submit_filter(self, term, token):
        if not self.catalog_fields:
            raise DkkdError("Chưa mở được form tra cứu của cổng")
        data = dict(self.catalog_fields)
        by_code = is_tax_code(term)
        data[CATALOG_TAX_FIELD] = term if by_code else ''
        data[CATALOG_NAME_FIELD] = '' if by_code else term
        data[CATALOG_FILTER_BUTTON] = CATALOG_FILTER_VALUE
        data['g-recaptcha-response'] = token
        data['grecaptcha-response'] = token
        response = self._post(self.catalog_url, data, referer=self.catalog_url)
        fresh_fields = self._form_fields(response.text)
        if fresh_fields:
            self.catalog_fields = fresh_fields
            self.catalog_opened_at = time.monotonic()
        return response

    @staticmethod
    def _result_row_targets(html_text, term=''):
        _require_libs()
        root = lxml_html.fromstring(html_text)
        table = root.xpath('//table[@id=$table_id]', table_id=CATALOG_RESULT_TABLE)
        scope = table[0] if table else root
        wanted = re.sub(r'\D', '', term or '')
        targets = []
        for row in scope.xpath('.//tr'):
            found = re.findall(r"__doPostBack\('([^']+)'\s*,\s*'([^']*)'\)",
                               lxml_html.tostring(row, encoding='unicode'))
            if not found:
                continue
            digits = re.sub(r'\D', '', row.text_content() or '')
            rank = 0 if wanted and wanted in digits else 1
            targets.extend((rank, target, argument) for target, argument in found)
        targets.sort(key=lambda item: item[0])
        return [(target, argument) for _rank, target, argument in targets[:3]]

    @staticmethod
    def _row_matches(html_text, term):
        wanted = re.sub(r'\D', '', term or '')
        if not wanted:
            return True
        _require_libs()
        root = lxml_html.fromstring(html_text)
        table = root.xpath('//table[@id=$table_id]', table_id=CATALOG_RESULT_TABLE)
        scope = table[0] if table else root
        return wanted in re.sub(r'\D', '', scope.text_content() or '')

    def read_status_from_results(self, html_text, page_url='', term=''):
        page_url = page_url or self.catalog_url
        info = parse_basic_info(html_text, page_url)
        if info.status_text or not self._row_matches(html_text, term):
            return info
        for target, argument in self._result_row_targets(html_text, term):
            data = self._form_fields(html_text)
            data['__EVENTTARGET'] = target
            data['__EVENTARGUMENT'] = argument
            posted = self._post(page_url, data, referer=page_url)
            info = parse_basic_info(posted.text, str(posted.url))
            if info.status_text:
                return info
        return info

    def fetch_basic_info(self, enterprise, solver=None):
        term = (enterprise.tax_code or enterprise.name or '').strip()
        if not term:
            raise DkkdError("Cần mã số thuế hoặc tên doanh nghiệp")
        try:
            return self._fetch(term, solver)
        except DkkdBroken:
            # Name lookups break inside the portal, so name the real cause.
            raise DkkdBroken(broken_message(term))

    def _fetch(self, term, solver):
        started = time.monotonic()
        self.open_catalog()
        opened = time.monotonic()
        if not self.captcha_sitekey:
            raise DkkdError("Trang cổng không có reCAPTCHA.")

        solved = opened
        response = info = None
        reused = False

        if self.captcha_is_reusable:
            reused = True
            # Detail page blocks new searches, so reopen the form.
            self.open_catalog(force=True)
            solved = time.monotonic()
            response = self.submit_filter(term, self.captcha_token)
            info = self.read_status_from_results(
                response.text, str(response.url), term)
            if info.status_text and matches_term(info, term):
                self.remember_captcha(self.captcha_token)
            else:
                self.forget_captcha()
                response = info = None

        # First lookup of the session, or the cached pass was refused.
        if info is None:
            if solver is None:
                raise CaptchaNeeded("Cần captcha. Dán khóa dịch vụ ở "
                                    "Cài đặt → Tra cứu đăng ký doanh nghiệp.")
            token = solver.solve_recaptcha(self.captcha_sitekey, self.catalog_url)
            solved = time.monotonic()
            response = self.submit_filter(term, token)
            info = self.read_status_from_results(
                response.text, str(response.url), term)
            if info.status_text:
                self.remember_captcha(token)

        _logger.info(
            "Lookup %s: form open %.1fs, %s %.1fs, read result %.1fs", term,
            opened - started, 'reopened form, reused pass' if reused
            else 'captcha solved', solved - opened, time.monotonic() - solved)
        if not info.status_text:
            if not has_result_rows(response.text) or not self._row_matches(
                    response.text, term):
                raise DkkdNotFound(
                    "Cổng không tra được '%s'. Chi nhánh thì dùng mã công ty mẹ."
                    % term)
            raise DkkdError("Cổng không trả tình trạng cho '%s'." % term)
        if not matches_term(info, term):
            raise DkkdError("Cổng trả về doanh nghiệp khác '%s'." % term)
        return info
