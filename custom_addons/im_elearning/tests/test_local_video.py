import base64

from odoo.tests import tagged

from .common import ImElearningCommon


@tagged('post_install', '-at_install')
class TestLocalVideo(ImElearningCommon):

    def _make_local_video(self):
        return self.env['slide.slide'].create({
            'name': 'Lesson 2 - Internal video',
            'channel_id': self.channel.id,
            'slide_category': 'video',
            'source_type': 'local_file',
            'binary_content': base64.b64encode(b'fake-mp4-bytes'),
            'is_published': True,
        })

    def test_uploaded_file_detected_as_local(self):
        """An uploaded file lands on the 'local' source, not False."""
        slide = self._make_local_video()
        self.assertEqual(slide.video_source_type, 'local')
        self.assertEqual(slide.slide_type, 'local_video')

    def test_youtube_still_works(self):
        """CE's three existing sources must keep working."""
        slide = self.env['slide.slide'].create({
            'name': 'YouTube lesson',
            'channel_id': self.channel.id,
            'slide_category': 'video',
            'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        })
        self.assertEqual(slide.video_source_type, 'youtube')
        self.assertEqual(slide.slide_type, 'youtube_video')

    def test_vimeo_still_works(self):
        slide = self.env['slide.slide'].create({
            'name': 'Vimeo lesson',
            'channel_id': self.channel.id,
            'slide_category': 'video',
            'video_url': 'https://vimeo.com/123456789',
        })
        self.assertEqual(slide.video_source_type, 'vimeo')

    def test_local_video_has_no_public_embed_code(self):
        """No public embed: an internal video is for course members only."""
        slide = self._make_local_video()
        self.assertFalse(slide.embed_code)
        self.assertFalse(slide.embed_code_external)

    def test_local_video_url_points_to_guarded_route(self):
        slide = self._make_local_video()
        self.assertEqual(slide._get_local_video_url(), '/im_elearning/video/%s' % slide.id)

    def test_empty_video_is_not_marked_local(self):
        """An empty lesson must not be taken for a self-hosted video."""
        slide = self.env['slide.slide'].create({
            'name': 'Empty lesson',
            'channel_id': self.channel.id,
            'slide_category': 'video',
            'source_type': 'local_file',
        })
        self.assertFalse(slide.video_source_type)
        self.assertFalse(slide.slide_type)

    def test_source_type_does_not_read_file_content(self):
        """The compute must never read ``binary_content``."""
        slides = self.env['slide.slide']
        for index in range(3):
            slides |= self.env['slide.slide'].create({
                'name': 'Video %s' % index,
                'channel_id': self.channel.id,
                'slide_category': 'video',
                'source_type': 'local_file',
                'binary_content': base64.b64encode(b'video-bytes' * 100),
            })
        slides.invalidate_recordset()

        reads = []
        original = type(self.env['ir.attachment'])._compute_raw

        def spy(records):
            reads.append(len(records))
            return original(records)

        type(self.env['ir.attachment'])._compute_raw = spy
        try:
            self.assertEqual(
                slides.mapped('video_source_type'), ['local'] * 3,
                "The uploaded-file source must still be detected")
        finally:
            type(self.env['ir.attachment'])._compute_raw = original

        self.assertFalse(
            reads,
            "Reading the file content just to know whether a lesson has a video "
            "is exactly what must not happen")

    def test_source_type_on_unsaved_record(self):
        """An unsaved record has no attachment, but holds the file."""
        slide = self.env['slide.slide'].new({
            'name': 'Unsaved',
            'channel_id': self.channel.id,
            'slide_category': 'video',
            'source_type': 'local_file',
            'binary_content': base64.b64encode(b'abc'),
        })
        self.assertEqual(slide.video_source_type, 'local')
