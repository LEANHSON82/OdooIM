{
    'name': 'InMotion - Calendar Google Meet',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Calendar',
    'summary': 'Google Meet là lựa chọn mặc định cho sự kiện lịch',
    'description': 'Tự tạo link Google Meet khi đã đồng bộ Google Calendar.',
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
