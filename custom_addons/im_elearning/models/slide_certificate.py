import logging
import secrets

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# No 0/O and no 1/I: people retype this code from a printed sheet.
SUFFIX_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
SUFFIX_LENGTH = 6


class SlideCertificate(models.Model):
    """A certificate anyone can verify from the code printed on it."""
    _name = 'slide.certificate'
    _description = 'Chứng chỉ eLearning'
    _order = 'date_issued desc, id desc'
    _rec_name = 'code'

    code = fields.Char(
        'Mã chứng chỉ', required=True, readonly=True, copy=False, index=True,
        default=lambda self: _('Cấp tự động'))
    partner_id = fields.Many2one(
        'res.partner', string='Học viên', required=True, readonly=True,
        ondelete='cascade', index=True)
    channel_id = fields.Many2one(
        'slide.channel', string='Khoá học', required=True, readonly=True,
        ondelete='cascade', index=True)
    date_issued = fields.Datetime(
        'Ngày cấp', required=True, readonly=True,
        default=fields.Datetime.now)
    user_input_id = fields.Many2one(
        'survey.user_input', string='Bài thi', readonly=True, ondelete='set null',
        help="Lượt thi đã đỗ dẫn tới việc cấp chứng chỉ này.")
    scoring_percentage = fields.Float(
        'Điểm (%)', related='user_input_id.scoring_percentage', store=True,
        readonly=True)

    is_revoked = fields.Boolean('Đã thu hồi', default=False, readonly=True, copy=False)
    revoke_reason = fields.Char('Lý do thu hồi', readonly=True, copy=False)
    revoke_date = fields.Datetime('Ngày thu hồi', readonly=True, copy=False)
    revoke_uid = fields.Many2one('res.users', string='Người thu hồi', readonly=True, copy=False)

    resume_line_id = fields.Many2one(
        'hr.resume.line', string='Dòng hồ sơ nhân viên', readonly=True,
        ondelete='set null', copy=False,
        help="Dòng tương ứng trong hồ sơ HR của nhân viên, nếu học viên là nhân sự công ty.")

    verify_url = fields.Char('Liên kết tra cứu', compute='_compute_verify_url')
    verify_page_url = fields.Char(
        'Trang tra cứu', compute='_compute_verify_url')

    mail_sent_date = fields.Datetime(
        'Đã gửi cho học viên', readonly=True, copy=False,
        help="Thời điểm gửi thư kèm bản chứng chỉ. Để trống nghĩa là chưa gửi "
             "được — bấm nút Gửi cho học viên để gửi lại.")

    _unique_code = models.Constraint('UNIQUE(code)', 'Mã chứng chỉ phải là duy nhất.')
    _unique_partner_channel = models.Constraint(
        'UNIQUE(partner_id, channel_id)',
        'Mỗi học viên chỉ được cấp một chứng chỉ cho mỗi khoá học.',
    )

    def _compute_verify_url(self):
        """Both the direct result link and the bare lookup page."""
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', '')
        for certificate in self:
            certificate.verify_page_url = '%s/certificate/verify' % base_url
            if certificate.code and certificate.id:
                certificate.verify_url = '%s/certificate/verify/%s' % (
                    base_url, certificate.code)
            else:
                certificate.verify_url = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Readable serial plus a random suffix: counting up must not
            # reveal somebody else's certificate.
            if not vals.get('code') or vals['code'] == _('Cấp tự động'):
                serial = self.env['ir.sequence'].next_by_code('slide.certificate')
                vals['code'] = '%s-%s' % (serial, self._generate_code_suffix())
        certificates = super().create(vals_list)
        certificates._sync_hr_resume_line()
        return certificates

    @api.model
    def _generate_code_suffix(self):
        """Random tail of the code, so counting up reveals nobody else's."""
        return ''.join(
            secrets.choice(SUFFIX_ALPHABET) for _index in range(SUFFIX_LENGTH))

    def _get_verify_token(self):
        """A signed string bound to the code, for anywhere that needs one."""
        self.ensure_one()
        return tools.hmac(self.env(su=True), 'im_elearning-certificate-verify', self.code)

    @api.model
    def _map_by_learner_and_course(self, partners, channels):
        """``{(partner_id, channel_id): certificate}`` for the given pairs.

        Shared by every place that has to decide whether someone already holds
        a certificate for a course, so the lookup is written once.
        """
        certificates = self.sudo().search([
            ('partner_id', 'in', partners.ids),
            ('channel_id', 'in', channels.ids),
        ])
        return {
            (certificate.partner_id.id, certificate.channel_id.id): certificate
            for certificate in certificates
        }

    @api.model
    def _issue_for_membership(self, membership, user_input=None):
        """Issue a certificate for a passing enrolment, never twice."""
        channel = membership.channel_id
        if not channel.certificate_enabled:
            return self.browse()
        existing = self._map_by_learner_and_course(membership.partner_id, channel)
        if existing:
            return next(iter(existing.values()))
        certificate = self.sudo().create({
            'partner_id': membership.partner_id.id,
            'channel_id': channel.id,
            'user_input_id': user_input.id if user_input else False,
        })
        certificate._send_issued_email()
        return certificate

    @api.model
    def _backfill_missing(self):
        """Issue certificates to learners who passed before install."""
        memberships = self.env['slide.channel.partner'].sudo().search([
            ('survey_certification_success', '=', True),
            ('channel_id.certificate_enabled', '=', True),
        ])
        already_held = self._map_by_learner_and_course(
            memberships.partner_id, memberships.channel_id)
        created = self.browse()
        for membership in memberships:
            if (membership.partner_id.id, membership.channel_id.id) in already_held:
                continue
            created |= self._issue_for_membership(membership)
        return created

    @api.model
    def action_backfill_missing(self):
        """Issue certificates to learners who passed before the install."""
        created = self._backfill_missing()
        if created:
            message = _(
                "Đã cấp %(count)s chứng chỉ và gửi thư cho học viên: %(codes)s",
                count=len(created), codes=', '.join(created.mapped('code')))
        else:
            message = _("Không có học viên nào đã đỗ mà còn thiếu chứng chỉ.")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cấp chứng chỉ còn thiếu'),
                'message': message,
                'type': 'success' if created else 'warning',
                'sticky': bool(created),
            },
        }

    def action_revoke(self):
        """Open the revoke wizard — for a mistaken issue or proven cheating."""
        self.ensure_one()
        if self.is_revoked:
            raise UserError(_("Chứng chỉ %s đã bị thu hồi trước đó.", self.code))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Thu hồi chứng chỉ'),
            'res_model': 'slide.certificate.revoke',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_certificate_id': self.id},
        }

    def action_restore(self):
        """Undo a revocation and put the HR resume line back."""
        self.ensure_one()
        self.sudo().write({
            'is_revoked': False,
            'revoke_reason': False,
            'revoke_date': False,
            'revoke_uid': False,
        })
        self._sync_hr_resume_line()

    def _do_revoke(self, reason):
        """Mark as revoked and drop the HR resume line."""
        self.sudo().write({
            'is_revoked': True,
            'revoke_reason': reason,
            'revoke_date': fields.Datetime.now(),
            'revoke_uid': self.env.user.id,
        })
        self.resume_line_id.sudo().unlink()

    def _send_issued_email(self):
        """Email the learner a copy carrying the verifiable code."""
        template = self.env['slide.channel']._im_get_mail_template('certificate_issued')
        if not template:
            _logger.warning(
                "im_elearning: no mail template for issued certificates, not sending "
                "%s. Is im_theme installed?", ', '.join(self.mapped('code')))
            return self.browse()
        sent = self.browse()
        for certificate in self:
            if certificate.is_revoked or not certificate.partner_id.email:
                continue
            try:
                template.sudo().send_mail(certificate.id, force_send=False)
            except Exception:
                _logger.exception(
                    "im_elearning: could not send certificate %s to %s",
                    certificate.code, certificate.partner_id.display_name)
                continue
            sent |= certificate
        sent.sudo().write({'mail_sent_date': fields.Datetime.now()})
        return sent

    def action_send_email(self):
        """Send again, by hand, after an automatic send failed."""
        self.ensure_one()
        if self.is_revoked:
            raise UserError(_(
                "Chứng chỉ %s đã bị thu hồi, không gửi lại được.", self.code))
        if not self.partner_id.email:
            raise UserError(_(
                "Học viên %s chưa có địa chỉ email.", self.partner_id.display_name))
        template = self.env['slide.channel']._im_get_mail_template('certificate_issued')
        if not template:
            raise UserError(_(
                "Chưa có mẫu thư gửi chứng chỉ. Cài module IM Theme trước."))
        template.sudo().send_mail(self.id, force_send=False)
        self.sudo().mail_sent_date = fields.Datetime.now()
        return True

    def _find_employee(self, partner):
        """The employee behind a learner, or an empty recordset."""
        Employee = self.env['hr.employee'].sudo()
        employee = Employee.search([('work_contact_id', '=', partner.id)], limit=1)
        return employee or Employee.search(
            [('user_id.partner_id', '=', partner.id)], limit=1)

    def _sync_hr_resume_line(self):
        """Record the certificate on the employee's resume, for HR to find."""
        line_type = self.env.ref(
            'im_elearning.resume_type_elearning_certificate', raise_if_not_found=False)
        for certificate in self:
            if certificate.is_revoked or certificate.resume_line_id:
                continue
            employee = self._find_employee(certificate.partner_id)
            if not employee:
                continue
            certificate.sudo().resume_line_id = self.env['hr.resume.line'].sudo().create({
                'employee_id': employee.id,
                'name': certificate.channel_id.name,
                'date_start': fields.Date.to_date(certificate.date_issued),
                'line_type_id': line_type.id if line_type else False,
                'description': _('Chứng chỉ %s', certificate.code),
                'external_url': certificate.verify_url,
            })


class SlideCertificateRevoke(models.TransientModel):
    _name = 'slide.certificate.revoke'
    _description = 'Thu hồi chứng chỉ'

    certificate_id = fields.Many2one(
        'slide.certificate', string='Chứng chỉ', required=True, ondelete='cascade')
    reason = fields.Char('Lý do', required=True)

    def action_confirm(self):
        """Revoke with the typed reason, then close the dialog."""
        self.ensure_one()
        self.certificate_id._do_revoke(self.reason)
        return {'type': 'ir.actions.act_window_close'}
