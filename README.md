# Sodoo

## Mô tả

Repo chứa 11 module tuỳ chỉnh cho Odoo 19 Community và bộ file deploy lên
Railway. Không có Odoo core trong repo: image `odoo:19` đã chứa sẵn, module custom
được copy vào `/mnt/extra-addons`.

| Thư mục / file | Việc |
|---|---|
| [custom_addons/](custom_addons/) | 11 module tuỳ chỉnh — xem [bản đồ module theo nghiệp vụ](custom_addons/README.md) |
| `Dockerfile`, `odoo.conf`, `entrypoint.sh`, `railway.json` | Bộ deploy Railway — xem [RAILWAY.md](RAILWAY.md) |

## Chạy tại máy

Repo được symlink vào một bản Odoo 19 core để chạy thử:

```
odoo19/custom_addons  -> Sodoo/custom_addons
odoo19/railway-deploy -> Sodoo
```

Nâng cấp một module sau khi sửa code:

```bash
odoo-bin -c odoo.conf -d <db> -u im_purchase_request --stop-after-init
```

## Deploy

`git push` lên remote `odooim` là Railway build lại. Mỗi lần khởi động,
`entrypoint.sh` chạy bốn bước:

1. Chờ Postgres, tạo role Odoo nếu chưa có.
2. Init database khi `base` chưa từng cài xong. Chỉ trường hợp này mới xoá schema;
   database đã có dữ liệu thì không bao giờ bị xoá.
3. Chạy `-u` cho mọi module trong `custom_addons` đang ở trạng thái installed, để
   view và data XML được nạp lại. Không có bước này thì sửa view XML xong deploy
   vẫn không thấy gì.
4. Đổi login admin theo `ODOO_ADMIN_LOGIN` / `ODOO_ADMIN_PASSWORD` nếu có.

Đặt `SKIP_UPGRADE=1` để bỏ bước 3 khi cần deploy gấp.

## Biến môi trường

| Biến | Việc |
|---|---|
| `ODOO_ADMIN_LOGIN`, `ODOO_ADMIN_PASSWORD` | Đổi tài khoản admin lần đầu |
| `BREVO_API_KEY`, `BREVO_SENDER_EMAIL` | Gửi mail qua HTTP API; Railway chặn SMTP nên bắt buộc |
| `SKIP_UPGRADE` | `1` để bỏ bước nâng cấp module lúc khởi động |

Lưu ý: `odoo.conf` trong repo vẫn để `admin_passwd` mẫu. Đổi thành mật khẩu thật
trước khi mở `list_db`.

## Thành quả

- Sửa view XML xong chỉ cần push, entrypoint tự nâng cấp module nên không phải
  vào giao diện bấm gì.
- Đổi lại: bước 3 nâng cấp mọi module mỗi lần deploy, nên đừng đổi tên nhóm quyền
  hay bản ghi data trong giao diện nếu chúng không nằm trong `<data noupdate="1">`,
  lần deploy sau sẽ ghi đè lại.
- Thiếu `BREVO_API_KEY` trên Railway thì không thư nào gửi được.
