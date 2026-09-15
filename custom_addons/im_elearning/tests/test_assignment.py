from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import ImElearningCommon


@tagged('post_install', '-at_install')
class TestAssignment(ImElearningCommon):

    def _assign(self, deadline=None, employee=None, assigned=None):
        vals = {
            'channel_id': self.channel.id,
            'employee_id': (employee or self.employee).id,
            'date_deadline': deadline,
        }
        if assigned:
            vals['date_assigned'] = assigned
        elif deadline:
            vals['date_assigned'] = fields.Date.subtract(deadline, days=7)
        return self.env['im.course.assignment'].create(vals)

    def test_assignment_enrolls_employee(self):
        """Assigning enrols the employee, so progress can be measured."""
        assignment = self._assign()
        self.assertTrue(assignment.channel_partner_id)
        self.assertEqual(assignment.channel_partner_id.partner_id, self.partner_student)
        self.assertEqual(assignment.channel_partner_id.channel_id, self.channel)

    def test_state_not_started(self):
        assignment = self._assign()
        self.assertEqual(assignment.state, 'not_started')

    def test_state_in_progress(self):
        assignment = self._assign()
        assignment.channel_partner_id.write({'completion': 40})
        assignment.invalidate_recordset()
        self.assertEqual(assignment.state, 'in_progress')

    def test_state_done_by_completion(self):
        assignment = self._assign()
        assignment.channel_partner_id.write({'completion': 100})
        assignment.invalidate_recordset()
        self.assertEqual(assignment.state, 'done')

    def test_state_overdue(self):
        yesterday = fields.Date.subtract(fields.Date.context_today(self.env.user), days=1)
        assignment = self._assign(deadline=yesterday)
        self.assertEqual(assignment.state, 'overdue')

    def test_done_beats_overdue(self):
        """Finishing the course beats the deadline having passed."""
        yesterday = fields.Date.subtract(fields.Date.context_today(self.env.user), days=1)
        assignment = self._assign(deadline=yesterday)
        assignment.channel_partner_id.write({'completion': 100})
        assignment.invalidate_recordset()
        self.assertEqual(assignment.state, 'done')

    def test_search_state_matches_compute(self):
        """The dashboard filter must return what the status column displays."""
        yesterday = fields.Date.subtract(fields.Date.context_today(self.env.user), days=1)
        overdue = self._assign(deadline=yesterday)
        fresh = self._assign(employee=self.manager_employee)

        found_overdue = self.env['im.course.assignment'].search([('state', '=', 'overdue')])
        self.assertIn(overdue, found_overdue)
        self.assertNotIn(fresh, found_overdue)

        found_not_started = self.env['im.course.assignment'].search(
            [('state', '=', 'not_started')])
        self.assertIn(fresh, found_not_started)
        self.assertNotIn(overdue, found_not_started)

    def _other_employee(self, name):
        partner = self.env['res.partner'].create(
            {'name': name, 'email': '%s@example.com' % name.replace(' ', '')})
        return self.env['hr.employee'].create(
            {'name': name, 'work_contact_id': partner.id})

    def test_search_state_handles_several_states_at_once(self):
        """Filtering on two or more states must return their union."""
        today = fields.Date.context_today(self.env.user)
        yesterday = fields.Date.subtract(today, days=1)

        overdue = self._assign(deadline=yesterday)
        not_started = self._assign(employee=self._other_employee('Not started'))
        in_progress = self._assign(employee=self._other_employee('In progress'))
        in_progress.channel_partner_id.write({'completion': 40})
        done = self._assign(employee=self._other_employee('Finished'))
        done.channel_partner_id.write({'completion': 100})

        every = overdue | not_started | in_progress | done
        every.invalidate_recordset()
        self.assertEqual(
            [overdue.state, not_started.state, in_progress.state, done.state],
            ['overdue', 'not_started', 'in_progress', 'done'],
            "If the fixture is wrong, everything checked below means nothing")

        def found(operator, value):
            return self.env['im.course.assignment'].search(
                [('id', 'in', every.ids), ('state', operator, value)])

        self.assertEqual(found('in', ['done', 'overdue']), done | overdue)
        self.assertEqual(
            found('in', ['not_started', 'in_progress']), not_started | in_progress)
        self.assertEqual(
            found('in', ['done', 'overdue', 'not_started']),
            done | overdue | not_started)
        self.assertEqual(found('not in', ['done']), overdue | not_started | in_progress)
        self.assertEqual(found('not in', ['done', 'overdue']), not_started | in_progress)
        self.assertEqual(found('!=', 'removed'), every)

    def test_deadline_cannot_precede_assignment(self):
        yesterday = fields.Date.subtract(fields.Date.context_today(self.env.user), days=1)
        with self.assertRaises(ValidationError):
            self.env['im.course.assignment'].create({
                'channel_id': self.channel.id,
                'employee_id': self.employee.id,
                'date_assigned': fields.Date.context_today(self.env.user),
                'date_deadline': yesterday,
            })

    def test_cannot_assign_same_course_twice(self):
        self._assign()
        with self.assertRaises(Exception):
            self._assign()
            self.env.flush_all()

    def test_manager_is_picked_up(self):
        assignment = self._assign()
        self.assertEqual(assignment.manager_id, self.manager_employee)
        self.assertEqual(assignment.department_id, self.department)

    def test_reminder_cron_marks_sent_once(self):
        tomorrow = fields.Date.add(fields.Date.context_today(self.env.user), days=1)
        assignment = self._assign(deadline=tomorrow)
        self.env['im.course.assignment']._cron_remind_deadline()
        assignment.invalidate_recordset()
        self.assertTrue(assignment.reminder_sent)

        count = self.env['im.course.assignment']._cron_remind_deadline()
        self.assertEqual(count, 0)

    def test_cron_without_a_theme_marks_nothing(self):
        """No template means no mail went out, so nothing may be flagged as
        sent, or a theme installed later would never reach these people."""
        tomorrow = fields.Date.add(fields.Date.context_today(self.env.user), days=1)
        assignment = self._assign(deadline=tomorrow)
        Channel = type(self.env['slide.channel'])
        with patch.object(Channel, '_im_get_mail_template',
                          return_value=self.env['mail.template']):
            count = self.env['im.course.assignment']._cron_remind_deadline()
        assignment.invalidate_recordset()
        self.assertEqual(count, 0)
        self.assertFalse(assignment.reminder_sent)

    def test_reminder_skips_completed(self):
        tomorrow = fields.Date.add(fields.Date.context_today(self.env.user), days=1)
        assignment = self._assign(deadline=tomorrow)
        assignment.channel_partner_id.write({'completion': 100})
        assignment.invalidate_recordset()
        self.env['im.course.assignment']._cron_remind_deadline()
        assignment.invalidate_recordset()
        self.assertFalse(assignment.reminder_sent, "No reminder once the course is finished")

    def test_overdue_cron(self):
        yesterday = fields.Date.subtract(fields.Date.context_today(self.env.user), days=1)
        assignment = self._assign(deadline=yesterday)
        self.env['im.course.assignment']._cron_notify_overdue()
        assignment.invalidate_recordset()
        self.assertTrue(assignment.overdue_notified)

    def test_wizard_assigns_department(self):
        wizard = self.env['im.course.assignment.wizard'].create({
            'channel_id': self.channel.id,
            'department_ids': [(4, self.department.id)],
        })
        wizard.action_assign()
        assignment = self.env['im.course.assignment'].search([
            ('channel_id', '=', self.channel.id),
            ('employee_id', '=', self.employee.id),
        ])
        self.assertEqual(len(assignment), 1)

    def test_wizard_skips_already_assigned(self):
        self._assign()
        wizard = self.env['im.course.assignment.wizard'].create({
            'channel_id': self.channel.id,
            'employee_ids': [(4, self.employee.id)],
        })
        wizard.action_assign()
        assignments = self.env['im.course.assignment'].search([
            ('channel_id', '=', self.channel.id),
            ('employee_id', '=', self.employee.id),
        ])
        self.assertEqual(len(assignments), 1, "The same course must not be assigned twice")

    def test_wizard_requires_target(self):
        wizard = self.env['im.course.assignment.wizard'].create({
            'channel_id': self.channel.id,
        })
        with self.assertRaises(UserError):
            wizard.action_assign()

    def test_unenrolled_learner_is_not_reported_as_in_progress(self):
        """CE drops a learner from the course on their last failed attempt."""
        assignment = self._assign()
        assignment.channel_partner_id.write({'completion': 60})
        assignment.invalidate_recordset()
        self.assertEqual(assignment.state, 'in_progress')

        self.channel._remove_membership(self.partner_student.ids)
        assignment.invalidate_recordset()

        self.assertFalse(assignment.is_enrolled)
        self.assertEqual(assignment.state, 'removed')
        self.assertIn(
            assignment,
            self.env['im.course.assignment'].search([('state', '=', 'removed')]))
        self.assertNotIn(
            assignment,
            self.env['im.course.assignment'].search([('state', '=', 'in_progress')]))

    def test_reenroll_restores_membership(self):
        """A mandatory course does not end with a failed exam."""
        assignment = self._assign()
        self.channel._remove_membership(self.partner_student.ids)
        assignment.invalidate_recordset()
        self.assertEqual(assignment.state, 'removed')

        assignment.action_reenroll()
        assignment.invalidate_recordset()
        self.assertTrue(assignment.is_enrolled)
        self.assertNotEqual(assignment.state, 'removed')

    def test_completed_learner_stays_done_even_if_unenrolled(self):
        assignment = self._assign()
        assignment.channel_partner_id.write({'completion': 100})
        self.channel._remove_membership(self.partner_student.ids)
        assignment.invalidate_recordset()
        self.assertEqual(assignment.state, 'done')
