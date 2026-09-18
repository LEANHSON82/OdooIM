from odoo import models, fields, api, _

class EventSession(models.Model):
    """One session of a multi-session training course."""

    _name = 'event.session'
    _description = 'Event Training Session'
    _order = 'sequence, date_start, id'

    name = fields.Char(string='Session Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    event_id = fields.Many2one('event.event', string='Event', required=True, ondelete='cascade')
    date_start = fields.Datetime(string='Start Time')
    date_end = fields.Datetime(string='End Time')
    description = fields.Text(string='Notes / Description')
    
    attendance_ids = fields.One2many('event.session.attendance', 'session_id', string='Attendance Records')
    present_count = fields.Integer(string='Present Count', compute='_compute_attendance_stats')
    total_attendance_count = fields.Integer(string='Total Attendees', compute='_compute_attendance_stats')

    @api.depends('attendance_ids.is_present')
    def _compute_attendance_stats(self):
        for session in self:
            session.total_attendance_count = len(session.attendance_ids)
            session.present_count = len(session.attendance_ids.filtered(lambda a: a.is_present))

    @api.model_create_multi
    def create(self, vals_list):
        sessions = super().create(vals_list)
        # A new session needs an attendance row for everyone already enrolled.
        sessions.event_id.registration_ids._generate_missing_attendance()
        return sessions

    def action_open_attendance(self):
        self.ensure_one()
        return {
            'name': _('Điểm danh: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'event.session.attendance',
            'view_mode': 'list',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id},
        }

class EventSessionAttendance(models.Model):
    """One row per session and attendee: present, absent or excused."""

    _name = 'event.session.attendance'
    _description = 'Session Attendance Record'
    _order = 'session_id, registration_id'

    session_id = fields.Many2one('event.session', string='Session', required=True, ondelete='cascade')
    registration_id = fields.Many2one('event.registration', string='Attendee Registration', required=True, ondelete='cascade')
    is_present = fields.Boolean(string='Present', default=False)
    is_excused = fields.Boolean(
        string='Excused',
        default=False,
        help='Excused sessions are removed from this attendee\'s attendance rate '
             '(mid-course enrolment, class transfer, make-up session...).'
    )
    note = fields.Char(string='Note')

    _attendance_uniq = models.Constraint(
        'unique(session_id, registration_id)',
        'An attendee can only be marked once per session!'
    )

    def action_mark_present(self):
        return self.write({'is_present': True, 'is_excused': False})

    def action_mark_absent(self):
        return self.write({'is_present': False, 'is_excused': False})

    def action_mark_excused(self):
        return self.write({'is_present': False, 'is_excused': True})
