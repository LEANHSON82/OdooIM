{
    'name': 'IM Brevo Mail (HTTP API)',
    'version': '1.0',
    'category': 'Technical',
    'summary': 'Gửi email qua Brevo HTTP API thay cho SMTP',
    'description': """
Gửi email ra ngoài qua Brevo HTTP API thay cho SMTP.

Dùng khi máy chủ chặn cổng SMTP, ví dụ Railway (API HTTP đi cổng 443).
Bật khi có khoá: tham số hệ thống brevo.api_key hoặc biến môi trường
BREVO_API_KEY. Không có khoá thì Odoo gửi bằng SMTP như bình thường.
Tuỳ chọn: brevo.sender_email, brevo.sender_name.
Chi tiết: README.md trong module.
""",
    'author': 'IM',
    'license': 'LGPL-3',
    'depends': ['base'],
    'installable': True,
}
