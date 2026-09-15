from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home
import logging

_logger = logging.getLogger(__name__)


class ImHome(Home):

    @http.route()
    def web_client(self, s_action=None, **kw):
        response = super().web_client(s_action, **kw)
        try:
            if request.session.uid:
                color_scheme = request.env['ir.http'].color_scheme()
                if color_scheme:
                    response.set_cookie('color_scheme', color_scheme, max_age=365 * 24 * 3600)
                else:
                    response.set_cookie('color_scheme', '', max_age=0)
        except Exception:
            _logger.exception("im_web_backend_lab: failed to set color_scheme cookie")
        return response

    @http.route('/favicon.ico', type='http', auth='public', sitemap=False)
    def favicon(self):
        return request.redirect('/web/static/img/favicon.ico', code=301)
