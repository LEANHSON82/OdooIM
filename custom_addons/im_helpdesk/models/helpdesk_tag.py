"""Model tag của ticket trong IM Helpdesk.

Tag vừa là nhãn hiển thị trên ticket, vừa là dữ liệu đầu vào cho tự động gắn tag
theo keyword, chuyển ticket về team phù hợp và chọn nhân viên xử lý.
"""

import re
from random import randint

from odoo import api, fields, models


class HelpdeskTag(models.Model):
    """Biểu diễn một tag helpdesk có thể tái sử dụng và có keyword tự gắn tùy chọn."""

    _name = 'helpdesk.tag'
    _description = 'Helpdesk Tags'
    _order = 'name'

    def _get_default_color(self):
        """Chọn ngẫu nhiên mã màu kanban khi tạo tag."""
        return randint(1, 11)

    name = fields.Char(required=True, translate=True)
    color = fields.Integer('Color', default=_get_default_color)
    auto_apply_keywords = fields.Text(
        'Auto Tag Keywords',
        help="Comma or newline separated keywords. If any keyword appears in a ticket subject or description, this tag is added automatically.")
    auto_apply_min_score = fields.Integer(
        'Minimum Auto Tag Score',
        default=1,
        help="Minimum total keyword score required before this tag is added automatically.")

    _name_uniq = models.Constraint(
        'unique (name)',
        "A tag with the same name already exists.",
    )
    _auto_apply_min_score_positive = models.Constraint(
        'CHECK(auto_apply_min_score > 0)',
        "Minimum auto-tag score must be positive.",
    )

    @api.model
    def name_create(self, name):
        """Dùng lại tag đã có khi quick-create nhận cùng một tên.

        Luồng quick-create của Odoo có thể được gọi từ widget many2many. Override
        này tránh tạo tag trùng chỉ khác chữ hoa/thường hoặc khoảng trắng.
        """
        existing_tag = self.search([('name', '=ilike', name.strip())], limit=1)
        if existing_tag:
            return existing_tag.id, existing_tag.display_name
        return super().name_create(name)

    def _get_auto_apply_keywords(self):
        """Trả về danh sách keyword đã chuẩn hóa để tự động gắn tag.

        Keyword có thể được phân tách bằng dấu phẩy, dấu chấm phẩy hoặc xuống
        dòng. Kết quả được casefold để match không phân biệt hoa/thường và ổn
        định hơn với cả text non-ASCII.
        """
        self.ensure_one()
        return [
            keyword.strip().casefold()
            for keyword in re.split(r'[,;\n]+', self.auto_apply_keywords or '')
            if keyword.strip()
        ]

    def _get_auto_apply_keyword_entries(self):
        """Trả về các keyword tự gắn tag cùng trọng số cấu hình.

        Dữ liệu cũ như ``invoice`` vẫn có trọng số 1. Cú pháp mới
        ``keyword::3`` cho phép keyword đó đóng góp 3 điểm vào tag.
        """
        self.ensure_one()
        entries = []
        for raw_entry in re.split(r'[,;\n]+', self.auto_apply_keywords or ''):
            raw_entry = raw_entry.strip()
            if not raw_entry:
                continue

            keyword, separator, raw_weight = raw_entry.rpartition('::')
            if not separator:
                entries.append((raw_entry, 1))
                continue

            keyword = keyword.strip()
            try:
                weight = int(raw_weight.strip())
            except (TypeError, ValueError):
                entries.append((raw_entry, 1))
                continue

            if keyword:
                entries.append((keyword, max(weight, 1)))
        return entries
