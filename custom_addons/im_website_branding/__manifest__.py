{
    'name': 'IM Website Branding',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Gỡ khối quảng bá Odoo khỏi chân trang website',
    'description': """
Gỡ khối quảng bá Odoo ("Powered by Odoo") ở chân trang website công khai.

Cách làm: kế thừa template web.brand_promotion với priority 99 và xoá khối
o_brand_promotion. Priority phải cao để chạy sau website/website_sale.
Chi tiết: README.md trong module.
""",
    'author': 'IM',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/website_templates.xml',
    ],
    'installable': True,
}
