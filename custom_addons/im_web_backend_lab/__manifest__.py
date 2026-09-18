{
    'name': 'Lab - Web Backend',
    'version': '19.0.0.5.0',
    'category': 'Hidden',
    'summary': 'Thương hiệu, menu chính, thanh điều hướng và chế độ tối',
    'description': """
Tuỳ biến giao diện backend: màu thương hiệu, Home Menu dạng lưới app,
thanh điều hướng riêng và chế độ tối.

Module giao diện thuần, không có model nghiệp vụ. Lưu ý: manifest thay
entry point web/static/src/main.js để khởi động ImWebClient — kiểm tra chỗ
này đầu tiên nếu backend trắng trang sau khi nâng cấp Odoo.
Chế độ tối chọn theo thứ tự cookie > thiết lập người dùng > hệ điều hành;
đổi theme luôn phải reload vì bundle CSS do server chọn.
Chi tiết: README.md trong module.
""",
    'author': 'InMotion',
    'license': 'LGPL-3',
    'depends': ['web', 'base_setup'],
    'data': [
        'views/webclient_templates.xml',
        'views/res_users_views.xml',
    ],
    'assets': {
        # Brand colors
        'web._assets_primary_variables': [
            ('prepend',
             'im_web_backend_lab/static/src/scss/primary_variables.scss'),
        ],
        # Replace entry point
        'web.assets_web': [
            ('replace', 'web/static/src/main.js',
             'im_web_backend_lab/static/src/main.js'),
        ],
        # Backend
        'web.assets_backend': [
            # Home menu
            'im_web_backend_lab/static/src/webclient/home_menu/home_menu_service.js',
            'im_web_backend_lab/static/src/webclient/home_menu/home_menu.js',
            'im_web_backend_lab/static/src/webclient/home_menu/home_menu.xml',
            'im_web_backend_lab/static/src/webclient/home_menu/home_menu.scss',
            # Web client
            'im_web_backend_lab/static/src/webclient/im_webclient.js',
            'im_web_backend_lab/static/src/webclient/im_webclient.xml',
            'im_web_backend_lab/static/src/webclient/im_webclient.scss',
            # Navbar
            'im_web_backend_lab/static/src/webclient/navbar/navbar.js',
            'im_web_backend_lab/static/src/webclient/navbar/navbar.xml',
            'im_web_backend_lab/static/src/webclient/navbar/navbar.scss',
            # Color scheme
            'im_web_backend_lab/static/src/core/color_scheme/color_scheme_service.js',
            'im_web_backend_lab/static/src/core/color_scheme/user_menu_items.js',
            # Theme
            'im_web_backend_lab/static/src/scss/home_menu_theme.scss',
        ],
        # Dark mode variables
        'web.assets_web_dark': [
            ('before', 'web/static/src/scss/primary_variables.scss',
             'im_web_backend_lab/static/src/scss/primary_variables.dark.scss'),
            ('before', 'web/static/src/scss/secondary_variables.scss',
             'im_web_backend_lab/static/src/scss/secondary_variables.dark.scss'),
            ('after', 'web/static/lib/bootstrap/scss/_functions.scss',
             'im_web_backend_lab/static/src/scss/bs_functions_overridden.dark.scss'),
            'im_web_backend_lab/static/src/scss/bootstrap_overridden.dark.scss',
            'im_web_backend_lab/static/src/scss/dark_mode.scss',
        ],
        # Login page
        'web.assets_frontend': [
            'im_web_backend_lab/static/src/scss/login.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
}
