{
    'name': 'InMotion - Marketing Automation Journey Engine',
    'version': '19.0.1.0.0',
    'category': 'Marketing/Automation',
    'summary': 'Hành trình nuôi dưỡng lead nhiều bước qua Zalo ZNS và email',
    'description': """
Kịch bản nuôi dưỡng lead nhiều bước: gửi tin - chờ - rẽ nhánh theo điều kiện.

Lead vào giai đoạn CRM kích hoạt thì tự ghi danh; cron 5 phút đẩy từng bước.
Có sẵn: chống gửi trùng (giãn cách bước + nhật ký), giờ im lặng 22:00-07:00
theo múi giờ của kịch bản, chặn kịch bản có vòng lặp, thoát khi lead đổi
giai đoạn hoặc bị lưu trữ, cho phép vào lại kịch bản.

CHÚ Ý: phần gửi thật CHƯA nối. _send_node_message mới chỉ ghi nhật ký, chưa
gọi API Zalo ZNS và chưa tạo mail.mail.
Chi tiết: README.md trong module.
""",
    'author': 'InMotion',
    'website': 'https://inmotion.vn',
    'license': 'LGPL-3',
    'depends': ['base', 'crm', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/journey_participant_views.xml',
        'views/journey_views.xml',
        'views/journey_log_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
}
