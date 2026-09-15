import pytz
from datetime import datetime, timedelta
from unittest.mock import patch
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger
from odoo import fields

VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

def _utc_at(local_str):
    naive = datetime.strptime(local_str, '%Y-%m-%d %H:%M')
    return VN_TZ.localize(naive).astimezone(pytz.utc).replace(tzinfo=None)

class TestJourneyEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Stage = cls.env['crm.stage']
        cls.Lead = cls.env['crm.lead']
        cls.Journey = cls.env['im.journey']
        cls.Node = cls.env['im.journey.node']
        cls.Participant = cls.env['im.journey.participant']
        cls.Log = cls.env['im.journey.log']

        cls.stage_new = cls.Stage.create({'name': 'New', 'sequence': 1})
        cls.stage_qualified = cls.Stage.create({'name': 'Qualified', 'sequence': 2})

        cls.journey = cls.Journey.create({
            'name': 'New Lead Nurturing Journey',
            'trigger_stage_id': cls.stage_new.id,
        })

        cls.node_1_zns = cls.Node.create({
            'journey_id': cls.journey.id,
            'name': 'Node 1: Send Welcome ZNS',
            'sequence': 10,
            'node_type': 'action',
            'action_type': 'zns',
            'message_template': 'Welcome to our platform!',
        })

        cls.node_2_wait = cls.Node.create({
            'journey_id': cls.journey.id,
            'name': 'Node 2: Wait 2 Hours',
            'sequence': 20,
            'node_type': 'wait',
            'wait_duration': 2,
            'wait_unit': 'hours',
        })

        cls.node_3_email = cls.Node.create({
            'journey_id': cls.journey.id,
            'name': 'Node 3: Send Intro Email',
            'sequence': 30,
            'node_type': 'action',
            'action_type': 'email',
            'message_template': 'Here are the onboarding details...',
        })

        cls.node_1_zns.write({'next_node_id': cls.node_2_wait.id})
        cls.node_2_wait.write({'next_node_id': cls.node_3_email.id})

        cls.journey.action_start()

    def test_01_auto_trigger_lead_creation(self):
        lead = self.Lead.create({
            'name': 'Lead Customer A',
            'stage_id': self.stage_new.id,
            'phone': '0901234567',
            'email_from': 'nva@example.com',
        })

        participant = self.Participant.search([('lead_id', '=', lead.id), ('journey_id', '=', self.journey.id)])
        self.assertTrue(bool(participant))
        self.assertEqual(participant.state, 'running')
        self.assertEqual(participant.current_node_id, self.node_1_zns)

    def test_02_node_execution_and_mock_logging(self):
        lead = self.Lead.create({
            'name': 'Lead Customer B',
            'stage_id': self.stage_new.id,
            'phone': '0909876543',
        })
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)
        
        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=1)
        participant.process_next_step(ignore_quiet_hours=True)

        log = self.Log.search([('participant_id', '=', participant.id), ('node_id', '=', self.node_1_zns.id)])
        self.assertTrue(bool(log))
        self.assertEqual(log.status, 'success')
        self.assertEqual(log.action_type, 'zns')
        self.assertEqual(participant.current_node_id, self.node_2_wait)

        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=1)
        participant.process_next_step(ignore_quiet_hours=True)

        self.assertEqual(participant.current_node_id, self.node_3_email)
        self.assertTrue(participant.next_execution_time > fields.Datetime.now())

    def test_03_idempotency_protection(self):
        lead = self.Lead.create({
            'name': 'Lead Customer C',
            'stage_id': self.stage_new.id,
        })
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=1)
        participant.process_next_step(ignore_quiet_hours=True)

        logs_count = self.Log.search_count([('participant_id', '=', participant.id), ('node_id', '=', self.node_1_zns.id)])
        self.assertEqual(logs_count, 1)

        participant.current_node_id = self.node_1_zns
        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=1)
        participant.process_next_step(ignore_quiet_hours=True)

        logs_count_after = self.Log.search_count([('participant_id', '=', participant.id), ('node_id', '=', self.node_1_zns.id)])
        self.assertEqual(logs_count_after, 1)

    def test_04_exit_condition_when_stage_changed(self):
        lead = self.Lead.create({
            'name': 'Lead Customer D',
            'stage_id': self.stage_new.id,
        })
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        lead.write({'stage_id': self.stage_qualified.id})

        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=1)
        participant.process_next_step(ignore_quiet_hours=True)

        self.assertEqual(participant.state, 'exited')
        self.assertTrue('stage' in (participant.exit_reason or '').lower())

    def _run_cron_at(self, participant, local_str):
        frozen = _utc_at(local_str)
        participant.next_execution_time = frozen - timedelta(minutes=1)
        with patch.object(fields.Datetime, 'now', staticmethod(lambda: frozen)):
            self.Participant._cron_process_participants()

    def test_06_cron_twice_does_not_double_step(self):
        lead = self.Lead.create({
            'name': 'Lead Idempotent Cron', 'stage_id': self.stage_new.id, 'phone': '0912345678',
        })
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)
        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=5)

        self.Participant._cron_process_participants()
        logs_after_1 = self.Log.search_count([('participant_id', '=', participant.id)])
        node_after_1 = participant.current_node_id

        self.Participant._cron_process_participants()
        logs_after_2 = self.Log.search_count([('participant_id', '=', participant.id)])

        self.assertEqual(logs_after_1, 1, "lan cron dau phai gui dung 1 tin")
        self.assertEqual(logs_after_2, logs_after_1, "lan cron thu hai khong duoc gui them")
        self.assertEqual(participant.current_node_id, node_after_1,
                         "lan cron thu hai khong duoc chuyen buoc")
        self.assertTrue(participant.next_execution_time > fields.Datetime.now(),
                        "sau moi buoc phai co han thuc thi moi o tuong lai")

    def test_07_quiet_hours_defer_to_next_7am(self):
        self.env.user.tz = 'Asia/Ho_Chi_Minh'
        lead = self.Lead.create({'name': 'Lead Night', 'stage_id': self.stage_new.id})
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        self._run_cron_at(participant, '2026-08-10 22:30')

        self.assertFalse(self.Log.search_count([
            ('participant_id', '=', participant.id), ('status', '=', 'success')]))
        self.assertEqual(self.Log.search_count([
            ('participant_id', '=', participant.id), ('status', '=', 'postponed')]), 1)
        self.assertEqual(participant.current_node_id, self.node_1_zns)

        due_local = pytz.utc.localize(participant.next_execution_time).astimezone(VN_TZ)
        self.assertEqual(due_local.strftime('%Y-%m-%d %H:%M'), '2026-08-11 07:00')

    def test_08_quiet_hours_early_morning_defers_same_day(self):
        self.env.user.tz = 'Asia/Ho_Chi_Minh'
        lead = self.Lead.create({'name': 'Lead Dawn', 'stage_id': self.stage_new.id})
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        self._run_cron_at(participant, '2026-08-10 03:00')

        due_local = pytz.utc.localize(participant.next_execution_time).astimezone(VN_TZ)
        self.assertEqual(due_local.strftime('%Y-%m-%d %H:%M'), '2026-08-10 07:00')

    def test_09_quiet_hours_boundaries(self):
        self.env.user.tz = 'Asia/Ho_Chi_Minh'
        for local_str, should_send in [('2026-08-10 07:00', True),
                                       ('2026-08-10 21:59', True),
                                       ('2026-08-10 22:00', False)]:
            lead = self.Lead.create({'name': 'Lead ' + local_str, 'stage_id': self.stage_new.id})
            participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)
            self._run_cron_at(participant, local_str)
            sent = self.Log.search_count([
                ('participant_id', '=', participant.id), ('status', '=', 'success')])
            self.assertEqual(bool(sent), should_send, 'sai o moc %s' % local_str)

    def test_10_quiet_hours_does_not_spam_logs(self):
        self.env.user.tz = 'Asia/Ho_Chi_Minh'
        lead = self.Lead.create({'name': 'Lead Spam', 'stage_id': self.stage_new.id})
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        frozen = _utc_at('2026-08-10 23:00')
        participant.next_execution_time = frozen - timedelta(minutes=1)
        with patch.object(fields.Datetime, 'now', staticmethod(lambda: frozen)):
            for _ in range(5):
                self.Participant._cron_process_participants()

        self.assertEqual(self.Log.search_count([
            ('participant_id', '=', participant.id), ('status', '=', 'postponed')]), 1)

    def test_11_lead_moved_into_trigger_stage_enrolls(self):
        lead = self.Lead.create({'name': 'Lead Moved In', 'stage_id': self.stage_qualified.id})
        self.assertFalse(self.Participant.search_count([
            ('lead_id', '=', lead.id), ('journey_id', '=', self.journey.id)]))

        lead.write({'stage_id': self.stage_new.id})

        participant = self.Participant.search([
            ('lead_id', '=', lead.id), ('journey_id', '=', self.journey.id)])
        self.assertTrue(bool(participant))
        self.assertEqual(participant.current_node_id, self.node_1_zns)

    def test_12_condition_node_branches(self):
        node_cond = self.Node.create({
            'journey_id': self.journey.id, 'name': 'Cond has_phone', 'sequence': 40,
            'node_type': 'condition', 'condition_type': 'has_phone',
        })
        node_yes = self.Node.create({
            'journey_id': self.journey.id, 'name': 'Has phone', 'sequence': 50,
            'node_type': 'action', 'action_type': 'zns', 'message_template': 'co sdt',
        })
        node_no = self.Node.create({
            'journey_id': self.journey.id, 'name': 'No phone', 'sequence': 60,
            'node_type': 'action', 'action_type': 'email', 'message_template': 'khong co sdt',
        })
        node_cond.write({
            'next_node_if_true_id': node_yes.id, 'next_node_if_false_id': node_no.id,
        })

        with_phone = self.Lead.create({
            'name': 'Lead With Phone', 'stage_id': self.stage_new.id, 'phone': '0900000000'})
        p1 = self.Participant.search([('lead_id', '=', with_phone.id)], limit=1)
        p1.current_node_id = node_cond
        p1.process_next_step(ignore_quiet_hours=True)
        self.assertEqual(p1.current_node_id, node_yes)

        without_phone = self.Lead.create({
            'name': 'Lead No Phone', 'stage_id': self.stage_new.id})
        p2 = self.Participant.search([('lead_id', '=', without_phone.id)], limit=1)
        p2.current_node_id = node_cond
        p2.process_next_step(ignore_quiet_hours=True)
        self.assertEqual(p2.current_node_id, node_no)

    def test_13_lost_lead_stops_receiving_messages(self):
        lead = self.Lead.create({
            'name': 'Lead bi mat', 'stage_id': self.stage_new.id, 'phone': '0900000000',
        })
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        lead.action_set_lost()
        self.assertFalse(lead.active)
        self.assertEqual(lead.stage_id, self.stage_new, "CRM khong doi stage khi danh dau mat")

        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=10)
        self.Participant._cron_process_participants()

        self.assertEqual(participant.state, 'exited')
        self.assertIn('lost', (participant.exit_reason or '').lower())
        self.assertFalse(self.Log.search_count([
            ('participant_id', '=', participant.id), ('status', '=', 'success')]))

    def test_14_node_cannot_point_into_another_journey(self):
        other = self.Journey.create({
            'name': 'Kich ban khac', 'trigger_stage_id': self.stage_qualified.id,
        })
        other_node = self.Node.create({
            'journey_id': other.id, 'name': 'Node la', 'sequence': 10,
            'node_type': 'action', 'action_type': 'zns',
        })
        with self.assertRaises(ValidationError):
            self.node_3_email.write({'next_node_id': other_node.id})
            self.env.flush_all()

    def test_15_node_loop_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.node_3_email.write({'next_node_id': self.node_1_zns.id})
            self.env.flush_all()

    def test_16_node_cannot_point_to_itself(self):
        with self.assertRaises(ValidationError):
            self.node_3_email.write({'next_node_id': self.node_3_email.id})
            self.env.flush_all()

    def test_17_re_enroll_is_off_by_default(self):
        lead = self.Lead.create({'name': 'Lead quay lai', 'stage_id': self.stage_new.id})
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        lead.write({'stage_id': self.stage_qualified.id})
        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=10)
        self.Participant._cron_process_participants()
        self.assertEqual(participant.state, 'exited')

        lead.write({'stage_id': self.stage_new.id})
        self.assertEqual(participant.state, 'exited', "mac dinh khong cham soc lai")
        self.assertEqual(participant.run_count, 1)

    def test_18_re_enroll_starts_a_new_run_and_sends_again(self):
        self.journey.write({'allow_re_enroll': True})
        lead = self.Lead.create({
            'name': 'Lead cham soc lai', 'stage_id': self.stage_new.id, 'phone': '0911111111',
        })
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        self._run_cron_at(participant, '2026-08-10 10:00')
        self.assertEqual(self.Log.search_count([
            ('participant_id', '=', participant.id), ('status', '=', 'success')]), 1)

        lead.write({'stage_id': self.stage_qualified.id})
        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=10)
        self.Participant._cron_process_participants()
        self.assertEqual(participant.state, 'exited')

        lead.write({'stage_id': self.stage_new.id})
        self.assertEqual(participant.state, 'running')
        self.assertEqual(participant.run_count, 2)
        self.assertEqual(participant.current_node_id, self.node_1_zns)

        self._run_cron_at(participant, '2026-08-11 10:00')
        self.assertEqual(self.Log.search_count([
            ('participant_id', '=', participant.id), ('status', '=', 'success')]), 2,
            "luot thu hai phai gui lai tin cua node dau")

    def test_19_step_delay_comes_from_journey_not_from_cron(self):
        cron = self.env.ref('im_marketing_journey.ir_cron_process_marketing_journey')
        cron.write({'interval_number': 6, 'interval_type': 'hours'})
        self.journey.write({'step_delay_minutes': 15})

        lead = self.Lead.create({'name': 'Lead nhip buoc', 'stage_id': self.stage_new.id})
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        before = fields.Datetime.now()
        participant.process_next_step(ignore_quiet_hours=True)
        gap_minutes = (participant.next_execution_time - before).total_seconds() / 60.0
        self.assertGreater(gap_minutes, 14)
        self.assertLess(gap_minutes, 16)

    def test_20_quiet_hours_use_journey_timezone(self):
        self.env.user.tz = 'America/New_York'
        self.journey.write({'quiet_hours_tz': 'Asia/Ho_Chi_Minh'})

        lead = self.Lead.create({'name': 'Lead 23h', 'stage_id': self.stage_new.id})
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        self._run_cron_at(participant, '2026-08-10 23:00')

        self.assertFalse(self.Log.search_count([
            ('participant_id', '=', participant.id), ('status', '=', 'success')]))
        self.assertEqual(self.Log.search_count([
            ('participant_id', '=', participant.id), ('status', '=', 'postponed')]), 1)

    @mute_logger('odoo.sql_db')
    def test_21_journey_requires_a_trigger_stage(self):
        with self.assertRaises(Exception):
            self.Journey.create({'name': 'Khong co trigger stage'})
            self.env.flush_all()

    def test_22_step_delay_must_stay_positive(self):
        with self.assertRaises(ValidationError):
            self.journey.write({'step_delay_minutes': 0})
            self.env.flush_all()

    def test_05_quiet_hours_postponement(self):
        lead = self.Lead.create({
            'name': 'Lead Customer Late Night',
            'stage_id': self.stage_new.id,
        })
        participant = self.Participant.search([('lead_id', '=', lead.id)], limit=1)

        participant.next_execution_time = fields.Datetime.now() - timedelta(minutes=1)
        participant.process_next_step(ignore_quiet_hours=False)

        import pytz
        tz_name = self.env.user.tz or 'Asia/Ho_Chi_Minh'
        local_dt = pytz.utc.localize(fields.Datetime.now()).astimezone(pytz.timezone(tz_name))
        if local_dt.hour >= 22 or local_dt.hour < 7:
            self.assertTrue(participant.next_execution_time > fields.Datetime.now())
            self.assertEqual(participant.current_node_id, self.node_1_zns)
