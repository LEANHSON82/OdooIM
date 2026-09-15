from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from odoo.addons.im_elearning.tests.common import (
    ImElearningCommon, create_exam, create_internal_user, create_portal_user,
    submit_exam,
)


@tagged('post_install', '-at_install')
class TestCertificateMail(ImElearningCommon):

    def _issue_via_membership(self, partner=None):
        membership = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': (partner or self.partner_student).id,
        })
        return self.env['slide.certificate']._issue_for_membership(membership)

    def _mails_for(self, certificate):
        return self.env['mail.mail'].search([
            ('model', '=', 'slide.certificate'),
            ('res_id', '=', certificate.id),
        ])

    def test_theme_provides_the_template(self):
        template = self.env['slide.channel']._im_get_mail_template('certificate_issued')
        self.assertEqual(
            template, self.env.ref('im_theme.mail_template_certificate_issued'))

    def test_email_carries_the_code(self):
        """Without the code in hand, page and QR are both useless."""
        certificate = self._issue_via_membership()
        mail = self._mails_for(certificate)
        self.assertEqual(len(mail), 1, "Issuing must send exactly one mail")
        self.assertIn(certificate.code, mail.body_html)
        self.assertTrue(certificate.mail_sent_date)

    def test_email_attaches_the_certificate(self):
        certificate = self._issue_via_membership()
        mail = self._mails_for(certificate)
        self.assertTrue(mail.attachment_ids, "The mail must attach the certificate")
        # Under --test-enable Odoo renders reports as HTML, so only the name is checked.
        self.assertTrue(mail.attachment_ids[0].name.startswith('Chung chi'),
                        "The attachment is the certificate report, named after its code")

    def test_header_names_the_course_not_the_model(self):
        """Odoo's stock layout opens with 'Your <model name>'; ours opens with
        the course."""
        certificate = self._issue_via_membership()
        body = self._mails_for(certificate).body_html
        self.assertIn('Chứng chỉ khoá học', body)
        self.assertIn(self.channel.name, body)
        self.assertNotIn('Your Chứng chỉ', body)
        self.assertNotIn('Powered by', body)

    def test_no_email_when_learner_has_no_address(self):
        partner = self.env['res.partner'].create({'name': 'No mailbox'})
        certificate = self._issue_via_membership(partner)
        self.assertTrue(certificate, "A missing email must not block issuing")
        self.assertFalse(certificate.mail_sent_date)
        self.assertFalse(self._mails_for(certificate))

    def test_issue_survives_mail_failure(self):
        template = type(self.env['mail.template'])
        with patch.object(template, 'send_mail', side_effect=ValueError('SMTP down')):
            certificate = self._issue_via_membership()
        self.assertTrue(certificate.exists(), "The certificate must survive a failed send")
        self.assertFalse(certificate.mail_sent_date,
                         "A failed send leaves it empty so it can be filtered and retried")

    def test_resend_stamps_the_date(self):
        partner = self.env['res.partner'].create({'name': 'Mailbox added later'})
        certificate = self._issue_via_membership(partner)
        self.assertFalse(certificate.mail_sent_date)
        partner.email = 'later@example.com'
        certificate.action_send_email()
        self.assertTrue(certificate.mail_sent_date)
        self.assertTrue(self._mails_for(certificate))

    def test_email_is_not_sent_in_the_learners_name(self):
        """A learner who passes triggers the issue themselves, so a sender
        taken from create_uid would be the learner writing to themselves."""
        trainer = create_internal_user(
            self.env, 'im_trainer_cert_mail', email='trainer@example.com')
        self.channel.user_id = trainer
        learner = create_portal_user(
            self.env, 'im_learner_cert_mail', email='learner@gmail.com')
        membership = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id, 'partner_id': learner.partner_id.id})
        as_learner = membership.with_user(learner).sudo()
        certificate = self.env['slide.certificate'].with_user(learner).sudo() \
            ._issue_for_membership(as_learner)
        self.assertEqual(certificate.create_uid, learner,
                         "Precondition: the learner is the creator, as in production")
        mail = self._mails_for(certificate)
        self.assertEqual(len(mail), 1)
        self.assertNotIn('learner@gmail.com', mail.email_from)
        self.assertIn('trainer@example.com', mail.email_from)


@tagged('post_install', '-at_install')
class TestExamResultMail(ImElearningCommon):
    """A failed exam must reach the learner's inbox, a passed one must not
    trigger the failure letter."""

    FAIL_SUBJECT = 'chưa đạt'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slide_exam = create_exam(cls.env, cls.channel, scoring_success_min=50.0)
        cls.survey = cls.slide_exam.survey_id

    def _sit_exam(self, partner, passing, **kwargs):
        """An empty attempt scores 0, so the pass mark decides the outcome."""
        self.survey.scoring_success_min = 0.0 if passing else 50.0
        return submit_exam(self.env, self.slide_exam, partner, **kwargs)

    def _failure_mails(self, user_input):
        return self.env['mail.mail'].search([
            ('model', '=', 'survey.user_input'),
            ('res_id', '=', user_input.id),
            ('subject', 'ilike', self.FAIL_SUBJECT),
        ])

    def test_failed_exam_mails_the_learner(self):
        user_input = self._sit_exam(self.partner_student, passing=False)
        self.assertFalse(user_input.scoring_success, "Precondition: the exam was failed")
        mails = self._failure_mails(user_input)
        self.assertEqual(len(mails), 1, "One letter per failed attempt")
        self.assertIn(self.partner_student, mails.recipient_ids)
        self.assertIn(self.channel.name, mails.subject)
        self.assertIn('50', mails.body_html, "The pass mark must be spelled out")
        self.assertIn('/slides/', mails.body_html, "A way back to the course")

    def test_header_names_the_course_not_the_model(self):
        user_input = self._sit_exam(self.partner_student, passing=False)
        body = self._failure_mails(user_input).body_html
        self.assertIn('Kết quả bài thi', body)
        self.assertIn(self.channel.name, body)
        self.assertNotIn('Your Survey', body)

    def test_every_failed_attempt_is_reported(self):
        first = self._sit_exam(self.partner_student, passing=False)
        second = self._sit_exam(self.partner_student, passing=False)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self._failure_mails(first)), 1)
        self.assertEqual(len(self._failure_mails(second)), 1)

    def test_passed_exam_sends_no_failure_letter(self):
        user_input = self._sit_exam(self.partner_student, passing=True)
        self.assertTrue(user_input.scoring_success)
        self.assertFalse(self._failure_mails(user_input))

    def test_test_entry_is_silent(self):
        """The survey's Test button is not a real learner."""
        user_input = self._sit_exam(self.partner_student, passing=False, test_entry=True)
        self.assertFalse(self._failure_mails(user_input))

    def test_learner_without_address_is_skipped_quietly(self):
        self.partner_student.email = False
        user_input = self._sit_exam(self.partner_student, passing=False)
        self.assertFalse(self._failure_mails(user_input))

    def test_last_limited_attempt_is_left_to_ce(self):
        """When attempts run out CE already writes and drops the learner from
        the course; a second letter would only confuse them."""
        self.survey.write({
            'is_attempts_limited': True,
            'attempts_limit': 1,
            'users_login_required': True,
        })
        user_input = self._sit_exam(self.partner_student, passing=False)
        self.assertFalse(self._failure_mails(user_input))
        ce_mails = self.env['mail.mail'].search([
            ('model', '=', 'survey.user_input'),
            ('res_id', '=', user_input.id),
        ])
        self.assertEqual(len(ce_mails), 1, "CE's own failure letter must still go out")

    def test_letter_is_not_sent_in_the_learners_name(self):
        trainer = create_internal_user(
            self.env, 'im_trainer_fail_mail', email='trainer@example.com')
        self.channel.user_id = trainer
        learner = create_portal_user(
            self.env, 'im_learner_fail_mail', email='learner@gmail.com')
        user_input = self._sit_exam(learner.partner_id, passing=False, as_user=learner)
        mails = self._failure_mails(user_input)
        self.assertEqual(len(mails), 1)
        self.assertNotIn('learner@gmail.com', mails.email_from)
        self.assertIn('trainer@example.com', mails.email_from)


@tagged('post_install', '-at_install')
class TestAssignmentMail(ImElearningCommon):

    def _assign(self, deadline, employee=None):
        return self.env['im.course.assignment'].create({
            'channel_id': self.channel.id,
            'employee_id': (employee or self.employee).id,
            'date_assigned': fields.Date.subtract(deadline, days=7),
            'date_deadline': deadline,
        })

    def _other_employee(self, name):
        partner = self.env['res.partner'].create(
            {'name': name, 'email': '%s@example.com' % name.replace(' ', '')})
        return self.env['hr.employee'].create(
            {'name': name, 'work_contact_id': partner.id})

    def _mails_for(self, assignment):
        return self.env['mail.mail'].search([
            ('model', '=', 'im.course.assignment'),
            ('res_id', '=', assignment.id),
        ])

    def test_reminder_mail_names_the_course(self):
        tomorrow = fields.Date.add(fields.Date.context_today(self.env.user), days=1)
        assignment = self._assign(deadline=tomorrow)
        self.env['im.course.assignment']._cron_remind_deadline()
        mail = self._mails_for(assignment)
        self.assertEqual(len(mail), 1)
        self.assertIn(self.channel.name, mail.subject)
        self.assertIn('Khoá học được giao', mail.body_html)
        self.assertIn(self.partner_student, mail.recipient_ids)

    def test_overdue_mail_copies_the_line_manager(self):
        yesterday = fields.Date.subtract(fields.Date.context_today(self.env.user), days=1)
        assignment = self._assign(deadline=yesterday)
        self.env['im.course.assignment']._cron_notify_overdue()
        mail = self._mails_for(assignment)
        self.assertEqual(len(mail), 1)
        # The template puts the manager in cc; Odoo turns known addresses into
        # recipient partners, so accept either form.
        reached = (mail.email_cc or '') + ' ' + ' '.join(mail.recipient_ids.mapped('email'))
        self.assertIn(self.manager_employee.work_email, reached)
        self.assertIn(self.partner_student, mail.recipient_ids)

    def test_reminder_cron_survives_one_broken_mail(self):
        """One failing send must not leave the whole batch unreminded."""
        tomorrow = fields.Date.add(fields.Date.context_today(self.env.user), days=1)
        broken = self._assign(deadline=tomorrow)
        healthy = self._assign(
            deadline=tomorrow, employee=self._other_employee('Second person'))

        MailTemplate = type(self.env['mail.template'])
        real_send = MailTemplate.send_mail

        def flaky(template, res_id, **kwargs):
            if res_id == broken.id:
                raise ValueError('SMTP died mid-flight')
            return real_send(template, res_id, **kwargs)

        with patch.object(MailTemplate, 'send_mail', flaky):
            count = self.env['im.course.assignment']._cron_remind_deadline()

        (broken | healthy).invalidate_recordset()
        self.assertEqual(count, 1)
        self.assertTrue(healthy.reminder_sent, "Everyone else must still be reminded")
        self.assertFalse(
            broken.reminder_sent, "A failed send stays unmarked so the next run retries")
