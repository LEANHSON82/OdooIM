from odoo import fields, models

from odoo.addons.im_business_status_checker.tools import captcha_solver

class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    im_captcha_provider = fields.Selection(
        selection=[('none', 'Không dùng')] + captcha_solver.CAPTCHA_PROVIDERS,
        string='Dịch vụ captcha', default='none',
        config_parameter='im_business_status_checker.captcha_provider')
    im_captcha_api_key = fields.Char(
        string='Khóa dịch vụ', config_parameter='im_business_status_checker.captcha_api_key')
    im_captcha_timeout = fields.Integer(
        string='Chờ tối đa (giây)', default=180,
        config_parameter='im_business_status_checker.captcha_timeout')
    im_batch_size = fields.Integer(
        string='Số doanh nghiệp mỗi lô', default=10,
        help='Số bản ghi xử lý mỗi lượt. Đặt lớn quá cổng dễ chặn.',
        config_parameter='im_business_status_checker.batch_size')
    im_request_delay = fields.Integer(
        string='Nghỉ giữa hai lần gọi (giây)', default=3,
        help='Thời gian nghỉ giữa hai doanh nghiệp trong cùng một lô.',
        config_parameter='im_business_status_checker.request_delay')
    im_portal_timeout = fields.Integer(
        string='Chờ cổng mỗi request (giây)', default=45,
        help='Số giây chờ cổng trả lời một request. Cổng chậm thì tăng lên.',
        config_parameter='im_business_status_checker.portal_timeout')
    im_portal_retries = fields.Integer(
        string='Số lần thử lại', default=1,
        help='Số lần gọi lại khi cổng bận. Tăng thì chậm hơn.',
        config_parameter='im_business_status_checker.portal_retries')
    im_portal_proxy = fields.Char(
        string='Proxy cho cổng',
        help='Dạng http://tài-khoản:mật-khẩu@host:port. Điền khi máy chủ ở nước '
             'ngoài bị cổng chặn; nên dùng proxy có IP Việt Nam.',
        config_parameter='im_business_status_checker.portal_proxy')
