# im_user_default_app

## Mô tả module

Cho phép chọn app mở sẵn sau khi đăng nhập, cho từng người dùng. Odoo 19 CE có
sẵn trường `res.users.action_id` ("Home Action") nhưng chỉ admin ở chế độ nhà
phát triển mới thấy, và phải chọn một `ir.actions.*` chứ không chọn theo app.

## Tính năng

- Chọn app mặc định (`default_app_id`) và tuỳ chọn menu con (`default_menu_id`)
  ngay trong tab Preferences.
- Nút "Bỏ app mặc định" để quay về hành vi gốc của Odoo.
- Người dùng thường tự đặt được cho chính mình, không cần admin.
- Đồng bộ tự động sang `action_id` chuẩn của Odoo, kể cả khi ghi qua RPC.

## Phân quyền và cấu hình kỹ thuật

Không có cron, không có tham số hệ thống, không có nhóm quyền mới.

Hai trường được thêm vào `SELF_READABLE_FIELDS` và `SELF_WRITEABLE_FIELDS`; thiếu
phần này thì người dùng thường mở form Sở thích sẽ bị AccessError.

## Workflow

1. Vào form người dùng (hoặc Sở thích của chính mình) tab Preferences.
2. Chọn App mặc định, nếu cần thì chọn thêm menu con trong app đó.
3. Lưu. Lần đăng nhập sau sẽ mở thẳng vào đó.
4. Muốn bỏ thì bấm "Bỏ app mặc định".

Bên dưới, `_sync_default_app_to_action` dò xuống cây menu tìm menu đầu tiên có
action rồi ghi vào `action_id`; phần còn lại do Odoo lo.

## Thành quả

- Người dùng thường tự đặt và tự bỏ app mặc định được, không phải nhờ admin và
  không cần bật chế độ nhà phát triển.
- Nút "Bỏ app mặc định" không phải để cho đẹp: ô many2one muốn xoá phải bôi đen
  chữ rồi xoá, gần như không ai đoán ra, nên trước đó người dùng coi như mắc kẹt
  với app đã chọn.
