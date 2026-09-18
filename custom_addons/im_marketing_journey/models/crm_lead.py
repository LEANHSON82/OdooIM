from odoo import models, fields, api

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    participant_ids = fields.One2many('im.journey.participant', 'lead_id', string='Marketing Journeys')
    journey_count = fields.Integer(string='Journey Count', compute='_compute_journey_count')

    @api.depends('participant_ids')
    def _compute_journey_count(self):
        for lead in self:
            lead.journey_count = len(lead.participant_ids)

    def _enroll_in_running_journeys(self):
        """Enroll these leads into every running journey they now match.

        Called on create and whenever stage_id changes, which is also how a
        lead leaves another journey.
        """
        running_journeys = self.env['im.journey'].search([('state', '=', 'running')])
        if not running_journeys:
            return

        Participant = self.env['im.journey.participant']
        candidates = self.filtered('active')
        if not candidates:
            return

        existing = Participant.search([
            ('journey_id', 'in', running_journeys.ids),
            ('lead_id', 'in', candidates.ids),
        ])
        by_key = {(p.journey_id.id, p.lead_id.id): p for p in existing}

        for lead in candidates:
            for journey in running_journeys:
                if lead.stage_id != journey.trigger_stage_id:
                    continue
                # One participant per (journey, lead) by constraint, so an
                # existing one is restarted rather than duplicated.
                participant = by_key.get((journey.id, lead.id))
                if participant:
                    if journey.allow_re_enroll and participant.state in ('done', 'exited'):
                        participant.action_restart_run()
                    continue
                first_node = journey.node_ids.sorted('sequence')[:1]
                Participant.create({
                    'journey_id': journey.id,
                    'lead_id': lead.id,
                    'current_node_id': first_node.id if first_node else False,
                    'next_execution_time': fields.Datetime.now(),
                    'state': 'running',
                })

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        leads._enroll_in_running_journeys()
        return leads

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            self._enroll_in_running_journeys()
        return res
