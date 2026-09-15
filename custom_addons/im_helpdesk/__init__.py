"""Khởi tạo module IM Helpdesk.

File này nạp các package Python vào Odoo và khai báo post-init hook
dùng để tạo team helpdesk mặc định cho các công ty sau khi cài module.
"""

from . import controllers
from . import models
from . import report
from . import wizard


def _create_helpdesk_team(env):
    """Tạo team 'Customer Care' mặc định cho các công ty chưa có team.

    Odoo gọi hook này một lần sau khi cài module. Team demo/mặc định đã thuộc
    về một công ty, nên helper này chỉ tạo team cho các công ty còn lại và dùng
    lại helper của company để giữ cấu hình mặc định nhất quán.
    """
    team_1 = env.ref('im_helpdesk.helpdesk_team1', raise_if_not_found=False)
    if team_1:
        env['res.company'].search([('id', '!=', team_1.company_id.id)])._create_helpdesk_team()
