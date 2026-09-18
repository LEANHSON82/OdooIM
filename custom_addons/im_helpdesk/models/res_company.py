"""Company extension providing the IM Helpdesk defaults.

A new company automatically gets a basic Customer Care team with the standard helpdesk
stages, so it can take tickets right away.
"""

from odoo import Command, api, models, _


class ResCompany(models.Model):
    """Extend company with automatic helpdesk team creation."""

    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        """Create the company and its default helpdesk team in one go."""
        company = super().create(vals_list)
        company._create_helpdesk_team()
        return company

    def _create_helpdesk_team(self):
        """Create one default Customer Care team per company in ``self``.

        The helper reuses the configured stages, generates a mail alias that
        does not clash, and leaves SLA off so the team starts simple until an
        admin turns policies on deliberately.
        """
        results = []
        stage_ids = []
        for xml_id in ['stage_new', 'stage_in_progress', 'stage_solved', 'stage_cancelled', 'stage_on_hold']:
            record = self.env.ref(f'im_helpdesk.{xml_id}', False)
            if record:
                stage_ids.append(record.id)
        team_name = _('Customer Care')
        to_create_or_existing_aliases = {r['alias_name'] for r in self.env['helpdesk.team'].search_read(fields=['alias_name'])}

        for company in self:
            alias_name = f"{team_name}-{company.name}"
            sanitized_alias_name = self.env['mail.alias']._sanitize_alias_name(alias_name)

            if sanitized_alias_name in to_create_or_existing_aliases:
                alias_name = f"{sanitized_alias_name}-{company.id}"
            to_create_or_existing_aliases.add(sanitized_alias_name)
            company = company.with_company(company)
            results += [{
                'name': team_name,
                'company_id': company.id,
                'use_sla': False,
                'stage_ids': [Command.set(stage_ids)],
                'alias_name': alias_name,
            }]
        return self.env['helpdesk.team'].sudo().create(results)
