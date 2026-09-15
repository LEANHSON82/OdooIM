from odoo.tests import common


def create_internal_user(env, login, groups=(), **vals):
    """An employee-side user; *groups* are xml ids added to base.group_user.

    Login doubles as password so tests can ``authenticate(login, login)``.
    """
    group_ids = [env.ref('base.group_user').id] + [env.ref(xmlid).id for xmlid in groups]
    return env['res.users'].create({
        'name': login,
        'login': login,
        'password': login,
        'email': '%s@example.com' % login,
        'group_ids': [(6, 0, group_ids)],
        **vals,
    })


def create_portal_user(env, login, **vals):
    """A learner from outside the company, as an invited contractor would be."""
    return env['res.users'].create({
        'name': login,
        'login': login,
        'password': login,
        'email': '%s@example.com' % login,
        'group_ids': [(6, 0, [env.ref('base.group_portal').id])],
        **vals,
    })


def create_exam(env, channel, **survey_vals):
    """A published certification slide backed by a scored survey.

    The default pass mark is 0, so an empty attempt passes; raise
    ``scoring_success_min`` to make it fail.
    """
    survey = env['survey.survey'].create({
        'title': 'Final exam',
        'scoring_type': 'scoring_with_answers',
        'scoring_success_min': 0.0,
        'certification': True,
        **survey_vals,
    })
    return env['slide.slide'].create({
        'name': survey.title,
        'channel_id': channel.id,
        'slide_category': 'certification',
        'survey_id': survey.id,
        'is_published': True,
    })


def submit_exam(env, exam, partner, as_user=None, test_entry=False):
    """Enrol *partner*, hand in an empty attempt at *exam* and return it.

    An empty attempt scores 0, so the survey's pass mark decides the outcome.
    With *as_user* the submission runs as that user with sudo, the way CE's
    website controller does it for a logged-in learner.
    """
    channel = exam.channel_id
    channel._action_add_members(partner)
    progress = env['slide.slide.partner'].search([
        ('slide_id', '=', exam.id), ('partner_id', '=', partner.id)])
    if not progress:
        progress = env['slide.slide.partner'].create({
            'slide_id': exam.id, 'channel_id': channel.id, 'partner_id': partner.id})
    attempt = exam.survey_id.sudo()._create_answer(
        partner=partner, check_attempts=False, test_entry=test_entry,
        slide_id=exam.id, slide_partner_id=progress.id)
    if as_user:
        attempt = attempt.with_user(as_user).sudo()
    attempt._mark_done()
    env.flush_all()
    return attempt


def complete_slides(env, slides, partner):
    """Record *slides* as finished for *partner*, the way CE stores progress."""
    for slide in slides:
        progress = env['slide.slide.partner'].search([
            ('slide_id', '=', slide.id), ('partner_id', '=', partner.id)])
        if progress:
            progress.completed = True
        else:
            env['slide.slide.partner'].create({
                'slide_id': slide.id,
                'channel_id': slide.channel_id.id,
                'partner_id': partner.id,
                'completed': True,
            })
    env.flush_all()


class ImElearningCommon(common.TransactionCase):
    """Shared fixture: a course, a learner and the HR chain behind them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.partner_student = cls.env['res.partner'].create({
            'name': 'Nguyen Van A',
            'email': 'a@example.com',
        })
        cls.partner_other = cls.env['res.partner'].create({
            'name': 'Tran Thi B',
            'email': 'b@example.com',
        })

        cls.department = cls.env['hr.department'].create({'name': 'Accounting'})
        cls.manager_employee = cls.env['hr.employee'].create({
            'name': 'Manager C',
            'work_email': 'c@example.com',
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Nguyen Van A',
            'department_id': cls.department.id,
            'parent_id': cls.manager_employee.id,
            'work_contact_id': cls.partner_student.id,
        })

        cls.channel = cls.env['slide.channel'].create({
            'name': 'Information Security',
            'certificate_enabled': True,
        })
        cls.slide_article = cls.env['slide.slide'].create({
            'name': 'Lesson 1 - Introduction',
            'channel_id': cls.channel.id,
            'slide_category': 'article',
            'is_published': True,
            'html_content': '<p>Content</p>',
        })
