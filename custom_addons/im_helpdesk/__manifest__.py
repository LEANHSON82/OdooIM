{
    'name': 'IM Helpdesk',
    'version': '1.0',
    'category': 'Services/Helpdesk',
    'sequence': 110,
    'summary': 'Quản lý ticket hỗ trợ khách hàng',
    'description': """
Helpdesk cho Odoo 19 Community (bản CE không có sẵn module này).

Nội dung chính:

- Team, ticket, stage dùng chung nhiều team; stage fold nghĩa là đã đóng
- Ticket vào từ ba đường: backend, email qua alias của team, portal khách hàng
- Tự phân loại: gắn tag theo keyword có trọng số, chuyển ticket về team phù
  hợp, rồi chọn người xử lý theo rule tag và lịch làm việc
- SLA theo giờ làm việc; stage bị loại trừ làm dừng đồng hồ SLA
- Tự đóng ticket không hoạt động (cron, mặc định tắt), đánh giá của khách
- Hai báo cáo SQL: phân tích ticket và phân tích trạng thái SLA

Cài xong tự tạo team Customer Care kèm 5 stage chuẩn cho mỗi công ty.
Chi tiết: README.md trong module.
""",
    'author': 'IM',
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail', 'utm', 'rating', 'resource', 'portal'],
    'data': [
        'security/helpdesk_security.xml',
        'security/ir.model.access.csv',
        'data/mail_message_subtype_data.xml',
        'data/mail_template_data.xml',
        'data/helpdesk_data.xml',
        'data/ir_cron_data.xml',
        'data/ir_sequence_data.xml',
        'views/helpdesk_ticket_views.xml',
        'report/helpdesk_ticket_analysis_views.xml',
        'report/helpdesk_sla_report_analysis_views.xml',
        'views/helpdesk_tag_views.xml',
        'views/helpdesk_tag_assignment_views.xml',
        'views/helpdesk_stage_views.xml',
        'views/helpdesk_sla_views.xml',
        'views/helpdesk_team_views.xml',
        'views/helpdesk_portal_templates.xml',
        'views/rating_rating_views.xml',
        'views/res_partner_views.xml',
        'views/mail_activity_views.xml',
        'views/helpdesk_templates.xml',
        'views/helpdesk_menus.xml',
        'wizard/helpdesk_stage_delete_views.xml',
    ],
    'post_init_hook': '_create_helpdesk_team',
    'installable': True,
    'application': True,
}
