from odoo import http
from odoo.http import request


class ImCertificateController(http.Controller):
    """The public certificate lookup page."""

    @http.route('/certificate/verify', type='http', auth='public', website=True, sitemap=False)
    def certificate_verify_form(self, code=None, **kwargs):
        """The code entry box, for someone holding a printed certificate."""
        if code and code.strip():
            return request.redirect(request.env['ir.http']._url_lang(
                '/certificate/verify/%s' % code.strip()))
        return request.render('im_elearning.certificate_verify_form', {'code': ''})

    @http.route('/certificate/verify/<path:code>', type='http', auth='public',
                website=True, sitemap=False)
    def certificate_verify(self, code, **kwargs):
        """Look up one certificate."""
        certificate = request.env['slide.certificate'].sudo().search(
            [('code', '=', code.strip())], limit=1)

        if not certificate:
            return request.render('im_elearning.certificate_verify_result', {
                'found': False,
                'code': code,
            })

        return request.render('im_elearning.certificate_verify_result', {
            'found': True,
            'code': certificate.code,
            'partner_name': certificate.partner_id.name,
            'channel_name': certificate.channel_id.name,
            'date_issued': certificate.date_issued,
            'is_revoked': certificate.is_revoked,
            'company_name': certificate.channel_id.website_id.company_id.name
            or request.env.company.name,
        })
