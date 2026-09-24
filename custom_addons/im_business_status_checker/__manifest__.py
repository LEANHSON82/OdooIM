{
    'name': 'InMotion - Business Status Checker',
    'version': '19.0.2.12.0',
    'category': 'Sales/CRM',
    'summary': 'Tra tình trạng hoạt động doanh nghiệp theo mã số thuế',
    'description': """
Tra tình trạng hoạt động doanh nghiệp trên cổng đăng ký doanh nghiệp.
Cần khóa captcha của 2captcha, Capsolver hoặc Anti-Captcha.
Chạy nền, danh sách tự cập nhật.
""",
    'author': 'InMotion',
    'website': 'https://inmotion.vn',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'external_dependencies': {'python': ['requests', 'lxml']},
    'assets': {
        'web.assets_backend': [
            'im_business_status_checker/static/src/**/*.js',
            'im_business_status_checker/static/src/**/*.xml',
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/business_status_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': True,
}
