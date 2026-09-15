import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

LINE_RE = re.compile(r'^\s*(?P<url>\S+)\s*(?:\|\s*(?P<title>.+?))?\s*$')

MAX_REPORTED_PROBLEMS = 30

MEANINGLESS_URL_TAILS = frozenset({
    'view', 'watch', 'edit', 'preview', 'embed', 'open', 'file', 'video',
    'share', 'usp', 'sharing', 'index', 'player', 'default',
})


class ImSlideLinkImport(models.TransientModel):
    """Create many lessons at once from a pasted list of links."""
    _name = 'im.slide.link.import'
    _description = 'Nạp bài giảng từ danh sách liên kết'

    channel_id = fields.Many2one(
        'slide.channel', string='Khoá học', required=True, ondelete='cascade')
    section_id = fields.Many2one(
        'slide.slide', string='Thêm vào phần',
        domain="[('channel_id', '=', channel_id), ('is_category', '=', True)]",
        help="Để trống thì các bài giảng nằm ở cuối khoá học.")
    links = fields.Text(
        'Danh sách liên kết', required=True,
        help="Mỗi dòng một liên kết. Muốn tự đặt tên thì viết: liên kết | tiêu đề")
    fetch_metadata = fields.Boolean(
        'Tự lấy tiêu đề và thời lượng', default=True,
        help="Hỏi YouTube / Google Drive / Vimeo để lấy tiêu đề, mô tả, ảnh và "
             "thời lượng. YouTube và Drive cần khoá API Google khai trong cấu "
             "hình website; không có thì bỏ qua, dùng tiêu đề bạn tự ghi.")
    is_published = fields.Boolean('Đăng luôn', default=True)
    result = fields.Text('Kết quả', readonly=True)

    @api.model
    def _parse_links(self, raw):
        """Split the pasted text into ``(url, title)`` pairs."""
        entries = []
        seen = set()
        for line in (raw or '').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = LINE_RE.match(line)
            if not match:
                continue
            url = match.group('url')
            if not url.startswith(('http://', 'https://')):
                continue
            if url in seen:
                continue
            seen.add(url)
            entries.append((url, (match.group('title') or '').strip()))
        return entries

    def _fallback_name(self, url, index):
        """A placeholder title when nothing better is available."""
        tail = url.rstrip('/').split('/')[-1].split('?')[0]
        tail = re.sub(r'[_-]+', ' ', tail).strip()
        looks_like_id = (
            bool(tail) and not re.search(r'[aeiouAEIOU]', tail) and len(tail) > 8)
        if not tail or tail.lower() in MEANINGLESS_URL_TAILS or looks_like_id:
            return self.env._("Bài giảng %s", index)
        return tail

    def action_import(self):
        """Create one lesson per link, reporting what needs a second look."""
        self.ensure_one()
        entries = self._parse_links(self.links)
        if not entries:
            raise UserError(_(
                "Không đọc được liên kết nào. Mỗi dòng một liên kết bắt đầu "
                "bằng http:// hoặc https://"))

        Slide = self.env['slide.slide']
        already_in_course = set(Slide.search([
            ('channel_id', '=', self.channel_id.id),
            ('video_url', '!=', False),
        ]).mapped('video_url'))

        sequence = self.channel_id._im_make_room_after_section(
            self.section_id, len(entries))

        created = skipped = 0
        problems = []
        for index, (url, title) in enumerate(entries, start=1):
            if url in already_in_course:
                skipped += 1
                continue
            sequence += 1
            try:
                slide = Slide.create({
                    'name': title or self._fallback_name(url, index),
                    'channel_id': self.channel_id.id,
                    'slide_category': 'video',
                    'video_url': url,
                    'sequence': sequence,
                    'is_published': self.is_published,
                })
            except Exception as err:
                problems.append('%s — %s' % (url, str(err)[:80]))
                continue

            if not slide.video_source_type:
                problems.append(_("%s — không nhận ra là liên kết video", url))

            if self.fetch_metadata:
                self._apply_metadata(slide, bool(title), problems)
            created += 1

        self.result = self._format_result(created, skipped, problems)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _apply_metadata(self, slide, has_title, problems):
        """Pull title and duration, never failing the batch."""
        try:
            values, error = slide._fetch_external_metadata()
        except Exception as err:
            problems.append('%s — %s' % (slide.video_url, str(err)[:80]))
            return
        if error or not values:
            if not has_title:
                problems.append(_(
                    "%s — không lấy được tiêu đề, đang dùng tên tạm", slide.video_url))
            return
        if has_title:
            values.pop('name', None)
        slide.write(values)

    def _format_result(self, created, skipped, problems):
        """Summarise the run, capping the problem list so it stays readable.

        Goes through ``self.env._`` rather than the module-level ``_``: the
        latter finds the language by inspecting the caller's frame for an
        environment, which a static method does not have.
        """
        lines = [self.env._("Đã tạo %s bài giảng.", created)]
        if skipped:
            lines.append(self.env._("Bỏ qua %s liên kết đã có trong khoá.", skipped))
        if problems:
            lines.append('')
            lines.append(self.env._("Cần xem lại (%s):", len(problems)))
            lines.extend('  - %s' % problem
                         for problem in problems[:MAX_REPORTED_PROBLEMS])
            if len(problems) > MAX_REPORTED_PROBLEMS:
                lines.append(self.env._(
                    "  ... và %s dòng nữa", len(problems) - MAX_REPORTED_PROBLEMS))
        return '\n'.join(lines)
