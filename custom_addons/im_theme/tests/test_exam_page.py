from odoo.tests import HttpCase, tagged

from odoo.addons.im_elearning.tests.common import create_exam, create_portal_user


@tagged('post_install', '-at_install')
class TestExamPage(HttpCase):
    """What the learner sees on the exam's start page."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.learner = create_portal_user(cls.env, 'im_theme_learner')
        cls.channel = cls.env['slide.channel'].create({
            'name': 'Themed Course',
            'is_published': True,
            'visibility': 'public',
            'enroll': 'public',
            'exam_unlock_completion': 0,
        })
        cls.exam = create_exam(cls.env, cls.channel)
        # An exam without questions shows survey's "empty" page, not the start page.
        cls.env['survey.question'].create({
            'survey_id': cls.exam.survey_id.id,
            'title': 'What is the first step?',
            'question_type': 'char_box',
        })
        cls.channel._action_add_members(cls.learner.partner_id)

    def test_course_exam_start_page(self):
        self.authenticate('im_theme_learner', 'im_theme_learner')
        response = self.url_open(
            '/slides_survey/slide/get_certification_url?slide_id=%s' % self.exam.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('/survey/', response.url)
        self.assertIn('Bài thi khoá học', response.text)
        self.assertIn(self.channel.name, response.text)
        self.assertIn('Bắt đầu làm bài', response.text)
        self.assertNotIn('Start Certification', response.text)
        self.assertNotIn('Start Survey', response.text)
        self.assertNotIn('Powered by', response.text)

    def test_test_button_of_a_course_exam_is_themed_too(self):
        """The trainer's Test button opens the same page, without a slide on
        the answer; the survey's course link is enough."""
        self.authenticate('admin', 'admin')
        response = self.url_open('/survey/test/%s' % self.exam.survey_id.access_token)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Bài thi khoá học', response.text)
        self.assertIn(self.channel.name, response.text)
        self.assertIn('Bắt đầu làm bài', response.text)
        self.assertNotIn('Powered by', response.text)

    def test_plain_survey_keeps_odoo_wording(self):
        """Surveys that are not course exams are none of our business."""
        survey = self.env['survey.survey'].create({
            'title': 'Plain survey',
            'access_mode': 'public',
            'users_login_required': False,
        })
        self.env['survey.question'].create({
            'survey_id': survey.id, 'title': 'Anything?', 'question_type': 'char_box'})
        response = self.url_open('/survey/start/%s' % survey.access_token)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Start Survey', response.text)
        self.assertNotIn('Bài thi khoá học', response.text)
        self.assertNotIn('Bắt đầu làm bài', response.text)
