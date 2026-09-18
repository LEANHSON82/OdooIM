from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

from odoo.addons.base.models.res_partner import _tz_get

class ImJourney(models.Model):
    """A nurturing scenario: entry stage plus the nodes to walk through."""

    _name = 'im.journey'
    _description = 'Marketing Automation Journey'
    _order = 'id desc'

    name = fields.Char(string='Journey Name', required=True)
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('paused', 'Paused'),
    ], string='Status', default='draft', required=True)

    trigger_stage_id = fields.Many2one(
        'crm.stage', string='Trigger Stage (CRM)', required=True,
        help='When a new Lead is created or moved to this Stage, it will automatically enter this Journey.'
    )
    node_ids = fields.One2many('im.journey.node', 'journey_id', string='Journey Nodes', copy=True)
    participant_ids = fields.One2many('im.journey.participant', 'journey_id', string='Participants')
    participant_count = fields.Integer(string='Participant Count', compute='_compute_participant_count')

    step_delay_minutes = fields.Integer(
        string='Minimum Delay Between Steps (minutes)',
        default=5, required=True,
        help='Minimum gap between two steps of the same participant. This is what makes '
             'the engine idempotent: right after a step the participant is not due again, '
             'so two consecutive cron runs cannot push it twice.'
    )
    quiet_hours_tz = fields.Selection(
        _tz_get, string='Quiet Hours Timezone',
        default='Asia/Ho_Chi_Minh', required=True,
        help='Timezone the 22:00-07:00 quiet window is evaluated in. Configured here on '
             'purpose: relying on the timezone of the user running the cron breaks silently '
             'the day someone sets a timezone on OdooBot.'
    )
    allow_re_enroll = fields.Boolean(
        string='Allow Re-enrollment',
        default=False,
        help='When enabled, a lead that already finished or exited this journey enters it '
             'again if it comes back to the trigger stage, as a new run. Leave off to keep '
             'contacting each lead only once.'
    )

    @api.depends('participant_ids')
    def _compute_participant_count(self):
        for journey in self:
            journey.participant_count = len(journey.participant_ids)

    @api.constrains('step_delay_minutes')
    def _check_step_delay(self):
        for journey in self:
            if journey.step_delay_minutes < 1:
                raise ValidationError(_(
                    "Minimum delay between steps must be at least 1 minute, otherwise two "
                    "consecutive cron runs could push the same participant twice."
                ))

    def action_start(self):
        self.write({'state': 'running'})

    def action_pause(self):
        self.write({'state': 'paused'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})
