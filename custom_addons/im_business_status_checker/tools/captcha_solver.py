import logging
import time

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

CAPTCHA_PROVIDERS = [
    ('2captcha', '2Captcha'),
    ('capsolver', 'Capsolver'),
    ('anticaptcha', 'Anti-Captcha'),
]

_TASK_APIS = {
    # Capsolver and Anti-Captcha share one protocol.
    'capsolver': ('https://api.capsolver.com', 'ReCaptchaV2TaskProxyless'),
    'anticaptcha': ('https://api.anti-captcha.com', 'RecaptchaV2TaskProxyless'),
}
_TWOCAPTCHA_IN = 'https://2captcha.com/in.php'
_TWOCAPTCHA_RES = 'https://2captcha.com/res.php'


class CaptchaSolveError(Exception):
    pass


class CaptchaSolver:

    def __init__(self, provider, api_key, timeout=180, poll_interval=3):
        self.provider = (provider or '').strip().lower()
        self.api_key = (api_key or '').strip()
        self.timeout = max(int(timeout or 180), 30)
        self.poll_interval = max(int(poll_interval or 3), 2)
        if self.provider not in dict(CAPTCHA_PROVIDERS):
            raise CaptchaSolveError(
                "Dịch vụ captcha không hợp lệ: %s" % (provider or 'trống'))
        if not self.api_key:
            raise CaptchaSolveError(
                "Chưa cấu hình khóa dịch vụ %s" % self.provider)

    def solve_recaptcha(self, sitekey, page_url):
        if not sitekey or not page_url:
            raise CaptchaSolveError("Thiếu khóa trang hoặc địa chỉ captcha")
        _logger.info("Sending captcha %s to %s", sitekey[:20], self.provider)
        if requests is None:
            raise CaptchaSolveError("Thiếu thư viện Python 'requests'")
        if self.provider == '2captcha':
            return self._solve_2captcha(sitekey, page_url)
        # Other providers accept a task and are polled the same way.
        base, task_type = _TASK_APIS[self.provider]
        return self._solve_task_api(base, task_type, sitekey, page_url)

    def _solve_2captcha(self, sitekey, page_url):
        body = self._request('POST', _TWOCAPTCHA_IN, data={
            'key': self.api_key, 'method': 'userrecaptcha',
            'googlekey': sitekey, 'pageurl': page_url, 'json': 1,
        })
        if body.get('status') != 1:
            raise CaptchaSolveError("2captcha từ chối: %s" % body.get('request'))
        task_id = body.get('request')
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            body = self._request('GET', _TWOCAPTCHA_RES, params={
                'key': self.api_key, 'action': 'get', 'id': task_id, 'json': 1})
            if body.get('status') == 1:
                token = body.get('request')
                if token and not token.startswith('ERROR'):
                    return token
                raise CaptchaSolveError("2captcha trả lỗi: %s" % token)
            if body.get('request') != 'CAPCHA_NOT_READY':
                raise CaptchaSolveError("2captcha trả lỗi: %s" % body.get('request'))
        raise CaptchaSolveError("2captcha không trả kết quả trong %ss" % self.timeout)

    def _solve_task_api(self, base, task_type, sitekey, page_url):
        task = {'type': task_type, 'websiteURL': page_url, 'websiteKey': sitekey}
        created = self._request('POST', base + '/createTask', json={
            'clientKey': self.api_key, 'task': task})
        if created.get('errorId'):
            raise CaptchaSolveError("%s trả lỗi: %s" % (
                base, created.get('errorDescription') or created.get('errorCode')))
        task_id = created.get('taskId')
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            body = self._request('POST', base + '/getTaskResult', json={
                'clientKey': self.api_key, 'taskId': task_id})
            if body.get('errorId'):
                raise CaptchaSolveError("%s trả lỗi: %s" % (
                    base, body.get('errorDescription') or body.get('errorCode')))
            if body.get('status') == 'ready':
                token = (body.get('solution') or {}).get('gRecaptchaResponse')
                if token:
                    return token
                raise CaptchaSolveError("%s không trả token" % base)
        raise CaptchaSolveError("%s không trả kết quả trong %ss" % (base, self.timeout))

    @staticmethod
    def _request(method, url, **kwargs):
        response = requests.request(method, url, timeout=60, **kwargs)
        if response.status_code >= 400:
            raise CaptchaSolveError("%s trả mã lỗi %s" % (url, response.status_code))
        try:
            return response.json()
        except ValueError:
            raise CaptchaSolveError("%s trả dữ liệu không đọc được" % url)
