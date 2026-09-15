from odoo import Command
from odoo.tests.common import TransactionCase


class TestHelpdeskAutoClassification(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Ticket = cls.env['helpdesk.ticket'].with_context(
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            tracking_disable=True,
        )
        cls.Tag = cls.env['helpdesk.tag']
        cls.Assignment = cls.env['helpdesk.tag.assignment']

        helpdesk_group = cls.env.ref('im_helpdesk.group_helpdesk_user')
        employee_group = cls.env.ref('base.group_user')
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def create_user(login):
            return Users.create({
                'name': f'Auto Classify {login}',
                'login': f'auto_classify_{login}',
                'email': f'auto_classify_{login}@example.com',
                'group_ids': [Command.set([employee_group.id, helpdesk_group.id])],
            })

        cls.login_primary = create_user('login_primary')
        cls.login_backup = create_user('login_backup')
        cls.billing_primary = create_user('billing_primary')
        cls.billing_backup = create_user('billing_backup')

        cls.stage_new = cls.env['helpdesk.stage'].create({
            'name': 'Auto Classify New',
            'sequence': 0,
        })

        Team = cls.env['helpdesk.team'].with_context(mail_create_nolog=True, mail_create_nosubscribe=True)
        cls.team_general = Team.create({
            'name': 'Auto Classify General',
            'use_alias': False,
            'use_sla': False,
            'auto_assignment': False,
            'member_ids': [Command.set([cls.login_primary.id])],
            'stage_ids': [Command.set([cls.stage_new.id])],
        })
        cls.team_login = Team.create({
            'name': 'Auto Classify Login',
            'use_alias': False,
            'use_sla': False,
            'auto_assignment': True,
            'assign_method': 'tags',
            'member_ids': [Command.set([cls.login_primary.id, cls.login_backup.id])],
            'stage_ids': [Command.set([cls.stage_new.id])],
        })
        cls.team_billing = Team.create({
            'name': 'Auto Classify Billing',
            'use_alias': False,
            'use_sla': False,
            'auto_assignment': True,
            'assign_method': 'tags',
            'member_ids': [Command.set([cls.billing_primary.id, cls.billing_backup.id])],
            'stage_ids': [Command.set([cls.stage_new.id])],
        })

    def _create_tag(self, name, keywords=False, min_score=1):
        return self.Tag.create({
            'name': name,
            'auto_apply_keywords': keywords,
            'auto_apply_min_score': min_score,
        })

    def _create_assignment(self, team, tag, users, weight=1):
        return self.Assignment.create({
            'team_id': team.id,
            'tag_id': tag.id,
            'user_ids': [Command.set(users.ids)],
            'route_weight': weight,
        })

    def test_auto_tag_weighted_vietnamese_and_no_substring(self):
        login_tag = self._create_tag(
            'Auto Test Login',
            keywords='lỗi đăng nhập::2',
            min_score=2,
        )
        art_tag = self._create_tag(
            'Auto Test Art',
            keywords='art',
            min_score=1,
        )

        ticket = self.Ticket.create({
            'name': 'Loi dang nhap vao he thong',
            'description': '<p>Khach hang bao loi dang nhap</p>',
            'team_id': self.team_general.id,
        })
        self.assertIn(login_tag, ticket.tag_ids)
        self.assertNotIn(art_tag, ticket.tag_ids)

        substring_ticket = self.Ticket.create({
            'name': 'cart checkout problem',
            'team_id': self.team_general.id,
        })
        self.assertNotIn(art_tag, substring_ticket.tag_ids)

    def test_weighted_routing_and_current_team_tie(self):
        payment_tag = self._create_tag(
            'Auto Test Payment',
            keywords='không thanh toán::2',
            min_score=2,
        )
        self._create_assignment(self.team_login, payment_tag, self.login_primary, weight=1)
        self._create_assignment(self.team_billing, payment_tag, self.billing_primary, weight=4)

        ticket = self.Ticket.create({
            'name': 'Khong thanh toan duoc don hang',
            'team_id': self.team_login.id,
        })
        self.assertEqual(ticket.team_id, self.team_billing)

        tie_tag = self._create_tag(
            'Auto Test Tie',
            keywords='bao hanh',
            min_score=1,
        )
        self._create_assignment(self.team_login, tie_tag, self.login_primary, weight=2)
        self._create_assignment(self.team_billing, tie_tag, self.billing_primary, weight=2)

        tied_ticket = self.Ticket.create({
            'name': 'Can bao hanh san pham',
            'team_id': self.team_login.id,
        })
        self.assertEqual(tied_ticket.team_id, self.team_login)

    def test_tag_assignment_prefers_expertise_then_workload_and_fallback(self):
        login_tag = self._create_tag(
            'Auto Test Expert Login',
            keywords='login loi::2',
            min_score=2,
        )
        shared_tag = self._create_tag('Auto Test Shared')
        self._create_assignment(self.team_login, login_tag, self.login_primary, weight=5)
        self._create_assignment(
            self.team_login,
            shared_tag,
            self.login_primary | self.login_backup,
            weight=1,
        )

        expert_ticket = self.Ticket.create({
            'name': 'Login loi tren ung dung',
            'team_id': self.team_general.id,
        })
        self.assertEqual(expert_ticket.team_id, self.team_login)
        self.assertEqual(expert_ticket.user_id, self.login_primary)

        self.Ticket.create({
            'name': 'Existing assigned ticket',
            'team_id': self.team_login.id,
            'user_id': self.login_primary.id,
        })
        balanced_expert_ticket = self.Ticket.create({
            'name': 'Shared tagged ticket',
            'team_id': self.team_login.id,
            'tag_ids': [Command.set([shared_tag.id])],
        })
        self.assertEqual(balanced_expert_ticket.user_id, self.login_backup)

        fallback_ticket = self.Ticket.create({
            'name': 'No configured tag on this ticket',
            'team_id': self.team_login.id,
        })
        self.assertIn(fallback_ticket.user_id, self.team_login.member_ids)

    def test_email_body_can_classify_after_ticket_creation(self):
        email_tag = self._create_tag(
            'Auto Test Email Payment',
            keywords='lỗi thanh toán::2',
            min_score=2,
        )
        self._create_assignment(self.team_billing, email_tag, self.billing_primary, weight=3)

        ticket = self.Ticket.create({
            'name': 'Can ho tro',
            'team_id': self.team_login.id,
            'partner_email': 'auto-classify-customer@example.com',
        })
        ticket.message_post(
            body='<p>Toi gap lỗi thanh toán tren cong thanh toan.</p>',
            message_type='email',
            subtype_xmlid='im_helpdesk.mt_ticket_new',
            email_from='auto-classify-customer@example.com',
        )

        self.assertIn(email_tag, ticket.tag_ids)
        self.assertEqual(ticket.team_id, self.team_billing)
        self.assertEqual(ticket.user_id, self.billing_primary)
