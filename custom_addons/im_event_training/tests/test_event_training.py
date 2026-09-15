from datetime import datetime, timedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from odoo import fields

class TestEventTraining(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Event = cls.env['event.event']
        cls.Session = cls.env['event.session']
        cls.Registration = cls.env['event.registration']
        cls.Ticket = cls.env['event.event.ticket']

        cls.event = cls.Event.create({
            'name': 'Advanced Python Training',
            'is_training': True,
            'date_begin': fields.Datetime.now(),
            'date_end': fields.Datetime.now() + timedelta(days=5),
            'certificate_threshold': 80.0,
        })

        cls.sessions = cls.Session.create([
            {'name': f'Session {i+1}', 'event_id': cls.event.id, 'sequence': i+1}
            for i in range(5)
        ])

        cls.reg_pass = cls.Registration.create({
            'name': 'Attendee Full Presence',
            'email': 'full@example.com',
            'event_id': cls.event.id,
        })
        cls.reg_fail = cls.Registration.create({
            'name': 'Attendee Absent',
            'email': 'absent@example.com',
            'event_id': cls.event.id,
        })

    def test_01_generate_attendance_and_ratio(self):
        self.event.action_generate_attendance()
        
        self.assertEqual(len(self.reg_pass.attendance_ids), 5)
        self.assertEqual(len(self.reg_fail.attendance_ids), 5)

        pass_attendances = self.reg_pass.attendance_ids
        for att in pass_attendances[:4]:
            att.write({'is_present': True})

        self.assertEqual(self.reg_pass.attended_session_count, 4)
        self.assertEqual(self.reg_pass.attendance_ratio, 80.0)
        self.assertTrue(self.reg_pass.is_certificate_eligible)

        fail_attendances = self.reg_fail.attendance_ids
        for att in fail_attendances[:3]:
            att.write({'is_present': True})

        self.assertEqual(self.reg_fail.attended_session_count, 3)
        self.assertEqual(self.reg_fail.attendance_ratio, 60.0)
        self.assertFalse(self.reg_fail.is_certificate_eligible)

    def test_02_issue_certificate(self):
        self.event.action_generate_attendance()

        self.reg_pass.attendance_ids.write({'is_present': True})
        self.assertTrue(self.reg_pass.is_certificate_eligible)

        self.reg_pass.action_issue_certificate()
        self.assertEqual(self.reg_pass.certificate_state, 'issued')
        self.assertTrue(bool(self.reg_pass.certificate_number))

        with self.assertRaises(UserError):
            self.reg_fail.action_issue_certificate()

    def test_03_early_bird_ticket_logic(self):
        now = fields.Datetime.now()
        
        ticket = self.Ticket.create({
            'name': 'Early Bird Ticket',
            'event_id': self.event.id,
            'is_early_bird': True,
            'early_bird_deadline': now + timedelta(days=1),
            'early_bird_max_qty': 2,
            'price_early_bird': 500000.0,
            'price_standard': 800000.0,
        })

        self.assertTrue(ticket.is_early_bird_active)
        self.assertEqual(ticket.price, 500000.0)

        ticket.write({'early_bird_deadline': now - timedelta(days=1)})
        self.assertFalse(ticket.is_early_bird_active)
        self.assertEqual(ticket.price, 800000.0)

        ticket.write({'early_bird_deadline': now + timedelta(days=1)})
        self.assertTrue(ticket.is_early_bird_active)

        self.Registration.create({
            'name': 'User 1',
            'event_id': self.event.id,
            'event_ticket_id': ticket.id,
        })
        self.Registration.create({
            'name': 'User 2',
            'event_id': self.event.id,
            'event_ticket_id': ticket.id,
        })

        ticket._compute_early_bird_sold_qty()
        ticket._compute_is_early_bird_active()
        self.assertEqual(ticket.early_bird_sold_qty, 2)
        self.assertFalse(ticket.is_early_bird_active)
        self.assertEqual(ticket.price, 800000.0)

    def test_04_delete_event_with_registrations_is_blocked(self):
        new_event = self.Event.create({'name': 'Event To Delete', 'date_begin': fields.Datetime.now(), 'date_end': fields.Datetime.now() + timedelta(days=1)})
        reg = self.Registration.create({'name': 'Attendee 1', 'event_id': new_event.id})

        with self.assertRaises(UserError):
            new_event.unlink()
        self.assertTrue(new_event.exists())
        self.assertTrue(reg.exists(), "khong duoc xoa lan sang ban ghi dang ky")

        reg.unlink()
        new_event.unlink()
        self.assertFalse(new_event.exists())

    def test_06_late_registration_gets_attendance(self):
        self.event.action_generate_attendance()
        late = self.Registration.create({
            'name': 'Attendee Late', 'email': 'late@example.com', 'event_id': self.event.id,
        })
        self.assertEqual(len(late.attendance_ids), 5)

    def test_07_new_session_backfills_attendance(self):
        self.event.action_generate_attendance()
        self.Session.create({'name': 'Session 6', 'event_id': self.event.id, 'sequence': 6})
        self.assertEqual(len(self.reg_pass.attendance_ids), 6)
        self.assertEqual(self.reg_pass.total_session_count, 6)

    def test_08_threshold_change_recomputes_eligibility(self):
        self.event.action_generate_attendance()
        self.reg_fail.attendance_ids[:3].write({'is_present': True})
        self.assertEqual(self.reg_fail.attendance_ratio, 60.0)
        self.assertFalse(self.reg_fail.is_certificate_eligible)

        self.event.write({'certificate_threshold': 50.0})
        self.assertTrue(self.reg_fail.is_certificate_eligible)

    def test_09_price_reduce_is_the_price_customer_pays(self):
        now = fields.Datetime.now()
        ticket = self.Ticket.create({
            'name': 'EB Path', 'event_id': self.event.id, 'is_early_bird': True,
            'early_bird_deadline': now + timedelta(days=1), 'early_bird_max_qty': 10,
            'price_early_bird': 300000.0, 'price_standard': 900000.0,
        })
        self.assertEqual(ticket.price_reduce, 300000.0)

        ticket.write({'early_bird_deadline': now - timedelta(seconds=1)})
        self.assertEqual(ticket.price_reduce, 900000.0)
        self.assertEqual(ticket.price, 900000.0)

    def test_10_product_change_does_not_clobber_early_bird_price(self):
        now = fields.Datetime.now()
        ticket = self.Ticket.create({
            'name': 'EB Product', 'event_id': self.event.id, 'is_early_bird': True,
            'early_bird_deadline': now + timedelta(days=1), 'early_bird_max_qty': 10,
            'price_early_bird': 300000.0, 'price_standard': 900000.0,
        })
        self.assertEqual(ticket.price, 300000.0)

        product = self.env['product.product'].create({
            'name': 'Ticket Product', 'list_price': 1234567.0,
            'type': 'service', 'service_tracking': 'event',
        })
        ticket.write({'product_id': product.id})
        self.assertEqual(ticket.price, 300000.0)

    def test_11_cron_refreshes_expired_early_bird(self):
        now = fields.Datetime.now()
        ticket = self.Ticket.create({
            'name': 'EB Cron', 'event_id': self.event.id, 'is_early_bird': True,
            'early_bird_deadline': now + timedelta(hours=1), 'early_bird_max_qty': 10,
            'price_early_bird': 300000.0, 'price_standard': 900000.0,
        })
        self.assertEqual(ticket.price, 300000.0)
        self.env.flush_all()

        self.env.cr.execute(
            "UPDATE event_event_ticket SET early_bird_deadline = %s WHERE id = %s",
            (now - timedelta(hours=1), ticket.id),
        )
        ticket.invalidate_recordset()
        self.assertEqual(ticket.price, 300000.0, "gia trong DB van la gia cu truoc khi cron chay")

        self.Ticket._cron_refresh_early_bird()
        ticket.invalidate_recordset()
        self.assertFalse(ticket.is_early_bird_active)
        self.assertEqual(ticket.price, 900000.0)

    def test_12_normal_ticket_keeps_manual_price_when_sold(self):
        product = self.env['product.product'].create({
            'name': 'Normal Ticket Product', 'list_price': 1000000.0,
            'type': 'service', 'service_tracking': 'event',
        })
        ticket = self.Ticket.create({
            'name': 'Ve thuong', 'event_id': self.event.id, 'product_id': product.id,
        })
        ticket.write({'price': 500000.0})
        self.env.flush_all()

        self.Registration.create({
            'name': 'Khach mua ve thuong', 'event_id': self.event.id,
            'event_ticket_id': ticket.id,
        })
        self.env.flush_all()
        ticket.invalidate_recordset()
        self.assertEqual(ticket.price, 500000.0,
                         "gia admin dat tay bi ghi de bang gia product khi co nguoi dang ky")

    def test_13_cancelled_registration_cannot_get_certificate(self):
        self.event.action_generate_attendance()
        self.reg_pass.attendance_ids.write({'is_present': True})
        self.reg_pass.write({'state': 'cancel'})

        with self.assertRaises(UserError):
            self.reg_pass.action_issue_certificate()
        self.assertEqual(self.reg_pass.certificate_state, 'draft')
        self.assertFalse(self.reg_pass.certificate_number)

    def test_14_early_bird_quota_ignores_standard_price_sales(self):
        now = fields.Datetime.now()
        ticket = self.Ticket.create({
            'name': 'EB Quota', 'event_id': self.event.id, 'is_early_bird': True,
            'early_bird_deadline': now - timedelta(days=1),
            'early_bird_max_qty': 10,
            'price_early_bird': 300000.0, 'price_standard': 900000.0,
        })
        for i in range(10):
            self.Registration.create({
                'name': f'Std {i}', 'event_id': self.event.id, 'event_ticket_id': ticket.id,
            })
        self.env.flush_all()
        ticket.invalidate_recordset()
        self.assertEqual(ticket.early_bird_sold_qty, 0, "chua ai mua o gia early-bird")
        self.assertEqual(ticket.price, 900000.0)

        ticket.write({'early_bird_deadline': now + timedelta(days=7)})
        self.env.flush_all()
        ticket.invalidate_recordset()
        self.assertTrue(ticket.is_early_bird_active, "dot khuyen mai thu hai phai chay duoc")
        self.assertEqual(ticket.price, 300000.0)

    def test_15_early_bird_sale_flag_respects_quota(self):
        now = fields.Datetime.now()
        ticket = self.Ticket.create({
            'name': 'EB Flag', 'event_id': self.event.id, 'is_early_bird': True,
            'early_bird_deadline': now + timedelta(days=1), 'early_bird_max_qty': 2,
            'price_early_bird': 300000.0, 'price_standard': 900000.0,
        })
        regs = [self.Registration.create({
            'name': f'Buyer {i}', 'event_id': self.event.id, 'event_ticket_id': ticket.id,
        }) for i in range(3)]
        self.env.flush_all()

        self.assertTrue(regs[0].is_early_bird_sale)
        self.assertTrue(regs[1].is_early_bird_sale)
        self.assertFalse(regs[2].is_early_bird_sale, "nguoi thu 3 da vuot quota 2 ve")
        self.assertEqual(ticket.early_bird_sold_qty, 2)

        regs[0].write({'state': 'cancel'})
        self.env.flush_all()
        ticket.invalidate_recordset()
        self.assertEqual(ticket.early_bird_sold_qty, 1)
        self.assertTrue(ticket.is_early_bird_active)

    def test_16_issued_certificate_keeps_snapshot_and_can_be_revoked(self):
        self.event.write({'certificate_threshold': 50.0})
        self.event.action_generate_attendance()
        self.reg_fail.attendance_ids[:3].write({'is_present': True})
        self.reg_fail.action_issue_certificate()

        self.assertEqual(self.reg_fail.certificate_state, 'issued')
        self.assertEqual(self.reg_fail.certificate_ratio, 60.0)
        self.assertEqual(self.reg_fail.certificate_threshold_issued, 50.0)
        serial = self.reg_fail.certificate_number

        self.event.write({'certificate_threshold': 90.0})
        self.assertFalse(self.reg_fail.is_certificate_eligible)
        self.assertEqual(self.reg_fail.certificate_ratio, 60.0, "snapshot khong duoc doi theo")
        self.assertEqual(self.reg_fail.certificate_threshold_issued, 50.0)

        self.reg_fail.action_revoke_certificate()
        self.assertEqual(self.reg_fail.certificate_state, 'revoked')
        self.assertEqual(self.reg_fail.certificate_number, serial,
                         "thu hoi la su kien duoc ghi nhan, khong phai xoa dau vet")

    def test_17_excused_sessions_leave_the_denominator(self):
        self.event.action_generate_attendance()
        late = self.Registration.create({
            'name': 'Vao muon', 'email': 'late2@example.com', 'event_id': self.event.id,
        })
        self.assertEqual(late.total_session_count, 5)

        late.attendance_ids[:3].write({'is_excused': True})
        late.attendance_ids[3:].write({'is_present': True})

        self.assertEqual(late.total_session_count, 2)
        self.assertEqual(late.attended_session_count, 2)
        self.assertEqual(late.attendance_ratio, 100.0)
        self.assertTrue(late.is_certificate_eligible)

    def test_18_bulk_marking_covers_every_selected_record(self):
        self.event.action_generate_attendance()
        Attendance = self.env['event.session.attendance']

        first_three = self.sessions[:3]
        selection = Attendance.search([('session_id', 'in', first_three.ids)])
        self.assertEqual(len(selection), 6)

        selection.action_mark_present()
        self.assertTrue(all(selection.mapped('is_present')))
        self.assertEqual(self.reg_pass.attended_session_count, 3)
        self.assertEqual(self.reg_fail.attended_session_count, 3)

        excused = self.reg_fail.attendance_ids.filtered(
            lambda a: a.session_id in first_three
        )
        excused.action_mark_excused()
        self.assertFalse(any(excused.mapped('is_present')))
        self.assertEqual(self.reg_fail.total_session_count, 2)
        self.assertEqual(self.reg_fail.attended_session_count, 0)

        excused.action_mark_absent()
        self.assertFalse(any(excused.mapped('is_excused')))
        self.assertEqual(self.reg_fail.total_session_count, 5)

    def test_19_open_attendance_action_is_scoped_to_the_session(self):
        self.event.action_generate_attendance()
        session = self.sessions[0]
        action = session.action_open_attendance()

        self.assertEqual(action['res_model'], 'event.session.attendance')
        self.assertEqual(action['domain'], [('session_id', '=', session.id)])
        opened = self.env['event.session.attendance'].search(action['domain'])
        self.assertEqual(opened, session.attendance_ids)

    def test_05_event_type_is_training_inheritance(self):
        event_type = self.env['event.type'].create({
            'name': 'Training Template',
            'is_training': True,
        })
        event = self.Event.create({
            'name': 'Course From Template',
            'event_type_id': event_type.id,
            'date_begin': fields.Datetime.now(),
            'date_end': fields.Datetime.now() + timedelta(days=2),
        })
        event._onchange_event_type_id_training()
        self.assertTrue(event.is_training)
