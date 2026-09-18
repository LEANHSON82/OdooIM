"""Model package loader for IM Helpdesk.

Import order puts the foundation objects first, then the ticket and business logic, and
finally the inherited Odoo models that add helpdesk fields or hooks.
"""

from . import helpdesk_team
from . import helpdesk_stage
from . import helpdesk_sla_status
from . import helpdesk_sla
from . import helpdesk_ticket
from . import helpdesk_tag
from . import helpdesk_tag_assignment
from . import res_users
from . import res_partner
from . import res_company
