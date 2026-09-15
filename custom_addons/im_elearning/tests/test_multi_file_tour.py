from odoo.tests import HttpCase, tagged

from .common import create_internal_user


@tagged('post_install', '-at_install')
class TestMultiFileUploadTour(HttpCase):
    """Drive a real browser through the multi-file picker."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.publisher = create_internal_user(
            cls.env, 'im_tour_publisher',
            groups=('website_slides.group_website_slides_manager',))
        cls.channel = cls.env['slide.channel'].create({
            'name': 'Multi-file upload test course',
            'user_id': cls.publisher.id,
            'is_published': True,
            'enroll': 'public',
            'visibility': 'public',
        })

    def test_multi_file_upload_does_not_crash(self):
        self.start_tour(
            '/slides/%s' % self.channel.id,
            'im_multi_file_upload',
            login='im_tour_publisher',
        )

    def test_video_file_upload_from_dialog(self):
        """CE blocks video files in this dialog; the patch allows them."""
        self.start_tour(
            '/slides/%s' % self.channel.id,
            'im_video_file_upload',
            login='im_tour_publisher',
        )

        slides = self.env['slide.slide'].search([
            ('channel_id', '=', self.channel.id),
            ('slide_category', '=', 'video'),
        ])
        self.assertEqual(len(slides), 2, "Two files must become two lessons")
        for slide in slides:
            self.assertEqual(
                slide.video_source_type, 'local',
                "CE forces source_type='external' for video; the patch must "
                "flip it back")
            self.assertEqual(slide.slide_type, 'local_video')
            self.assertTrue(slide.binary_content, "The video file must really be sent")
            self.assertFalse(slide.video_url,
                             "Uploading a file must not keep the old URL")
        self.assertEqual(
            sorted(slides.mapped('name')),
            ['Lesson 1 Introduction', 'Lesson 2 Next steps'],
            "Titles must be derived from the file names")

    def test_oversized_video_is_blocked_before_creating_slide(self):
        """Blocked in the browser, leaving no empty lesson behind."""
        self.env['ir.config_parameter'].sudo().set_param(
            'im_elearning.video_upload_limit_mb', '1')
        before = self.env['slide.slide'].search_count([
            ('channel_id', '=', self.channel.id)])

        self.start_tour(
            '/slides/%s' % self.channel.id,
            'im_video_too_big',
            login='im_tour_publisher',
        )

        after = self.env['slide.slide'].search_count([
            ('channel_id', '=', self.channel.id)])
        self.assertEqual(
            before, after,
            "A rejected file must not leave any empty lesson behind")
