import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SurveyUserInput(models.Model):
    """Issue the certificate on a pass, tell the learner on a fail."""
    _inherit = 'survey.user_input'

    def _mark_done(self):
        """CE's end-of-attempt hook; certificate and failure mail hang off it."""
        res = super()._mark_done()
        self._im_issue_certificates()
        self._im_notify_failures()
        return res

    def _im_course_exam_attempts(self):
        """Real learners sitting a course exam; the survey's Test button and
        stand-alone surveys are not our business."""
        return self.filtered(
            lambda attempt: attempt.slide_partner_id and not attempt.test_entry)

    def _im_issue_certificates(self):
        """Issue a certificate for every passing course exam attempt."""
        # The membership, not the attempt, is what a certificate belongs to.
        Certificate = self.env['slide.certificate']
        ChannelPartner = self.env['slide.channel.partner'].sudo()
        for attempt in self._im_course_exam_attempts().filtered('scoring_success'):
            slide_partner = attempt.slide_partner_id
            membership = ChannelPartner.search([
                ('channel_id', '=', slide_partner.channel_id.id),
                ('partner_id', '=', slide_partner.partner_id.id),
            ], limit=1)
            if membership:
                Certificate._issue_for_membership(membership, user_input=attempt)

    def _im_notify_failures(self):
        """Mail every failed course exam attempt, unless CE just did.

        CE only writes to a learner who fails when the exam limits attempts and
        the last one is gone; it then also drops them from the course. With the
        default unlimited attempts a failed exam is silent, so this fills the
        gap and steps aside on the one case CE already covers.
        """
        template = self.env['slide.channel']._im_get_mail_template('exam_failed')
        if not template:
            _logger.warning(
                "im_elearning: no mail template for failed exams, not reporting them. "
                "Is im_theme installed?")
            return self.browse()
        notified = self.browse()
        for attempt in self._im_course_exam_attempts():
            if attempt.scoring_success:
                continue
            if not (attempt.partner_id.email or attempt.email):
                continue
            # No attempt left means CE already mailed this learner.
            if not attempt.survey_id.sudo()._has_attempts_left(
                    attempt.partner_id, attempt.email, attempt.invite_token):
                continue
            try:
                template.sudo().send_mail(attempt.id, force_send=False)
            except Exception:
                _logger.exception(
                    "im_elearning: could not report the failed exam of %s on %s",
                    attempt.partner_id.display_name or attempt.email,
                    attempt.slide_partner_id.channel_id.display_name)
                continue
            notified |= attempt
        return notified
