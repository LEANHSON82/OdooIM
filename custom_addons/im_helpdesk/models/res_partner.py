"""Phần mở rộng partner cho ticket Helpdesk và SLA policy."""

from odoo import fields, models, _


class ResPartner(models.Model):
    """Hiển thị bộ đếm ticket và các SLA policy riêng theo khách hàng."""

    _inherit = 'res.partner'

    ticket_count = fields.Integer("Tickets", compute='_compute_ticket_count')
    sla_ids = fields.Many2many(
        'helpdesk.sla', 'helpdesk_sla_res_partner_rel',
        'res_partner_id', 'helpdesk_sla_id', string='SLA Policies',
        help="SLA Policies that will automatically apply to the tickets submitted by this customer.")

    def _compute_ticket_count(self):
        """Đếm ticket cho từng partner, bao gồm cả contact con.

        Query read-group đếm ticket theo partner trực tiếp trên ticket, sau đó
        cộng dồn theo cây commercial/contact để company cha hiển thị tổng số
        ticket của cả nhóm.
        """
        all_partners_subquery = self.with_context(active_test=False)._search([('id', 'child_of', self.ids)])

        groups = self.env['helpdesk.ticket']._read_group(
            [('partner_id', 'in', all_partners_subquery)],
            groupby=['partner_id'], aggregates=['__count'],
        )
        self.ticket_count = 0
        for partner, count in groups:
            while partner:
                if partner in self:
                    partner.ticket_count += count
                partner = partner.with_context(prefetch_fields=False).parent_id

    def action_open_helpdesk_ticket(self):
        """Mở ticket helpdesk của partner từ smart button.

        Nếu chỉ có một ticket thì mở thẳng form view. Nếu có nhiều ticket thì
        mở list view với domain gồm partner hiện tại và toàn bộ contact con.
        """
        self.ensure_one()
        action = {
            **self.env["ir.actions.actions"]._for_xml_id("im_helpdesk.helpdesk_ticket_action_main_tree"),
            'display_name': _("%(partner_name)s's Tickets", partner_name=self.name),
            'context': {},
        }
        all_child = self.with_context(active_test=False).search([('id', 'child_of', self.ids)])
        search_domain = [('partner_id', 'in', (self | all_child).ids)]
        if self.ticket_count <= 1:
            ticket_id = self.env['helpdesk.ticket'].search(search_domain, limit=1)
            action['res_id'] = ticket_id.id
            action['views'] = [(view_id, view_type) for view_id, view_type in action['views'] if view_type == "form"]
        else:
            action['domain'] = search_domain
        return action
