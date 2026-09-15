from odoo.tests import HttpCase, tagged

from .common import ImElearningCommon, complete_slides, create_exam, create_portal_user


@tagged('post_install', '-at_install')
class TestExamGating(ImElearningCommon):
    """Two lessons and one exam: the exam must never count as a lesson."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slide_article_2 = cls.env['slide.slide'].create({
            'name': 'Lesson 2 - Passwords',
            'channel_id': cls.channel.id,
            'slide_category': 'article',
            'is_published': True,
            'html_content': '<p>More content</p>',
        })
        cls.slide_exam = create_exam(cls.env, cls.channel)
        cls.lessons = cls.slide_article | cls.slide_article_2

    def _enrol(self, partner=None):
        partner = partner or self.partner_student
        self.channel._action_add_members(partner)
        return self.env['slide.channel.partner'].search([
            ('channel_id', '=', self.channel.id), ('partner_id', '=', partner.id)])

    def _complete(self, slides, partner=None):
        complete_slides(self.env, slides, partner or self.partner_student)

    def test_gating_is_on_by_default(self):
        """80% out of the box."""
        self.assertEqual(self.channel.exam_unlock_completion, 80)
        self._enrol()
        self.assertTrue(self.channel._get_exam_lock_reason(self.partner_student))

    def test_can_be_turned_off(self):
        """Courses that do not need gating can still switch it off."""
        self.channel.exam_unlock_completion = 0
        self._enrol()
        self.assertFalse(self.channel._get_exam_lock_reason(self.partner_student))

    def test_locked_below_threshold(self):
        self.channel.exam_unlock_completion = 80
        self._enrol()
        self._complete(self.slide_article)
        reason = self.channel._get_exam_lock_reason(self.partner_student)
        self.assertTrue(reason)
        self.assertIn('80', reason)
        self.assertIn('50', reason,
                      "The message must say where the learner stands, not just "
                      "that they are blocked")

    def test_exam_slide_does_not_count(self):
        """All lessons done must open the exam even though CE's own progress
        figure, which counts the exam itself, still sits below the threshold."""
        self.channel.exam_unlock_completion = 80
        membership = self._enrol()
        self._complete(self.lessons)
        self.assertLess(membership.completion, 80,
                        "Precondition: CE counts 2 of 3 contents, i.e. 67%")
        self.assertEqual(self.channel._get_lesson_completion(self.partner_student), 100)
        self.assertFalse(self.channel._get_exam_lock_reason(self.partner_student))

    def test_unlocked_at_threshold(self):
        self.channel.exam_unlock_completion = 50
        self._enrol()
        self._complete(self.slide_article)
        self.assertFalse(self.channel._get_exam_lock_reason(self.partner_student))

    def test_unlocked_above_threshold(self):
        self.channel.exam_unlock_completion = 30
        self._enrol()
        self._complete(self.slide_article)
        self.assertFalse(self.channel._get_exam_lock_reason(self.partner_student))

    def test_unpublished_lessons_do_not_count(self):
        """A draft lesson cannot be studied, so it must not hold the exam shut."""
        self.channel.exam_unlock_completion = 100
        self.slide_article_2.is_published = False
        self._enrol()
        self._complete(self.slide_article)
        self.assertFalse(self.channel._get_exam_lock_reason(self.partner_student))

    def test_exam_only_course_is_open(self):
        """Nothing to study means nothing to wait for."""
        self.channel.exam_unlock_completion = 80
        self.lessons.write({'is_published': False})
        self._enrol()
        self.assertFalse(self.channel._get_exam_lock_reason(self.partner_student))

    def test_non_member_is_locked(self):
        """Someone not enrolled has 0% progress and must be blocked."""
        self.channel.exam_unlock_completion = 50
        reason = self.channel._get_exam_lock_reason(self.partner_other)
        self.assertTrue(reason)
        self.assertIn('0', reason)

    def test_threshold_must_be_percentage(self):
        with self.assertRaises(Exception):
            self.channel.exam_unlock_completion = 150
            self.channel.flush_recordset()

    def test_threshold_cannot_be_negative(self):
        with self.assertRaises(Exception):
            self.channel.exam_unlock_completion = -10
            self.channel.flush_recordset()


@tagged('post_install', '-at_install')
class TestExamGatingPage(HttpCase):
    """What the learner actually sees in the browser when the exam is shut."""

    LOCK_TEXT = 'hoàn thành ít nhất'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.learner = create_portal_user(cls.env, 'im_gated_learner')
        cls.channel = cls.env['slide.channel'].create({
            'name': 'Gated Course',
            'is_published': True,
            'visibility': 'public',
            'enroll': 'public',
            'exam_unlock_completion': 80,
        })
        cls.lessons = cls.env['slide.slide'].create([{
            'name': 'Lesson %s' % index,
            'channel_id': cls.channel.id,
            'slide_category': 'article',
            'is_published': True,
            'html_content': '<p>Lesson %s</p>' % index,
        } for index in (1, 2)])
        cls.exam = create_exam(cls.env, cls.channel)
        cls.channel._action_add_members(cls.learner.partner_id)

    def _complete_all_lessons(self):
        complete_slides(self.env, self.lessons, self.learner.partner_id)

    def _open_exam(self):
        return self.url_open(
            '/slides_survey/slide/get_certification_url?slide_id=%s' % self.exam.id)

    def test_locked_learner_lands_on_course_page_with_the_reason(self):
        self.authenticate('im_gated_learner', 'im_gated_learner')
        response = self._open_exam()
        self.assertEqual(response.status_code, 200)
        self.assertIn('exam_locked=1', response.url,
                      "The exam must bounce the learner back to the course")
        self.assertIn(self.LOCK_TEXT, response.text,
                      "The course page must say why, not just reload")
        self.assertIn('80%', response.text)

    def test_forged_flag_shows_nothing_when_not_locked(self):
        """The flag is only a hint; the page recomputes the real state."""
        self._complete_all_lessons()
        self.authenticate('im_gated_learner', 'im_gated_learner')
        response = self.url_open('/slides/%s?exam_locked=1' % self.channel.id)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.LOCK_TEXT, response.text)

    def test_learner_who_finished_reaches_the_exam(self):
        self._complete_all_lessons()
        self.authenticate('im_gated_learner', 'im_gated_learner')
        response = self._open_exam()
        self.assertEqual(response.status_code, 200)
        self.assertIn('/survey/', response.url,
                      "With every lesson done the exam must open")
        self.assertNotIn('exam_locked', response.url)
