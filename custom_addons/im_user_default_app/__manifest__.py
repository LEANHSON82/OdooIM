{
    'name': 'IM User Default App',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Ứng dụng mặc định cho từng người dùng sau đăng nhập',
    'description': """
Chọn app (và menu con) mở sẵn sau khi đăng nhập, cho từng người dùng.

Đặt tại tab Preferences trên form người dùng và form Sở thích của chính mình;
người dùng thường tự đặt được. Có nút bỏ chọn để quay về hành vi gốc.
Bên dưới chỉ là cách chọn dễ hiểu cho trường action_id sẵn có của Odoo.
Chi tiết: README.md trong module.
""",
    'author': 'IM',
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [
        'views/res_users_views.xml',
    ],
    'installable': True,
}
