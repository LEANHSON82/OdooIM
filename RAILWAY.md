# Deploy Odoo 19 + module custom lên Railway

Bộ file này (`Dockerfile`, `odoo.conf`, `entrypoint.sh`, `.dockerignore`) đủ để deploy Odoo 19
Community + 4 module custom lên Railway. **Không cần đẩy Odoo core** — image `odoo:19` đã chứa sẵn.

---

## Bước 0 — Chuẩn bị repo deploy (nhẹ, sạch)

Tạo **một repo GitHub mới** (VD `beepro-odoo`) với đúng cấu trúc:

```
beepro-odoo/
├── Dockerfile
├── odoo.conf
├── entrypoint.sh
├── .dockerignore
└── custom_addons/
    ├── im_calendar/
    ├── im_helpdesk/
    └── im_web_backend_lab/
```

Cách làm:
1. Copy 4 file trong thư mục `railway-deploy/` này ra thư mục gốc repo mới.
2. Copy cả thư mục `custom_addons/` (từ repo Odoo hiện tại) vào repo mới.
3. **Mở `odoo.conf` đổi `admin_passwd`** thành mật khẩu mạnh.
4. `git init && git add . && git commit -m "init" && git push` lên GitHub.

> ❌ Đừng copy `odoo/`, `addons/`, `.venv/` — nặng vô ích, image đã có.

---

## Bước 1 — Tạo project trên Railway

1. railway.app → **New Project** → **Deploy from GitHub repo** → chọn repo `beepro-odoo`.
2. Railway tự phát hiện `Dockerfile` và build. (Lần đầu build vài phút.)

---

## Bước 2 — Thêm Postgres

1. Trong project bấm **New → Database → Add PostgreSQL**.
2. Railway tạo service Postgres kèm sẵn biến `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`.

---

## Bước 3 — Nối Odoo với Postgres (biến môi trường)

Mở service **Odoo → tab Variables → New Variable**, thêm 5 biến tham chiếu sang Postgres:

| Biến | Giá trị |
|---|---|
| `PGHOST` | `${{Postgres.PGHOST}}` |
| `PGPORT` | `${{Postgres.PGPORT}}` |
| `PGUSER` | `${{Postgres.PGUSER}}` |
| `PGPASSWORD` | `${{Postgres.PGPASSWORD}}` |
| `PGDATABASE` | `${{Postgres.PGDATABASE}}` |

> `${{Postgres.XXX}}` là cú pháp Railway để trỏ sang biến của service Postgres (đổi `Postgres` cho
> khớp tên service nếu khác).
>
> (Tuỳ chọn) Muốn chọn module cài lần đầu khác đi thì thêm biến `INIT_MODULES`, VD chỉ event:
> `INIT_MODULES = base,web,event,website_event`

---

## Bước 4 — Thêm Volume (BẮT BUỘC)

Service **Odoo → Settings → Volumes → New Volume**, mount path:

```
/var/lib/odoo
```

> Không có volume → **mất toàn bộ ảnh/file upload mỗi lần redeploy**. Đây là lỗi phổ biến nhất.

---

## Bước 5 — Deploy & khởi tạo DB

1. Bấm **Deploy**. Lần đầu, `entrypoint.sh` sẽ tự **khởi tạo DB trắng** (cài base + event +
   website_event + 4 module custom). Xem tiến trình ở tab **Deploy Logs** (mất vài phút).
2. Khi log hiện *"Khởi động Odoo (web port ...)"* là xong.

---

## Bước 6 — Tên miền (domain)

1. Service **Odoo → Settings → Networking → Generate Domain** (được domain `*.up.railway.app`),
   hoặc **Custom Domain** rồi trỏ CNAME tên miền của bạn theo hướng dẫn Railway.
2. HTTPS do Railway tự cấp.

---

## Bước 7 — Đăng nhập & cấu hình lần đầu

1. Mở domain vừa có → đăng nhập admin đầu tiên: **login `admin` / mật khẩu `admin`** →
   **đổi mật khẩu ngay**.
2. Vào *Settings → Technical → System Parameters*, sửa **`web.base.url`** = `https://<domain-cua-ban>`
   (để link event/email trỏ đúng domain, không phải nội bộ).
3. Cấu hình **Outgoing Mail Server** (SMTP Gmail + App Password) như trong tài liệu event.
4. Tạo event BeePro theo `docs/event-community/huong-dan-tao-event.md`.

---

## Ghi chú
- **Dữ liệu không đi theo code**: DB trên Railway là DB mới → event/cấu hình tạo lại tại đây. Muốn
  mang DB local lên là việc riêng (dump/restore Postgres + filestore), làm sau.
- **RAM**: Odoo cần ~0.5–1GB → nên dùng plan trả phí của Railway cho ổn định.
- **Email**: Gmail giới hạn ~500 mail/ngày; event đông nên dùng Brevo/SendGrid/Mailgun.
- **Scale**: đang chạy `workers = 0` (threaded, 1 cổng) cho đơn giản. Cần nhiều worker/websocket thì
  phải cấu hình thêm `gevent-port` — không khuyến nghị trên Railway 1-cổng.
