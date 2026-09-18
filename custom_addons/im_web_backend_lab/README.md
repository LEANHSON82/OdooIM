# im_web_backend_lab

## Mô tả module

Tuỳ biến giao diện backend Odoo: màu thương hiệu, màn hình Home Menu dạng lưới
app, thanh điều hướng riêng và chế độ tối. Module giao diện thuần, không có model
nghiệp vụ nào.

## Tính năng

- Thay entry point của web client để khởi động `ImWebClient` thay cho `WebClient`.
- Home Menu: lưới app toàn màn hình, có ô tìm kiếm và điều hướng bằng bàn phím
  (mũi tên, Tab, Enter, Escape).
- Chế độ tối cho toàn backend, kèm mục bật/tắt trong menu người dùng.
- Màu thương hiệu cho backend và trang đăng nhập.

## Phân quyền và cấu hình kỹ thuật

Không có cron, không có tham số hệ thống, không có nhóm quyền mới.

Ba trường kỹ thuật lưu lựa chọn của người dùng: `res.users.settings.x_color_scheme`
(system/light/dark), `x_homemenu_config` (Json, để dành) và trường related
`res.users.x_color_scheme`.

Cấu hình bundle nằm trong `__manifest__.py`: `web._assets_primary_variables` cho
màu, `web.assets_web` thay `main.js`, `web.assets_web_dark` cho biến dark mode,
`web.assets_frontend` cho trang đăng nhập.

## Workflow

Chế độ tối chọn màu theo thứ tự cookie, rồi thiết lập người dùng, rồi hệ điều
hành:

1. Người dùng bấm "Dark Mode" trong menu người dùng.
2. JS đặt cookie `color_scheme` và gọi `setUserSettings('x_color_scheme')`, rồi
   reload trang.
3. `ir.http.color_scheme()` đọc cookie (hoặc thiết lập người dùng) để chọn bundle
   CSS.
4. `ImHome.web_client` ghi lại cookie cho khớp thiết lập người dùng, phòng khi
   đăng nhập từ máy khác.
5. Đăng xuất thì `_post_logout` xoá cookie, để người kế tiếp trên cùng máy không
   thừa hưởng theme của người trước.

Cookie phải đứng đầu vì SCSS dark mode nằm trong bundle riêng, mà server phải
quyết định nạp bundle nào trước khi JS chạy.

## Thành quả

- Backend có bộ mặt riêng: lưới app, navbar, chế độ tối và màu thương hiệu.
- Việc thay entry point `web/static/src/main.js` là chỗ xâm lấn nhất. Nâng cấp
  Odoo minor mà thấy backend trắng trang thì kiểm tra `__manifest__.py` trước.
- Đổi theme bắt buộc reload trang vì bundle CSS do server chọn; không đổi nóng
  được.
- Số cột trong `_getColCount` phải khớp breakpoint trong `home_menu.scss`, không
  thì phím mũi tên nhảy sai hàng.
