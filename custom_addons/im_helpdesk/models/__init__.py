"""Bộ nạp gói model cho IM Helpdesk.

Thứ tự import đặt các object nền tảng trước, sau đó đến ticket/logic nghiệp vụ,
và cuối cùng là các model Odoo kế thừa để thêm field hoặc hook riêng cho helpdesk.
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
