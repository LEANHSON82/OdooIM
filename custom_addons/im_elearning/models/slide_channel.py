from odoo import _, api, fields, models


class SlideChannel(models.Model):
    """Exam gating, plus the per-course certificate settings."""
    _inherit = 'slide.channel'

    exam_unlock_completion = fields.Integer(
        'Mở bài thi khi hoàn thành (%)', default=80,
        help="Học viên phải hoàn thành ít nhất bao nhiêu phần trăm bài giảng của "
             "khoá học trước khi được vào bài thi. Bản thân bài thi không được tính "
             "vào con số này. Để 0 nếu không muốn chặn.")
    certificate_enabled = fields.Boolean(
        'Cấp chứng chỉ khi đỗ', default=True,
        help="Khi học viên đỗ bài thi của khoá, hệ thống tự cấp chứng chỉ có mã "
             "tra cứu được.")
    certificate_ids = fields.One2many(
        'slide.certificate', 'channel_id', string='Chứng chỉ đã cấp')
    certificate_count = fields.Integer(
        'Số chứng chỉ', compute='_compute_certificate_count')

    _check_exam_unlock_completion = models.Constraint(
        'CHECK(exam_unlock_completion >= 0 AND exam_unlock_completion <= 100)',
        'Ngưỡng mở bài thi phải nằm trong khoảng 0 đến 100 phần trăm.',
    )

    @api.depends('certificate_ids')
    def _compute_certificate_count(self):
        counts = dict(self.env['slide.certificate']._read_group(
            [('channel_id', 'in', self.ids)], ['channel_id'], ['__count'],
        ))
        for channel in self:
            channel.certificate_count = counts.get(channel, 0)

    def _get_lesson_completion(self, partner):
        """Percentage of the course's lessons *partner* has completed.

        CE's ``slide.channel.partner.completion`` counts the exam slide in the
        denominator, so a course with N lessons can never show more than
        N/(N+1) before the exam and short courses would stay locked forever.
        This leaves certification slides out and looks only at published
        lessons, the same population CE counts otherwise.
        """
        self.ensure_one()
        lessons = self.sudo().slide_ids.filtered(
            lambda slide: slide.is_published and not slide.is_category
            and slide.slide_category != 'certification')
        if not lessons:
            return 100
        completed = self.env['slide.slide.partner'].sudo().search_count([
            ('slide_id', 'in', lessons.ids),
            ('partner_id', '=', partner.id),
            ('completed', '=', True),
        ])
        return round(100.0 * completed / len(lessons))

    def _get_exam_lock_reason(self, partner=None):
        """Explain why the exam is locked, or return False when it is open."""
        self.ensure_one()
        if not self.exam_unlock_completion:
            return False
        partner = partner or self.env.user.partner_id
        completion = self._get_lesson_completion(partner)
        if completion >= self.exam_unlock_completion:
            return False
        return _(
            "Bạn cần hoàn thành ít nhất %(required)s%% bài giảng của khoá học "
            "trước khi vào bài thi. Hiện tại bạn đã hoàn thành %(current)s%%.",
            required=self.exam_unlock_completion,
            current=completion,
        )

    @api.model
    def _im_get_mail_template(self, key):
        """Mail template for *key*: 'certificate_issued', 'exam_failed',
        'assignment_reminder' or 'assignment_overdue'.

        How the mails look is not this module's business. A theme module
        (im_theme) overrides this and returns its own template;
        without one there is none, and every sender logs that instead of
        failing.
        """
        return self.env['mail.template']

    def _im_make_room_after_section(self, section, count, ignore=None):
        """Sequence just after *section*, pushing later slides down."""
        self.ensure_one()
        ignore = ignore or self.env['slide.slide']
        slides = self.slide_ids - ignore
        if not section:
            return max(slides.mapped('sequence') or [0])

        in_section = slides.filtered(lambda slide: slide.category_id == section)
        start = max([section.sequence] + in_section.mapped('sequence'))

        following = slides.filtered(lambda slide: slide.sequence > start)
        for slide in following.sorted('sequence', reverse=True):
            slide.sequence += count
        return start

    def action_open_link_import(self):
        """Open the bulk lesson importer."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nạp bài giảng từ danh sách liên kết'),
            'res_model': 'im.slide.link.import',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_channel_id': self.id},
        }

    def action_view_certificates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Chứng chỉ đã cấp'),
            'res_model': 'slide.certificate',
            'view_mode': 'list,form',
            'domain': [('channel_id', '=', self.id)],
            'context': {'default_channel_id': self.id},
        }
