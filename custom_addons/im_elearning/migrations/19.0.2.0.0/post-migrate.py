"""Drop the mail templates that moved to im_theme.

They were ``noupdate`` records, so removing them from the manifest leaves them
behind as orphans that still show up under Settings > Email Templates.
"""
from odoo import SUPERUSER_ID, api

MOVED_TEMPLATES = (
    'im_elearning.mail_template_assignment_reminder',
    'im_elearning.mail_template_assignment_overdue',
    'im_elearning.mail_template_certificate_issued',
    'im_elearning.mail_template_exam_failed',
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in MOVED_TEMPLATES:
        template = env.ref(xmlid, raise_if_not_found=False)
        if template:
            template.unlink()
