import io

from odoo.tests import HttpCase, tagged

from .common import create_internal_user

BYTES_PER_MB = 1024 * 1024

BASE64_INFLATION = 4 / 3

STOCK_WIDGET_REQUEST_LIMIT = 128 * BYTES_PER_MB


@tagged('post_install', '-at_install')
class TestVideoUpload(HttpCase):
    """The browser upload path."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env['slide.channel'].create({'name': 'Video upload course'})
        cls.slide = cls.env['slide.slide'].create({
            'name': 'Lesson with video',
            'channel_id': cls.channel.id,
            'slide_category': 'video',
            'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        })
        create_internal_user(
            cls.env, 'im_teacher_test',
            groups=('website_slides.group_website_slides_manager',))

    def _upload(self, payload, filename='lesson.mp4', slide_id=None):
        return self.url_open(
            '/im_elearning/video/upload',
            data={'slide_id': slide_id or self.slide.id},
            files={'ufile': (filename, io.BytesIO(payload), 'application/octet-stream')},
        )

    def test_upload_stores_file_and_switches_source(self):
        self.authenticate('im_teacher_test', 'im_teacher_test')
        payload = b'video-bytes' * 1000

        response = self._upload(payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(response.json()['size'], len(payload))

        self.slide.invalidate_recordset()
        self.assertEqual(self.slide.video_source_type, 'local')
        self.assertEqual(self.slide.slide_type, 'local_video')
        self.assertFalse(
            self.slide.video_url,
            "Once a file is uploaded the file is the source; keeping the old "
            "URL would still play the YouTube video")

    def test_upload_guesses_video_mimetype(self):
        """A ``<video>`` tag refuses anything that is not ``video/*``."""
        self.authenticate('im_teacher_test', 'im_teacher_test')
        self._upload(b'x' * 100, filename='lesson-1.mp4')

        attachment = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'slide.slide'),
            ('res_id', '=', self.slide.id),
            ('res_field', '=', 'binary_content'),
        ], limit=1)
        self.assertEqual(attachment.mimetype, 'video/mp4')

    def test_upload_beyond_default_form_limit(self):
        """This route must clear the stock upload widget's real ceiling."""
        limit_mb = self.env['ir.config_parameter'].sudo().get_param(
            'im_elearning.video_upload_limit_mb', 512)
        self.assertGreater(
            int(limit_mb) * BYTES_PER_MB,
            int(STOCK_WIDGET_REQUEST_LIMIT / BASE64_INFLATION),
            "The route's ceiling must be higher than the stock widget's")

    def test_upload_rejects_empty_file(self):
        self.authenticate('im_teacher_test', 'im_teacher_test')
        response = self._upload(b'')
        self.assertFalse(response.json()['ok'])

    def test_upload_rejects_unknown_slide(self):
        self.authenticate('im_teacher_test', 'im_teacher_test')
        response = self._upload(b'x' * 10, slide_id=999999999)
        self.assertFalse(response.json()['ok'])

    def test_upload_requires_login(self):
        """An anonymous request is bounced to login and must write nothing."""
        response = self._upload(b'x' * 10)
        self.assertNotIn('"ok": true', response.text)
        self.slide.invalidate_recordset()
        self.assertFalse(self.slide.video_source_type == 'local')
