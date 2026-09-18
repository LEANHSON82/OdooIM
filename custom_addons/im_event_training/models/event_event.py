from odoo import models, fields, api, _
from odoo.exceptions import UserError

class EventType(models.Model):
    _inherit = 'event.type'

    is_training = fields.Boolean(
        string='Is Training Course',
        default=False,
        help='Check if events created from this template are training courses by default.'
    )

class EventEvent(models.Model):
    """Training course: sessions, attendance threshold, certificates."""

    _inherit = 'event.event'

    is_training = fields.Boolean(
        string='Is Training Course',
        default=False,
        help='Check if this event is a multi-session training course requiring attendance and certificates.'
    )
    session_ids = fields.One2many('event.session', 'event_id', string='Training Sessions', copy=True)
    session_count = fields.Integer(string='Session Count', compute='_compute_session_count')
    certificate_threshold = fields.Float(
        string='Certificate Threshold (%)',
        default=80.0,
        help='Minimum attendance percentage required to be eligible for a certificate.'
    )

    @api.onchange('event_type_id')
    def _onchange_event_type_id_training(self):
        if self.event_type_id:
            self.is_training = self.event_type_id.is_training

    @api.depends('session_ids')
    def _compute_session_count(self):
        for event in self:
            event.session_count = len(event.session_ids)

    def action_generate_attendance(self):
        """Fill in the attendance rows that are still missing."""
        self.ensure_one()
        if not self.session_ids:
            raise UserError(_("Please create at least 1 session before generating attendance records."))
        
        created_count = len(self.registration_ids._generate_missing_attendance())

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Attendance Generated Successfully'),
                'message': _('Created %s new attendance records.') % created_count,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_issue_certificates_bulk(self):
        """Issue certificates to every eligible attendee at once."""
        self.ensure_one()
        eligible_registrations = self.registration_ids.filtered(
            lambda r: r.state != 'cancel' and r.is_certificate_eligible and r.certificate_state != 'issued'
        )
        if not eligible_registrations:
            raise UserError(_("No eligible attendees found (or all eligible attendees have already been issued certificates)."))

        issued_count = 0
        for reg in eligible_registrations:
            reg.action_issue_certificate()
            issued_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Certificates Issued'),
                'message': _('Successfully issued certificates for %s attendees.') % issued_count,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_sessions(self):
        self.ensure_one()
        return {
            'name': _('Training Sessions'),
            'type': 'ir.actions.act_window',
            'res_model': 'event.session',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }

    def unlink(self):
        # Deleting would take attendance history and certificates with it.
        blocked = self.filtered('registration_ids')
        if blocked:
            raise UserError(_(
                "Cannot delete the following event(s) because attendees are already "
                "registered: %s.\n\n"
                "Registrations carry attendance history, issued certificates and sales "
                "order links. Cancel the registrations first, or archive the event instead."
            ) % ', '.join(blocked.mapped('name')))
        return super().unlink()
