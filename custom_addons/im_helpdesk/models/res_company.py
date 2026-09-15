"""Phần mở rộng company để tạo mặc định cho IM Helpdesk.

Khi tạo công ty mới, module tự tạo một team Customer Care cơ bản kèm các stage
helpdesk chuẩn để công ty có thể nhận ticket ngay.
"""

from odoo import Command, api, models, _


class ResCompany(models.Model):
    """Mở rộng company với cơ chế tự tạo team helpdesk."""

    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        """Tạo company và tạo luôn team helpdesk mặc định cho company đó."""
        company = super().create(vals_list)
        company._create_helpdesk_team()
        return company

    def _create_helpdesk_team(self):
        """Tạo một team Customer Care mặc định cho mỗi company trong ``self``.

        Helper này dùng lại các stage đã cấu hình, sinh mail alias không trùng
        và tắt SLA mặc định để team bắt đầu đơn giản cho tới khi admin chủ động
        bật policy.
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
