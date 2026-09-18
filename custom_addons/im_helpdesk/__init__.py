"""IM Helpdesk module entry point.

This file loads the python packages into Odoo and declares the post-init hook that
creates a default helpdesk team for every company after installation.
"""

from . import controllers
from . import models
from . import report
from . import wizard


def _create_helpdesk_team(env):
    """Create the default 'Customer Care' team for companies that have none.

    Odoo calls this hook once, right after the module is installed. The demo and
    default team already belong to one company, so this helper only covers the
    remaining ones and reuses the company helper to keep the defaults identical.
    """
    team_1 = env.ref('im_helpdesk.helpdesk_team1', raise_if_not_found=False)
    if team_1:
        env['res.company'].search([('id', '!=', team_1.company_id.id)])._create_helpdesk_team()
