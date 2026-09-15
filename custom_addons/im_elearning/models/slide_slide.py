from odoo import api, fields, models


class SlideSlide(models.Model):
    """Self-hosted video, as a fourth video source alongside CE's three."""
    _inherit = 'slide.slide'

    video_source_type = fields.Selection(
        selection_add=[('local', 'Tệp tải lên')],
    )
    slide_type = fields.Selection(
        selection_add=[('local_video', 'Video tải lên')],
        ondelete={'local_video': 'set null'},
    )
    video_binary_content = fields.Binary(
        'Tệp video', related='binary_content', readonly=False)
    category_id = fields.Many2one(readonly=False)

    def write(self, vals):
        """Setting a slide's section moves it to the matching sequence slot."""
        section_id = vals.get('category_id')
        res = super().write(vals)
        if 'category_id' in vals:
            self._im_move_to_section(self.browse(section_id))
        return res

    def _im_move_to_section(self, section):
        """Move slides after *section*, keeping their order."""
        movable = self.filtered(lambda slide: not slide.is_category)
        if not movable:
            return
        for channel in movable.channel_id:
            group = movable.filtered(lambda slide: slide.channel_id == channel)
            if section and section.channel_id != channel:
                continue
            sequence = channel._im_make_room_after_section(
                section, len(group), ignore=group)
            for slide in group.sorted('sequence'):
                sequence += 1
                slide.sequence = sequence

    @api.depends('video_url', 'slide_category', 'source_type')
    def _compute_video_source_type(self):
        """Keep CE's URL-based detection, add the uploaded-file branch."""
        super()._compute_video_source_type()
        candidates = self.filtered(
            lambda slide: slide.slide_category == 'video'
            and slide.source_type == 'local_file')
        if not candidates:
            return

        saved = candidates.filtered('id')
        ids_with_file = set()
        if saved:
            rows = self.env['ir.attachment'].sudo().search_read(
                [('res_model', '=', 'slide.slide'),
                 ('res_id', 'in', saved.ids),
                 ('res_field', '=', 'binary_content'),
                 ('file_size', '>', 0)],
                ['res_id'])
            ids_with_file = {row['res_id'] for row in rows}

        for slide in candidates:
            has_file = (
                slide.id in ids_with_file if slide.id else bool(slide.binary_content))
            if has_file:
                slide.video_source_type = 'local'

    @api.depends('slide_category', 'source_type', 'video_source_type')
    def _compute_slide_type(self):
        super()._compute_slide_type()
        for slide in self:
            if slide.slide_category == 'video' and slide.video_source_type == 'local':
                slide.slide_type = 'local_video'

    @api.depends('slide_category', 'google_drive_id', 'video_source_type', 'youtube_id')
    def _compute_embed_code(self):
        """A self-hosted video has no third-party iframe to embed."""
        super()._compute_embed_code()
        for slide in self:
            if slide.slide_category == 'video' and slide.video_source_type == 'local':
                slide.embed_code = False
                slide.embed_code_external = False

    def _get_local_video_url(self):
        """Streaming URL, used by the template and by the data handed to JS."""
        self.ensure_one()
        return '/im_elearning/video/%s' % self.id
