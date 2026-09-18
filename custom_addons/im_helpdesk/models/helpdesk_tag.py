"""Ticket tag model for IM Helpdesk.

A tag is both a label shown on the ticket and the input of the automations: keyword
auto-tagging, routing the ticket to the right team, and picking the agent who will
handle it.
"""

import re
from random import randint

from odoo import api, fields, models


class HelpdeskTag(models.Model):
    """A reusable helpdesk tag, with optional auto-apply keywords."""

    _name = 'helpdesk.tag'
    _description = 'Helpdesk Tags'
    _order = 'name'

    def _get_default_color(self):
        """Pick a random kanban colour when a tag is created."""
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
        """Reuse an existing tag when quick-create is given the same name.

        Odoo quick-create can fire from a many2many widget. This override avoids
        tags that differ only by case or surrounding spaces.
        """
        existing_tag = self.search([('name', '=ilike', name.strip())], limit=1)
        if existing_tag:
            return existing_tag.id, existing_tag.display_name
        return super().name_create(name)

    def _get_auto_apply_keywords(self):
        """Return the normalised keywords used for auto-tagging.

        Keywords may be separated by commas, semicolons or newlines. The result
        is casefolded so matching ignores case and behaves on non-ASCII text.
        """
        self.ensure_one()
        return [
            keyword.strip().casefold()
            for keyword in re.split(r'[,;\n]+', self.auto_apply_keywords or '')
            if keyword.strip()
        ]

    def _get_auto_apply_keyword_entries(self):
        """Return the auto-apply keywords together with their configured weight.

        Legacy data such as ``invoice`` still weighs 1. The newer ``keyword::3``
        syntax lets one keyword contribute 3 points to the tag.
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
