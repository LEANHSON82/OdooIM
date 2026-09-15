import base64
import json
import mimetypes

import werkzeug

from odoo import _
from odoo.exceptions import AccessError
from odoo.http import request, route

from odoo.addons.website_slides_survey.controllers.slides import WebsiteSlidesSurvey

BYTES_PER_MB = 1024 * 1024

DEFAULT_VIDEO_UPLOAD_LIMIT_MB = 512

VIDEO_UPLOAD_LIMIT_PARAM = 'im_elearning.video_upload_limit_mb'

FALLBACK_VIDEO_MIMETYPE = 'video/mp4'


def video_upload_limit(_controller):
    """Size ceiling for the upload route, read at request time."""
    param = request.env['ir.config_parameter'].sudo().get_param(
        VIDEO_UPLOAD_LIMIT_PARAM, DEFAULT_VIDEO_UPLOAD_LIMIT_MB)
    try:
        megabytes = int(param)
    except (TypeError, ValueError):
        megabytes = DEFAULT_VIDEO_UPLOAD_LIMIT_MB
    return megabytes * BYTES_PER_MB


class ImWebsiteSlides(WebsiteSlidesSurvey):
    """Serving self-hosted video, and locking the exam until enough is done."""

    @route('/im_elearning/video/<int:slide_id>', type='http', auth='user', website=True)
    def im_elearning_video(self, slide_id, **kwargs):
        """Stream a lesson's video file to a member of the course."""
        slide = request.env['slide.slide'].browse(slide_id).exists()
        if not slide:
            raise werkzeug.exceptions.NotFound()

        slide_sudo = slide.sudo()
        if slide_sudo.slide_category != 'video' or slide_sudo.video_source_type != 'local':
            raise werkzeug.exceptions.NotFound()

        channel = slide_sudo.channel_id
        if not (channel.is_member or channel.can_publish):
            raise werkzeug.exceptions.Forbidden(
                _("Bạn cần tham gia khoá học này để xem bài giảng."))

        if not slide_sudo.binary_content:
            raise werkzeug.exceptions.NotFound()

        stream = request.env['ir.binary']._get_stream_from(
            slide_sudo, 'binary_content', filename=slide_sudo.name)
        return stream.get_response(as_attachment=False)

    @route('/im_elearning/video/upload_limit', type='jsonrpc', auth='user')
    def im_elearning_video_upload_limit(self):
        """The ceiling, so the browser can refuse before sending."""
        return {'limit_mb': video_upload_limit(self) // BYTES_PER_MB}

    @route('/im_elearning/video/upload', type='http', auth='user', methods=['POST'],
           csrf=False, max_content_length=video_upload_limit)
    def im_elearning_video_upload(self, slide_id, **kwargs):
        """Upload a lesson's video file without going through base64."""
        slide = request.env['slide.slide'].browse(int(slide_id)).exists()
        if not slide:
            return self._upload_error(_("Không tìm thấy bài giảng."))
        try:
            slide.check_access('write')
        except AccessError:
            return self._upload_error(_("Bạn không có quyền sửa bài giảng này."))

        upload = request.httprequest.files.get('ufile')
        if not upload or not upload.filename:
            return self._upload_error(_("Chưa chọn tệp nào."))

        try:
            payload = upload.read()
            size = len(payload)
            if not size:
                return self._upload_error(_("Tệp rỗng."))

            slide.write({
                'source_type': 'local_file',
                'binary_content': base64.b64encode(payload),
                'video_url': False,
            })
            request.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'slide.slide'),
                ('res_id', '=', slide.id),
                ('res_field', '=', 'binary_content'),
            ]).write({
                'name': upload.filename,
                'mimetype': self._video_mimetype(upload),
            })

            return request.make_response(
                json.dumps({'ok': True, 'size': size, 'name': upload.filename}),
                headers=[('Content-Type', 'application/json')])
        except Exception as err:
            return self._upload_error(str(err))

    @staticmethod
    def _video_mimetype(upload):
        """The MIME type to store for an uploaded file."""
        declared = (upload.mimetype or '').lower()
        if declared.startswith('video/'):
            return declared
        guessed = mimetypes.guess_type(upload.filename or '')[0]
        if guessed and guessed.startswith('video/'):
            return guessed
        return FALLBACK_VIDEO_MIMETYPE

    @staticmethod
    def _upload_error(message):
        """Report a failure as JSON, so the upload widget can display it."""
        return request.make_response(
            json.dumps({'ok': False, 'error': message}),
            headers=[('Content-Type', 'application/json')])

    @route()
    def slide_get_certification_url(self, slide_id, **kw):
        """Block the exam until enough of the course has been completed."""
        fetch_res = self._fetch_slide(slide_id)
        if fetch_res.get('error'):
            raise werkzeug.exceptions.NotFound()

        slide = fetch_res['slide']
        channel = slide.channel_id
        if self._im_exam_is_locked(channel):
            return request.redirect(
                '/slides/%s?exam_locked=1' % request.env['ir.http']._slug(channel))
        return super().slide_get_certification_url(slide_id, **kw)

    def _prepare_additional_channel_values(self, values, **kwargs):
        """Tell the learner why the exam bounced them back to the course page.

        The redirect carries only a flag; the reason is recomputed here so a
        forged link cannot put arbitrary text on the page, and so it vanishes
        on its own once the learner has caught up.
        """
        values = super()._prepare_additional_channel_values(values, **kwargs)
        channel = values.get('channel')
        if kwargs.get('exam_locked') and channel and self._im_exam_is_locked(channel):
            values['exam_lock_reason'] = channel._get_exam_lock_reason(
                request.env.user.partner_id)
        return values

    @staticmethod
    def _im_exam_is_locked(channel):
        """Members below the threshold are locked; course staff never are."""
        if not channel.is_member or channel.can_publish:
            return False
        return bool(channel._get_exam_lock_reason(request.env.user.partner_id))
