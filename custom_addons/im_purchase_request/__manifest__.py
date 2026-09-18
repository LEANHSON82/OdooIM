{
    'name': 'IM Purchase Request',
    'version': '19.0.2.11.0',
    'category': 'Inventory/Purchase',
    'sequence': 115,
    'summary': 'Đề nghị mua hàng nội bộ, duyệt nhiều cấp theo hạn mức',
    'description': """
Phiếu đề nghị mua hàng nội bộ, đứng trước đơn mua của Odoo.

Luồng: Nháp -> Chờ duyệt -> Đã duyệt -> Đã tạo đơn mua. Trạng thái chỉ đổi
được bằng nút, không ghi thẳng qua RPC được.

Nội dung chính:

- Duyệt nhiều cấp theo hạn mức; cấp duyệt là dữ liệu cấu hình từng công ty
  (nhóm ký + dải tiền + phạm vi toàn công ty hoặc theo phòng)
- So sánh báo giá nhiều nhà cung cấp; bắt buộc nêu lý do nếu không chọn nơi
  rẻ nhất; số NCC tối thiểu cố định hoặc theo giá trị dòng hàng
- Tạo đơn mua gộp theo nhà cung cấp
- Kiểm soát chi vượt dự toán: chặn ở bước xác nhận đơn mua và bước vào sổ
  hoá đơn, mặc định cho vượt 10%, muốn qua phải có người duyệt và nêu lý do
- Một màn hình thiết lập cho mỗi công ty; tab cấu hình cá nhân trên người dùng

Chi tiết: README.md trong module.
""",
    'author': 'IM',
    'license': 'LGPL-3',
    'depends': ['purchase', 'account', 'hr'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_config_parameter_data.xml',
        'data/approval_level_data.xml',
        'data/config_data.xml',
        'wizard/refuse_wizard_views.xml',
        'wizard/overrun_wizard_views.xml',
        'views/purchase_request_views.xml',
        'views/approval_level_views.xml',
        'views/purchase_request_permission_views.xml',
        'views/purchase_request_config_views.xml',
        'views/purchase_order_views.xml',
        'views/account_move_views.xml',
        'views/menus.xml',
        'report/report_request.xml',
    ],
    'installable': True,
    'application': True,
}
