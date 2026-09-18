# im_brevo_mail

## Mô tả module

Gửi email ra ngoài bằng Brevo HTTP API thay cho SMTP. Railway và nhiều nền tảng
PaaS khác chặn cổng SMTP ra ngoài nên `ir.mail_server` chuẩn của Odoo không gửi
được gì; API HTTP của Brevo đi qua cổng 443 nên không bị chặn.

## Tính năng

- Ghi đè `ir.mail_server.send_email`, dựng JSON và POST sang Brevo.
- Hỗ trợ nhiều người nhận To/Cc/Bcc, Reply-To, thân HTML và text, tệp đính kèm.
- Tự kích hoạt khi tìm thấy khoá API; không có khoá thì Odoo gửi bằng SMTP như
  bình thường, cài module vào không đổi gì.
- Lỗi từ Brevo được ném ra dạng `UserError` kèm 500 ký tự đầu của phản hồi, hiện
  ngay trên hàng đợi thư.

## Phân quyền và cấu hình kỹ thuật

Không có cron, không có nhóm quyền mới. Cần khai khoá API, theo thứ tự ưu tiên
tham số hệ thống trước rồi mới tới biến môi trường:

| Tham số hệ thống | Biến môi trường | Việc |
|---|---|---|
| `brevo.api_key` | `BREVO_API_KEY` | Khoá API; có khoá là module bật |
| `brevo.sender_email` | `BREVO_SENDER_EMAIL` | Email người gửi, phải là sender đã xác thực bên Brevo |
| `brevo.sender_name` | `BREVO_SENDER_NAME` | Tên hiển thị người gửi |

Tham số hệ thống đặt tại Cài đặt > Kỹ thuật > Tham số hệ thống.

## Workflow

1. Tạo khoá API và xác thực sender bên Brevo.
2. Đặt `BREVO_API_KEY` và `BREVO_SENDER_EMAIL` (trên Railway là biến môi trường).
3. Cài module. Từ đó mọi thư của Odoo đi qua Brevo.
4. Thiếu `sender_email` và mail cũng không có `From` thì module báo lỗi rõ chứ
   không gửi lặng lẽ.

## Thành quả

- Mail của Odoo đi được trên môi trường chặn SMTP. Không có khoá thì mọi thứ rơi
  về SMTP gốc, nên cài vào không rủi ro gì.
- Module không đụng tới bản ghi `ir.mail_server`: danh sách máy chủ thư trong Cài
  đặt có thể trống mà mail vẫn đi.
- Brevo trả 202 khi nhận hàng đợi, nên code coi 200/201/202 đều là thành công.
