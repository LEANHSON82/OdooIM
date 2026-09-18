from odoo import models, fields

class ImJourneyLog(models.Model):
    """Audit trail of every step run, and the double-send guard."""

    _name = 'im.journey.log'
    _description = 'Marketing Journey Execution Log'
    _order = 'execution_time desc, id desc'

    participant_id = fields.Many2one('im.journey.participant', string='Participant Lead', required=True, ondelete='cascade')
    journey_id = fields.Many2one('im.journey', string='Journey', related='participant_id.journey_id', store=True, readonly=True)
    lead_id = fields.Many2one('crm.lead', string='Lead', related='participant_id.lead_id', store=True, readonly=True)
    node_id = fields.Many2one('im.journey.node', string='Node', required=True)
    action_type = fields.Selection([
        ('zns', 'Zalo ZNS'),
        ('email', 'Email'),
        ('system', 'System'),
    ], string='Channel', required=True, default='zns')
    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('postponed', 'Postponed (Quiet Hours)'),
    ], string='Status', default='success', required=True)
    message_content = fields.Text(string='Message Content / Log')
    execution_time = fields.Datetime(string='Execution Time', default=fields.Datetime.now, required=True)
    run_number = fields.Integer(string='Run Number', default=1, required=True)
