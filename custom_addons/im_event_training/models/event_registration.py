from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class EventRegistration(models.Model):
    _inherit = 'event.registration'

    is_training = fields.Boolean(related='event_id.is_training', string='Is Training Course', readonly=True)
    attendance_ids = fields.One2many('event.session.attendance', 'registration_id', string='Attendance Details')
    attended_session_count = fields.Integer(
        string='Attended Sessions',
        compute='_compute_attendance_stats',
        store=True
    )
    total_session_count = fields.Integer(
        string='Countable Sessions',
        compute='_compute_attendance_stats',
        store=True,
        help='Total sessions minus the ones this attendee was excused from.'
    )
    attendance_ratio = fields.Float(
        string='Attendance Rate (%)',
        compute='_compute_attendance_stats',
        store=True
    )
    certificate_threshold = fields.Float(
        related='event_id.certificate_threshold',
        string='Certificate Threshold (%)',
        readonly=True
    )
    is_certificate_eligible = fields.Boolean(
        string='Certificate Eligible',
        compute='_compute_attendance_stats',
        store=True
    )
    certificate_number = fields.Char(
        string='Certificate Code',
        readonly=True,
        copy=False
    )
    certificate_date = fields.Datetime(
        string='Certificate Issue Date',
        readonly=True,
        copy=False
    )
    certificate_state = fields.Selection([
        ('draft', 'Not Issued'),
        ('issued', 'Issued'),
        ('revoked', 'Revoked'),
    ], string='Certificate Status', default='draft', copy=False)
    certificate_ratio = fields.Float(
        string='Attendance Rate at Issue (%)',
        readonly=True,
        copy=False
    )
    certificate_threshold_issued = fields.Float(
        string='Threshold at Issue (%)',
        readonly=True,
        copy=False
    )
    is_early_bird_sale = fields.Boolean(
        string='Bought at Early-Bird Price',
        readonly=True,
        copy=False,
        help='Set when this registration was actually sold within the early-bird window.'
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Stamp the early-bird flag now, at sale time. Deriving it later
        # would re-price old registrations once the window closes.
        # `taken` counts this batch too, so one create() cannot overshoot
        # the max quantity.
        Ticket = self.env['event.event.ticket']
        taken = defaultdict(int)
        for vals in vals_list:
            ticket = Ticket.browse(vals['event_ticket_id']) if vals.get('event_ticket_id') else Ticket
            if not ticket or not ticket.is_early_bird or vals.get('state') == 'cancel':
                continue
            if ticket._is_early_bird_now(extra_sold=taken[ticket.id]):
                vals['is_early_bird_sale'] = True
                taken[ticket.id] += 1

        registrations = super().create(vals_list)
        registrations._generate_missing_attendance()
        registrations._refresh_early_bird_tickets()
        return registrations

    def write(self, vals):
        """Re-price early-bird tickets when the state or the ticket changes."""
        res = super().write(vals)
        if 'state' in vals or 'event_ticket_id' in vals:
            self._refresh_early_bird_tickets()
        return res

    def _refresh_early_bird_tickets(self):
        """Force the ticket price to be recomputed after a sale.

        Ticket price depends on how many early-bird seats are gone, which
        the ORM cannot see from here on its own.
        """
        tickets = self.event_ticket_id.filtered('is_early_bird')
        if not tickets:
            return
        tickets.flush_recordset()
        self.env.add_to_compute(self.env['event.event.ticket']._fields['price'], tickets)
        tickets.flush_recordset()

    def _generate_missing_attendance(self):
        """Create only the missing attendance rows, so it is idempotent."""
        Attendance = self.env['event.session.attendance']
        vals_list = []
        for reg in self:
            if reg.state == 'cancel':
                continue
            covered = reg.attendance_ids.mapped('session_id')
            for session in reg.event_id.session_ids - covered:
                vals_list.append({
                    'session_id': session.id,
                    'registration_id': reg.id,
                    'is_present': False,
                })
        return Attendance.create(vals_list) if vals_list else Attendance

    @api.depends('attendance_ids.is_present', 'attendance_ids.is_excused',
                 'event_id.session_ids', 'event_id.certificate_threshold')
    def _compute_attendance_stats(self):
        """Attendance rate over the sessions that count for this attendee."""
        for reg in self:
            # Excused sessions leave the denominator: someone excused from
            # 2 of 10 sessions who attends the other 8 still scores 100%.
            excused = reg.attendance_ids.filtered('is_excused').mapped('session_id')
            countable = reg.event_id.session_ids - excused
            reg.total_session_count = len(countable)
            if reg.total_session_count > 0:
                attended = len(reg.attendance_ids.filtered(
                    lambda a: a.is_present and not a.is_excused
                ))
                reg.attended_session_count = attended
                ratio = round((attended / reg.total_session_count) * 100.0, 2)
                reg.attendance_ratio = ratio
                reg.is_certificate_eligible = (ratio >= reg.event_id.certificate_threshold)
            else:
                reg.attended_session_count = 0
                reg.attendance_ratio = 0.0
                reg.is_certificate_eligible = False

    def action_issue_certificate(self):
        """Issue the certificate, refusing anyone below the threshold."""
        for reg in self:
            if reg.state == 'cancel':
                raise UserError(_(
                    "Attendee '%s' has cancelled their registration, "
                    "so no certificate can be issued."
                ) % (reg.name or reg.partner_id.name))

            if not reg.is_certificate_eligible:
                raise UserError(_(
                    "Attendee '%s' is not eligible for a certificate. "
                    "Current attendance rate: %.2f%% (Required minimum: %.2f%%)."
                ) % (reg.name or reg.partner_id.name, reg.attendance_ratio, reg.certificate_threshold))

            if reg.certificate_state == 'issued' and reg.certificate_number:
                continue

            seq_code = 'event.training.certificate'
            code = reg.certificate_number or self.env['ir.sequence'].next_by_code(seq_code)
            if not code:
                code = f"CERT/{fields.Date.today().year}/{reg.id:05d}"

            # Freeze the rate and threshold that applied at issue time, so
            # a later change to the course rules cannot rewrite history.
            reg.write({
                'certificate_number': code,
                'certificate_date': fields.Datetime.now(),
                'certificate_state': 'issued',
                'certificate_ratio': reg.attendance_ratio,
                'certificate_threshold_issued': reg.certificate_threshold,
            })
        return True

    def action_revoke_certificate(self):
        """Revoke an issued certificate without deleting the record."""
        for reg in self:
            if reg.certificate_state != 'issued':
                raise UserError(_(
                    "Only an issued certificate can be revoked (attendee '%s')."
                ) % (reg.name or reg.partner_id.name))
            reg.write({'certificate_state': 'revoked'})
        return True
