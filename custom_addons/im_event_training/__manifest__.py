{
    'name': 'InMotion - Event Training & Attendance',
    'version': '19.0.1.0.0',
    'category': 'Marketing/Events',
    'summary': 'Sự kiện nhiều buổi, điểm danh, chứng chỉ, vé sớm',
    'description': """
Mở rộng module Sự kiện thành lớp đào tạo nhiều buổi.

- event.session: chia sự kiện thành các buổi học
- event.session.attendance: điểm danh từng buổi, có trạng thái "được miễn"
  (buổi được miễn trừ vào mẫu số khi tính tỉ lệ chuyên cần)
- Chứng chỉ cấp theo ngưỡng chuyên cần của lớp, ghi lại tỉ lệ và ngưỡng
  tại thời điểm cấp; thu hồi không xoá dấu vết
- Vé early-bird: hai mức giá, hết ưu đãi theo hạn chót hoặc theo số lượng

Chỉ áp dụng cho sự kiện đánh dấu "Là khoá đào tạo".
Chi tiết: README.md trong module.
""",
    'author': 'InMotion',
    'website': 'https://inmotion.vn',
    'license': 'LGPL-3',
    'depends': ['event', 'event_product', 'event_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'data/event_training_demo.xml',
        'views/event_session_views.xml',
        'views/event_event_views.xml',
        'views/event_registration_views.xml',
        'views/event_ticket_views.xml',
    ],
    'installable': True,
    'application': False,
}
