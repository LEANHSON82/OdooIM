import pytz
from datetime import timedelta
from odoo import models, fields, api, _

# Messages are never sent between 22:00 and 07:00 local time.
QUIET_START_HOUR = 22
QUIET_END_HOUR = 7

DEFAULT_STEP_MINUTES = 5

class ImJourneyParticipant(models.Model):
    """One lead travelling through one journey.

    Position is `current_node_id`; the cron picks the participant up again
    once `next_execution_time` is due.
    """

    _name = 'im.journey.participant'
    _description = 'Marketing Journey Participant'
    _order = 'id desc'

    journey_id = fields.Many2one('im.journey', string='Journey', required=True, ondelete='cascade')
    lead_id = fields.Many2one('crm.lead', string='Lead', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Customer', related='lead_id.partner_id', store=True, readonly=True)
    current_node_id = fields.Many2one('im.journey.node', string='Current Node')
    next_execution_time = fields.Datetime(string='Next Execution Time', default=fields.Datetime.now)
    last_executed_time = fields.Datetime(string='Last Executed Time')
    state = fields.Selection([
        ('running', 'Running'),
        ('done', 'Done'),
        ('exited', 'Exited'),
    ], string='Status', default='running', required=True)
    exit_reason = fields.Char(string='Exit Reason')
    run_count = fields.Integer(string='Run Number', default=1, readonly=True)

    _participant_uniq = models.Constraint(
        'unique(journey_id, lead_id)',
        'A lead can only enter the same journey once!'
    )

    @api.model
    def _cron_process_participants(self):
        """Advance every participant that is due. Runs every 5 minutes."""
        # Paused journeys are skipped, and their participants keep their place.
        now = fields.Datetime.now()
        participants = self.search([
            ('journey_id.state', '=', 'running'),
            ('state', '=', 'running'),
            '|', ('next_execution_time', '=', False), ('next_execution_time', '<=', now),
        ])
        for participant in participants:
            participant.process_next_step()

    def _get_step_delay(self):
        """Minimum gap before this participant is due again."""
        self.ensure_one()
        return timedelta(minutes=self.journey_id.step_delay_minutes or DEFAULT_STEP_MINUTES)

    def _get_quiet_hours_deferral(self):
        """Return when to retry if we are inside quiet hours, else False.

        The timezone comes from the journey, not from the user running the
        cron: that would break silently the day OdooBot gets a timezone.
        """
        self.ensure_one()
        tz_name = self.journey_id.quiet_hours_tz or 'Asia/Ho_Chi_Minh'
        local_tz = pytz.timezone(tz_name)
        local_dt = pytz.utc.localize(fields.Datetime.now()).astimezone(local_tz)

        if QUIET_END_HOUR <= local_dt.hour < QUIET_START_HOUR:
            return False

        # Before midnight we defer to tomorrow morning, after midnight to today.
        target = local_dt + timedelta(days=1) if local_dt.hour >= QUIET_START_HOUR else local_dt
        naive_target = target.replace(
            tzinfo=None, hour=QUIET_END_HOUR, minute=0, second=0, microsecond=0
        )
        return local_tz.localize(naive_target).astimezone(pytz.utc).replace(tzinfo=None)

    def _log(self, node, status, content, action_type=None):
        """Write one line of the journey log for this step."""
        return self.env['im.journey.log'].create({
            'participant_id': self.id,
            'node_id': node.id,
            'action_type': action_type or node.action_type or 'system',
            'status': status,
            'message_content': content,
            'execution_time': fields.Datetime.now(),
            'run_number': self.run_count,
        })

    def _send_node_message(self, node):
        """Send one message for this node, at most once per run.

        NOT WIRED YET: this only writes the log row. Plug the real Zalo ZNS
        call or mail.mail here, keep the already_sent guard, and log
        'failed' instead of 'success' when the channel refuses.
        """
        self.ensure_one()
        # The log is the source of truth against double sending; run_number
        # keeps a re-enrolled lead from being blocked by its older run.
        already_sent = self.env['im.journey.log'].search_count([
            ('participant_id', '=', self.id),
            ('node_id', '=', node.id),
            ('status', '=', 'success'),
            ('run_number', '=', self.run_count),
        ])
        if already_sent:
            return False
        content = node.message_template or _("Auto %s message sent to Lead: %s") % (
            (node.action_type or '').upper(), self.lead_id.name
        )
        self._log(node, 'success', content)
        return True

    def _check_exit_condition(self):
        """Leave the journey when the lead is archived or changed stage."""
        self.ensure_one()
        lead = self.lead_id

        if not lead.active:
            self.write({
                'state': 'exited',
                'exit_reason': _("Lead is archived or marked as lost."),
            })
            return True

        trigger_stage = self.journey_id.trigger_stage_id
        if trigger_stage and lead.stage_id != trigger_stage:
            self.write({
                'state': 'exited',
                'exit_reason': _("Lead moved stage from '%s' to '%s'.") % (
                    trigger_stage.name, lead.stage_id.name
                ),
            })
            return True
        return False

    def process_next_step(self, ignore_quiet_hours=False):
        """Run the current node and move the participant to the next one."""
        self.ensure_one()
        if self.state != 'running' or self.journey_id.state != 'running':
            return False

        if self._check_exit_condition():
            return False

        node = self.current_node_id
        if not node:
            self.write({'state': 'done'})
            return False

        # Default due date is now + the journey's minimum gap; a wait node
        # replaces it with its own duration below.
        now = fields.Datetime.now()
        step_due = now + self._get_step_delay()

        if node.node_type == 'action':
            if not ignore_quiet_hours:
                deferred_to = self._get_quiet_hours_deferral()
                if deferred_to:
                    self._log(
                        node, 'postponed',
                        _("Quiet hours %02d:00-%02d:00, postponed to %s.")
                        % (QUIET_START_HOUR, QUIET_END_HOUR, deferred_to),
                    )
                    self.write({'next_execution_time': deferred_to})
                    return False
            self._send_node_message(node)
            next_node = node.next_node_id

        elif node.node_type == 'wait':
            delta = (timedelta(hours=node.wait_duration) if node.wait_unit == 'hours'
                     else timedelta(days=node.wait_duration))
            step_due = now + delta
            next_node = node.next_node_id

        elif node.node_type == 'condition':
            if node.condition_type == 'has_phone':
                is_ok = bool(self.lead_id.phone)
            elif node.condition_type == 'has_email':
                is_ok = bool(self.lead_id.email_from)
            else:
                is_ok = False
            next_node = node.next_node_if_true_id if is_ok else node.next_node_if_false_id

        else:
            return False

        vals = {
            'current_node_id': next_node.id if next_node else False,
            'next_execution_time': step_due,
            'last_executed_time': now,
        }
        if not next_node:
            vals['state'] = 'done'
        self.write(vals)
        return True

    def action_restart_run(self):
        """Send the lead through the journey again as a new run."""
        # Old logs stay; the higher run_count is what unblocks the sends.
        for participant in self:
            first_node = participant.journey_id.node_ids.sorted('sequence')[:1]
            participant.write({
                'run_count': participant.run_count + 1,
                'current_node_id': first_node.id if first_node else False,
                'next_execution_time': fields.Datetime.now(),
                'last_executed_time': False,
                'exit_reason': False,
                'state': 'running',
            })
        return True
