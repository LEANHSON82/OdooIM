from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home
import logging

_logger = logging.getLogger(__name__)


class ImHome(Home):

    @http.route()
    def web_client(self, s_action=None, **kw):
        """Re-sync the theme cookie with the stored user setting.

        Needed when the user logs in from another browser, where the
        cookie is missing or still holds someone else's choice.
        """
        response = super().web_client(s_action, **kw)
        try:
            if request.session.uid:
                color_scheme = request.env['ir.http'].color_scheme()
                if color_scheme:
                    response.set_cookie('color_scheme', color_scheme, max_age=365 * 24 * 3600)
                else:
                    response.set_cookie('color_scheme', '', max_age=0)
        except Exception:
            # Theming must never block access to the backend.
            _logger.exception("im_web_backend_lab: failed to set color_scheme cookie")
        return response
