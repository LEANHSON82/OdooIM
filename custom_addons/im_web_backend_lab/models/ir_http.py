from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def color_scheme(self):
        """Pick the theme: cookie first, then user setting, then system.

        The cookie wins because the dark SCSS lives in its own bundle and
        the server must choose the bundle before any JS runs.
        """
        if request and hasattr(request, 'httprequest'):
            cookie = request.httprequest.cookies.get('color_scheme')
            if cookie in ('light', 'dark'):
                return cookie
        if request and request.session.uid:
            try:
                settings = request.env['res.users.settings']._find_or_create_for_user(
                    request.env.user,
                )
                if settings.x_color_scheme and settings.x_color_scheme != 'system':
                    return settings.x_color_scheme
            except Exception:
                pass
        return super().color_scheme()

    def session_info(self):
        result = super().session_info()
        result['color_scheme'] = self.color_scheme()
        return result

    # Drop the cookie on logout, or the next user on this browser
    # inherits the previous one's theme.
    @classmethod
    def _post_logout(cls):
        res = super()._post_logout()
        if request and hasattr(request, 'future_response'):
            request.future_response.set_cookie('color_scheme', '', max_age=0)
        return res