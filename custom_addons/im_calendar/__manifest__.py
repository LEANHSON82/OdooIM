{
    'name': 'InMotion - Calendar Google Meet',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Calendar',
    'summary': 'Google Meet là lựa chọn mặc định cho sự kiện lịch',
    'description': """
Sự kiện lịch tạo link Google Meet thay cho phòng họp Discuss.

Chỉ chạy với người dùng đã nối Google Calendar; chưa nối thì dùng Discuss
như Odoo gốc. Link Meet lấy bằng cách tạo một sự kiện tạm trên Google rồi
xoá đi, vì Google không có API cấp riêng link Meet.
Chi tiết: README.md trong module.
""",
    'author': 'InMotion',
    'license': 'LGPL-3',
    'depends': ['calendar', 'google_calendar'],
    'data': [
        'views/calendar_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'im_calendar/static/src/**/*.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
