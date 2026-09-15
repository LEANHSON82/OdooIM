from odoo.tests import tagged

from odoo.addons.im_elearning.tests.common import ImElearningCommon


@tagged('post_install', '-at_install')
class TestCertificateReport(ImElearningCommon):

    def _certificate(self):
        return self.env['slide.certificate'].create({
            'partner_id': self.partner_student.id,
            'channel_id': self.channel.id,
        })

    def _html(self, certificate):
        html, _kind = self.env['ir.actions.report']._render_qweb_html(
            'im_theme.report_certificate', certificate.ids)
        return html.decode()

    def test_report_is_bound_to_certificates(self):
        action = self.env.ref('im_theme.action_report_certificate')
        self.assertEqual(action.model, 'slide.certificate')
        self.assertEqual(action.binding_model_id.model, 'slide.certificate')
        self.assertEqual(action.paperformat_id.orientation, 'Landscape')

    def test_report_shows_code_learner_course_and_qr(self):
        certificate = self._certificate()
        html = self._html(certificate)
        for text in (certificate.code, self.partner_student.name, self.channel.name,
                     'barcode_type=QR'):
            self.assertIn(text, html)
        self.assertNotIn('THU HỒI', html)

    def test_revoked_certificate_is_stamped(self):
        certificate = self._certificate()
        certificate._do_revoke('Issued by mistake')
        self.assertIn('ĐÃ BỊ THU HỒI', self._html(certificate))

    def test_certificate_mail_attaches_this_report(self):
        template = self.env.ref('im_theme.mail_template_certificate_issued')
        self.assertIn(self.env.ref('im_theme.action_report_certificate'),
                      template.report_template_ids)
