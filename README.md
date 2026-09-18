# Sodoo

Bộ module tuỳ chỉnh cho **Odoo 19 Community**, kèm cấu hình deploy bằng Docker
lên Railway.

Repo không chứa Odoo core. Image `odoo:19` chính thức đã có sẵn core; thư mục
`custom_addons/` được copy vào `/mnt/extra-addons` lúc build, nên repo luôn nhẹ
và nâng cấp Odoo không phải merge gì.

## Module

Mỗi module có `README.md` riêng mô tả tính năng, cấu hình kỹ thuật và luồng xử
lý. Bản đồ theo nghiệp vụ và cây phụ thuộc nằm ở
[custom_addons/README.md](custom_addons/README.md).

| Module | Vai trò |
|---|---|
| [im_elearning](custom_addons/im_elearning/) | Đào tạo nội bộ: video tự host, chặn thi sớm, chứng chỉ tra cứu, giao khoá học |
| [im_theme](custom_addons/im_theme/) | Mẫu thư, chứng chỉ PDF và trang thi cho im_elearning |
| [im_event_training](custom_addons/im_event_training/) | Lớp đào tạo nhiều buổi: điểm danh, chứng chỉ theo chuyên cần, vé early-bird |
| [im_purchase_request](custom_addons/im_purchase_request/) | Đề nghị mua hàng, duyệt nhiều cấp theo hạn mức, kiểm soát chi vượt dự toán |
| [im_helpdesk](custom_addons/im_helpdesk/) | Ticket hỗ trợ: SLA, portal khách hàng, tự phân loại theo keyword |
| [im_marketing_journey](custom_addons/im_marketing_journey/) | Kịch bản nuôi dưỡng lead nhiều bước trên CRM |
| [im_web_backend_lab](custom_addons/im_web_backend_lab/) | Giao diện backend: lưới app, thanh điều hướng, chế độ tối |
| [im_user_default_app](custom_addons/im_user_default_app/) | App mở sẵn sau khi đăng nhập, đặt cho từng người dùng |
| [im_brevo_mail](custom_addons/im_brevo_mail/) | Gửi email qua Brevo HTTP API thay SMTP |
| [im_calendar](custom_addons/im_calendar/) | Sự kiện lịch tạo link Google Meet |
| [im_website_branding](custom_addons/im_website_branding/) | Gỡ khối quảng bá Odoo ở chân trang website |

## Cấu trúc repo

```
Sodoo/
├── custom_addons/      11 module, mỗi module một README
├── Dockerfile          nền odoo:19, copy custom_addons vào /mnt/extra-addons
├── entrypoint.sh       khởi tạo database, nâng cấp module, đổi tài khoản admin
├── odoo.conf           cấu hình production
├── railway.json        healthcheck và chính sách restart
└── RAILWAY.md          hướng dẫn deploy từng bước
```

## Phát triển tại máy

Cần một bản Odoo 19 Community và một PostgreSQL chạy sẵn. Repo này được symlink
vào cây Odoo core để `addons_path` thấy được module:

```
odoo19/custom_addons  -> Sodoo/custom_addons
odoo19/railway-deploy -> Sodoo
```

Cài một module vào database mới:

```bash
odoo-bin -c odoo.conf -d <db> -i im_purchase_request --stop-after-init
```

Nâng cấp sau khi sửa code. Bắt buộc phải làm khi sửa file XML, vì Odoo chỉ nạp
lại view, menu, dữ liệu và phân quyền khi module được nâng cấp:

```bash
odoo-bin -c odoo.conf -d <db> -u im_purchase_request --stop-after-init
```

## Deploy

Push lên remote `odooim` là Railway build lại. Mỗi lần container khởi động,
`entrypoint.sh` chạy bốn bước:

1. Chờ Postgres sẵn sàng, tạo role Odoo nếu chưa có.
2. Khởi tạo database khi module `base` chưa từng cài xong. Chỉ trường hợp này
   mới xoá schema; database đã có dữ liệu thì không bao giờ bị xoá.
3. Nâng cấp mọi module trong `custom_addons` đang ở trạng thái installed.
4. Đổi login admin theo `ODOO_ADMIN_LOGIN` và `ODOO_ADMIN_PASSWORD` nếu có.

Đặt `SKIP_UPGRADE=1` để bỏ bước 3 khi cần deploy nhanh.

Hướng dẫn tạo project, gắn Postgres, gắn volume và trỏ tên miền: xem
[RAILWAY.md](RAILWAY.md).

## Biến môi trường

| Biến | Bắt buộc | Việc |
|---|---|---|
| `ODOO_ADMIN_LOGIN`, `ODOO_ADMIN_PASSWORD` | không | Đổi tài khoản admin trong lần khởi động đầu |
| `BREVO_API_KEY` | có, nếu cần gửi mail | Railway chặn cổng SMTP nên mail phải đi qua HTTP API |
| `BREVO_SENDER_EMAIL` | đi kèm khoá trên | Địa chỉ người gửi đã xác thực bên Brevo |
| `SKIP_UPGRADE` | không | Đặt `1` để bỏ bước nâng cấp module lúc khởi động |

## Lưu ý khi vận hành

- Bước 3 nâng cấp mọi module ở mỗi lần deploy. Vì vậy đừng sửa tên nhóm quyền
  hay bản ghi dữ liệu trực tiếp trên giao diện nếu chúng không nằm trong
  `<data noupdate="1">` — lần deploy sau sẽ ghi đè lại.
- Filestore nằm ở `/var/lib/odoo`. Trên Railway phải gắn volume vào đúng đường
  dẫn này, nếu không tệp đính kèm và video sẽ mất sau mỗi lần redeploy.
- `odoo.conf` trong repo vẫn để `admin_passwd` mẫu. Đổi thành mật khẩu thật
  trước khi bật `list_db`.
- Một số module cần cron hoặc tham số hệ thống mới chạy đủ. Bảng tổng hợp nằm ở
  [custom_addons/README.md](custom_addons/README.md#cron-và-tham-số-hệ-thống).

## Giấy phép

Các module trong repo khai `LGPL-3` trong `__manifest__.py`.
