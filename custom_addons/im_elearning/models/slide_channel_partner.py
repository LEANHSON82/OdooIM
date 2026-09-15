from odoo import api, fields, models


class SlideChannelPartner(models.Model):
    """Hook certificate issuance onto the moment a learner passes."""
    _inherit = 'slide.channel.partner'

    certificate_id = fields.Many2one(
        'slide.certificate', string='Chứng chỉ', readonly=True,
        compute='_compute_certificate_id')

    @api.depends('partner_id', 'channel_id')
    def _compute_certificate_id(self):
        held = self.env['slide.certificate']._map_by_learner_and_course(
            self.partner_id, self.channel_id)
        for membership in self:
            membership.certificate_id = held.get(
                (membership.partner_id.id, membership.channel_id.id), False)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('survey_certification_success'):
            self._im_issue_certificates()
        return res

    def _im_issue_certificates(self):
        """Issue a certificate for every membership that has passed."""
        Certificate = self.env['slide.certificate']
        for membership in self.filtered('survey_certification_success'):
            user_input = self.env['survey.user_input'].sudo().search([
                ('partner_id', '=', membership.partner_id.id),
                ('slide_id.channel_id', '=', membership.channel_id.id),
                ('scoring_success', '=', True),
            ], order='create_date desc', limit=1)
            Certificate._issue_for_membership(membership, user_input=user_input)
