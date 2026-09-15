from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import ImElearningCommon, create_exam, submit_exam


@tagged('post_install', '-at_install')
class TestCertificate(ImElearningCommon):

    def _make_certificate(self, partner=None):
        return self.env['slide.certificate'].create({
            'partner_id': (partner or self.partner_student).id,
            'channel_id': self.channel.id,
        })

    def test_code_follows_sequence_not_database_id(self):
        """The code must read CERT/<year>/<serial>, not a table id as in CE."""
        certificate = self._make_certificate()
        self.assertTrue(certificate.code.startswith('CERT/'))
        self.assertNotEqual(certificate.code, str(certificate.id))
        parts = certificate.code.split('/')
        self.assertEqual(len(parts), 3)
        serial, suffix = parts[2].split('-')
        self.assertEqual(len(serial), 5, "The serial must be padded to 5 digits")
        self.assertEqual(len(suffix), 6, "The code must carry a random part against enumeration")

    def test_code_is_unique(self):
        first = self._make_certificate()
        second = self._make_certificate(self.partner_other)
        self.assertNotEqual(first.code, second.code)

    def test_one_certificate_per_partner_and_channel(self):
        """Never issue twice to the same person for the same course."""
        membership = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': self.partner_student.id,
        })
        first = self.env['slide.certificate']._issue_for_membership(membership)
        second = self.env['slide.certificate']._issue_for_membership(membership)
        self.assertEqual(first, second, "Calling twice must return the same certificate")

    def test_not_issued_when_disabled_on_channel(self):
        self.channel.certificate_enabled = False
        membership = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': self.partner_student.id,
        })
        certificate = self.env['slide.certificate']._issue_for_membership(membership)
        self.assertFalse(certificate)

    def test_code_suffix_is_random(self):
        """Consecutive certificates must differ by more than the serial."""
        suffixes = {
            self._make_certificate(
                self.env['res.partner'].create({'name': 'Person %s' % i})
            ).code.split('-')[-1]
            for i in range(5)
        }
        self.assertEqual(len(suffixes), 5, "The random parts must differ")

    def test_verify_url_is_typable(self):
        """The lookup link holds only the code, so it can be typed by hand."""
        certificate = self._make_certificate()
        self.assertIn(certificate.code, certificate.verify_url)
        self.assertNotIn('token=', certificate.verify_url)

    def test_revoke_keeps_record(self):
        """Revoking keeps the record so the code stays lookupable."""
        certificate = self._make_certificate()
        code = certificate.code
        certificate._do_revoke('Cheating detected')

        self.assertTrue(certificate.exists(), "The record must survive so it stays lookupable")
        self.assertTrue(certificate.is_revoked)
        self.assertEqual(certificate.revoke_reason, 'Cheating detected')
        self.assertTrue(certificate.revoke_date)
        self.assertEqual(
            self.env['slide.certificate'].search([('code', '=', code)]), certificate)

    def test_revoke_twice_raises(self):
        certificate = self._make_certificate()
        certificate._do_revoke('Issued by mistake')
        with self.assertRaises(UserError):
            certificate.action_revoke()

    def test_no_expiry_field(self):
        """Certificates never expire: there is no validity period at all."""
        fields = self.env['slide.certificate']._fields
        for name in ('date_expiry', 'validity_months', 'date_end', 'is_expired'):
            self.assertNotIn(name, fields)

    def test_pushed_to_hr_resume(self):
        """Passing a course shows up on the employee resume straight away."""
        certificate = self._make_certificate()
        self.assertTrue(certificate.resume_line_id)
        self.assertEqual(certificate.resume_line_id.employee_id, self.employee)
        self.assertEqual(certificate.resume_line_id.name, self.channel.name)

    def test_hr_resume_line_removed_on_revoke(self):
        certificate = self._make_certificate()
        resume_line = certificate.resume_line_id
        self.assertTrue(resume_line.exists())
        certificate._do_revoke('Issued by mistake')
        self.assertFalse(resume_line.exists(),
                         "The HR resume reflects what is held now, not the issuing history")

    def test_no_hr_resume_for_external_learner(self):
        """An external learner has no hr.employee; skip, never raise."""
        certificate = self._make_certificate(self.partner_other)
        self.assertFalse(certificate.resume_line_id)

    def test_certificate_issued_through_real_exam_flow(self):
        """Walk CE's real path: submit exam, certificate, mail with code."""
        self._pass_exam(self.partner_student)

        certificate = self.env['slide.certificate'].sudo().search([
            ('partner_id', '=', self.partner_student.id),
            ('channel_id', '=', self.channel.id),
        ])
        self.assertEqual(len(certificate), 1,
                         "A passing submission must issue exactly one certificate")
        self.assertTrue(certificate.code.startswith('CERT/'))
        mail = self._mails_for(certificate)
        self.assertEqual(len(mail), 1, "The learner must be mailed")
        self.assertIn(certificate.code, mail.body_html,
                      "The mail must carry the lookup code, not CE's number")

    def test_certificate_issued_when_exam_passed(self):
        """The automatic issuing hook."""
        membership = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': self.partner_student.id,
        })
        self.assertFalse(self.env['slide.certificate'].search(
            [('partner_id', '=', self.partner_student.id)]))

        membership.survey_certification_success = True

        certificate = self.env['slide.certificate'].search(
            [('partner_id', '=', self.partner_student.id),
             ('channel_id', '=', self.channel.id)])
        self.assertEqual(len(certificate), 1)
        self.assertTrue(certificate.code.startswith('CERT/'))

    def test_exam_passed_twice_does_not_duplicate(self):
        membership = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': self.partner_student.id,
        })
        membership.survey_certification_success = True
        membership.write({'survey_certification_success': True})
        certificates = self.env['slide.certificate'].search(
            [('partner_id', '=', self.partner_student.id),
             ('channel_id', '=', self.channel.id)])
        self.assertEqual(len(certificates), 1)

    def _issue_via_membership(self, partner=None):
        membership = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': (partner or self.partner_student).id,
        })
        return self.env['slide.certificate']._issue_for_membership(membership)

    def _mails_for(self, certificate):
        """Mails go out through im_theme, which auto-installs with
        this module; the end-to-end tests below check they were sent."""
        return self.env['mail.mail'].search([
            ('model', '=', 'slide.certificate'),
            ('res_id', '=', certificate.id),
        ])

    def test_issue_without_a_theme_still_issues(self):
        """No theme, no mail template: the certificate is still issued and
        stays marked as unsent, the resend button says why."""
        Channel = type(self.env['slide.channel'])
        with patch.object(Channel, '_im_get_mail_template',
                          return_value=self.env['mail.template']):
            certificate = self._issue_via_membership()
            self.assertTrue(certificate.exists())
            self.assertFalse(certificate.mail_sent_date)
            with self.assertRaises(UserError):
                certificate.action_send_email()

    def test_resend_refused_for_revoked(self):
        certificate = self._issue_via_membership()
        certificate._do_revoke('Issued by mistake')
        with self.assertRaises(UserError):
            certificate.action_send_email()

    def test_resend_refused_without_address(self):
        partner = self.env['res.partner'].create({'name': 'No mailbox'})
        certificate = self._issue_via_membership(partner)
        with self.assertRaises(UserError):
            certificate.action_send_email()

    def _pass_exam(self, partner):
        """Build the full exam chain, submit it, and return the attempt."""
        return submit_exam(self.env, create_exam(self.env, self.channel), partner)

    def _mark_passed_before_module(self, partner):
        """Simulate an earlier passer: flag True, no certificate yet."""
        self.channel.certificate_enabled = False
        membership = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id, 'partner_id': partner.id})
        membership.survey_certification_success = True
        self.channel.certificate_enabled = True
        self.assertFalse(self.env['slide.certificate'].sudo().search([
            ('partner_id', '=', partner.id), ('channel_id', '=', self.channel.id)]))
        return membership

    def test_issued_even_when_ce_flag_already_set(self):
        """This is the bug that reached production."""
        self._mark_passed_before_module(self.partner_student)

        self._pass_exam(self.partner_student)

        certificate = self.env['slide.certificate'].sudo().search([
            ('partner_id', '=', self.partner_student.id),
            ('channel_id', '=', self.channel.id)])
        self.assertEqual(len(certificate), 1,
                         "Retaking must issue a certificate even with CE's flag already set")
        self.assertTrue(self._mails_for(certificate))

    def test_test_entry_does_not_issue(self):
        """The survey's Test button is not a real learner."""
        user_input = self._pass_exam(self.partner_other)
        self.env['slide.certificate'].sudo().search([
            ('partner_id', '=', self.partner_other.id)]).unlink()
        user_input.test_entry = True
        user_input._im_issue_certificates()
        self.assertFalse(self.env['slide.certificate'].sudo().search([
            ('partner_id', '=', self.partner_other.id),
            ('channel_id', '=', self.channel.id)]))

    def test_backfill_issues_for_earlier_passers(self):
        """Earlier passers who will not retake must still be covered."""
        self._mark_passed_before_module(self.partner_student)

        created = self.env['slide.certificate']._backfill_missing()

        self.assertEqual(len(created), 1)
        self.assertTrue(created.code.startswith('CERT/'))
        self.assertTrue(self._mails_for(created))

    def test_backfill_does_not_duplicate(self):
        self._mark_passed_before_module(self.partner_student)
        self.env['slide.certificate']._backfill_missing()
        again = self.env['slide.certificate']._backfill_missing()
        self.assertFalse(again, "A second run must issue nothing more")

    def test_verify_link_sits_on_the_courses_page(self):
        """The entry point sits just below the filter bar on /slides."""
        view = self.env.ref('im_elearning.courses_home_certificate_verify')
        self.assertEqual(view.inherit_id,
                         self.env.ref('website_slides.courses_home'))
        self.assertIn('action="/certificate/verify"', view.arch)
        self.assertIn('name="code"', view.arch)

    def _activate_vietnamese(self):
        """Activate vi_VN and load the module's translations."""
        self.env['res.lang']._activate_and_install_lang('vi_VN')
        self.env['ir.module.module'].search([
            ('name', '=', 'im_elearning'),
            ('state', '=', 'installed'),
        ])._update_translations(filter_lang='vi_VN')

    def test_verify_box_placeholder_is_translated(self):
        """Source string in English, Vietnamese coming from i18n/vi_VN.po."""
        self._activate_vietnamese()
        view = self.env.ref('im_elearning.courses_home_certificate_verify')
        self.assertIn('Verify a certificate', view.arch)
        self.assertIn(
            'Tra cứu chứng chỉ',
            view.with_context(lang='vi_VN').arch,
            "The Vietnamese translation must be loaded from i18n/vi_VN.po")

    def test_verify_page_url_has_no_code_in_it(self):
        """The entry page carries no code, so it can be typed by hand."""
        certificate = self._make_certificate()
        self.assertTrue(certificate.verify_page_url.endswith('/certificate/verify'))
        self.assertNotIn(certificate.code, certificate.verify_page_url)
        self.assertIn(certificate.code, certificate.verify_url)
