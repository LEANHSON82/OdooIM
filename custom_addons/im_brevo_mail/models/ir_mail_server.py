"""Send outgoing mail through the Brevo HTTP API instead of SMTP.

Enabled as soon as a key is found, either in the ``brevo.api_key`` system
parameter or the ``BREVO_API_KEY`` environment variable. Needed on hosts
that block outbound SMTP, such as Railway; the HTTP API uses port 443.

With no key everything falls back to stock Odoo SMTP.
"""

import base64
import logging
import os
from email.utils import getaddresses, parseaddr

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class _BrevoSession:
    """Fake SMTP session so mail.mail._send can still call quit/close."""

    def quit(self):
        pass

    def close(self):
        pass


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    def _brevo_api_key(self):
        """System parameter first, environment second; empty means SMTP."""
        key = (
            self.env['ir.config_parameter'].sudo().get_param('brevo.api_key')
            or os.environ.get('BREVO_API_KEY')
            or ''
        )
        return key.strip()

    def _connect__(self, *args, **kwargs):  # noqa: PLW3201
        # Brevo on: skip the real SMTP connect, hand back a fake session.
        if self._brevo_api_key():
            return _BrevoSession()
        return super()._connect__(*args, **kwargs)

    def send_email(self, message, *args, **kwargs):
        api_key = self._brevo_api_key()
        if api_key:
            return self._send_via_brevo(message, api_key)
        return super().send_email(message, *args, **kwargs)

    def _send_via_brevo(self, message, api_key):
        """Translate a python email Message into one Brevo API call."""
        # Sender must be verified on the Brevo side, so let config win
        # over whatever From header Odoo built.
        icp = self.env['ir.config_parameter'].sudo()
        from_name, from_email = parseaddr(message.get('From') or '')
        sender_email = (
            icp.get_param('brevo.sender_email')
            or os.environ.get('BREVO_SENDER_EMAIL')
            or from_email
        )
        sender_name = (
            icp.get_param('brevo.sender_name')
            or os.environ.get('BREVO_SENDER_NAME')
            or from_name
            or sender_email
        )
        if not sender_email:
            raise UserError(_("Brevo: thiếu email người gửi (sender)."))

        to_addrs = [e for _n, e in getaddresses(message.get_all('To', [])) if e]
        cc_addrs = [e for _n, e in getaddresses(message.get_all('Cc', [])) if e]
        bcc_addrs = [e for _n, e in getaddresses(message.get_all('Bcc', [])) if e]
        _rn, reply_email = parseaddr(message.get('Reply-To') or '')
        subject = message.get('Subject') or ''

        if not to_addrs:
            raise UserError(_("Brevo: không tìm thấy người nhận (To)."))

        # Walk the MIME tree once, keeping the first html and text part
        # plus every attachment; Brevo wants them as separate JSON keys.
        html_body = text_body = None
        attachments = []
        if message.is_multipart():
            for part in message.walk():
                if part.is_multipart():
                    continue
                dispo = part.get_content_disposition()
                ctype = part.get_content_type()
                if dispo == 'attachment':
                    payload = part.get_payload(decode=True) or b''
                    attachments.append({
                        'name': part.get_filename() or 'attachment',
                        'content': base64.b64encode(payload).decode(),
                    })
                elif ctype == 'text/html' and html_body is None:
                    html_body = (part.get_payload(decode=True) or b'').decode(
                        part.get_content_charset() or 'utf-8', 'replace')
                elif ctype == 'text/plain' and text_body is None:
                    text_body = (part.get_payload(decode=True) or b'').decode(
                        part.get_content_charset() or 'utf-8', 'replace')
        else:
            payload = (message.get_payload(decode=True) or b'').decode(
                message.get_content_charset() or 'utf-8', 'replace')
            if message.get_content_type() == 'text/html':
                html_body = payload
            else:
                text_body = payload

        body = {
            'sender': {'email': sender_email, 'name': sender_name},
            'to': [{'email': e} for e in to_addrs],
            'subject': subject,
        }
        if html_body:
            body['htmlContent'] = html_body
        if text_body:
            body['textContent'] = text_body
        # Brevo rejects a mail with no body at all.
        if not html_body and not text_body:
            body['textContent'] = ' '
        if cc_addrs:
            body['cc'] = [{'email': e} for e in cc_addrs]
        if bcc_addrs:
            body['bcc'] = [{'email': e} for e in bcc_addrs]
        if reply_email:
            body['replyTo'] = {'email': reply_email}
        if attachments:
            body['attachment'] = attachments

        try:
            resp = requests.post(
                BREVO_API_URL, json=body, timeout=30,
                headers={
                    'api-key': api_key,
                    'accept': 'application/json',
                    'content-type': 'application/json',
                },
            )
        except Exception as err:
            raise UserError(_("Brevo API request lỗi: %s") % err)

        # 202 means queued, which is the normal answer for transactional mail.
        if resp.status_code not in (200, 201, 202):
            raise UserError(_(
                "Brevo API lỗi %(code)s: %(text)s",
                code=resp.status_code, text=resp.text[:500]))

        _logger.info("Đã gửi email qua Brevo API tới %s", to_addrs)
        return message.get('Message-Id') or (resp.json() or {}).get('messageId') or 'brevo'
