from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ImSlideMoveSection(models.TransientModel):
    """Move several slides into another section of the same course."""
    _name = 'im.slide.move.section'
    _description = 'Chuyển bài giảng sang phần khác'

    slide_ids = fields.Many2many('slide.slide', string='Bài giảng')
    channel_id = fields.Many2one(
        'slide.channel', string='Khoá học', compute='_compute_channel_id', store=True)
    section_id = fields.Many2one(
        'slide.slide', string='Chuyển sang phần',
        domain="[('channel_id', '=', channel_id), ('is_category', '=', True)]",
        help="Để trống thì chuyển xuống cuối khoá học, ngoài mọi phần.")

    @api.depends('slide_ids')
    def _compute_channel_id(self):
        for wizard in self:
            wizard.channel_id = wizard.slide_ids[:1].channel_id

    @api.model
    def default_get(self, fields_list):
        """Pre-fill with the selected slides, minus any section headers."""
        values = super().default_get(fields_list)
        slide_ids = self.env.context.get('active_ids') or []
        if self.env.context.get('active_model') == 'slide.slide' and slide_ids:
            slides = self.env['slide.slide'].browse(slide_ids).exists()
            slides = slides.filtered(lambda slide: not slide.is_category)
            values['slide_ids'] = [(6, 0, slides.ids)]
        return values

    def action_move(self):
        """Move the selected slides, keeping their relative order."""
        self.ensure_one()
        if not self.slide_ids:
            raise UserError(_("Chưa chọn bài giảng nào."))

        channels = self.slide_ids.channel_id
        if len(channels) > 1:
            raise UserError(_(
                "Các bài giảng đã chọn thuộc %s khoá học khác nhau. "
                "Mỗi lần chỉ chuyển được trong phạm vi một khoá.", len(channels)))
        if self.section_id and self.section_id.channel_id != channels:
            raise UserError(_("Phần được chọn không thuộc khoá học này."))

        moved = self.slide_ids.sorted('sequence')
        sequence = channels._im_make_room_after_section(
            self.section_id, len(moved), ignore=moved)
        for slide in moved:
            sequence += 1
            slide.sequence = sequence

        return {'type': 'ir.actions.act_window_close'}
