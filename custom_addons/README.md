# custom_addons

## Mô tả

11 module chạy trên Odoo 19 Community, deploy bằng Docker lên Railway. Không
module nào phụ thuộc Odoo Enterprise.

Mỗi module có `README.md` riêng theo cùng một bố cục: mô tả, tính năng, phân
quyền và cấu hình kỹ thuật, workflow, thành quả. File này chỉ trả lời hai
câu: module nào phục vụ nghiệp vụ nào, và cài cái nào thì phải cài kèm cái gì.

## Bản đồ module theo nghiệp vụ

### Đào tạo nội bộ

| Module | Vai trò | Ghi chú |
|---|---|---|
| [im_elearning](im_elearning/) | Video tự host, chặn thi sớm, chứng chỉ tra cứu, giao khoá học | Lõi của luồng |
| [im_theme](im_theme/) | Mẫu thư, chứng chỉ PDF, trang bắt đầu bài thi | Tự cài kèm `im_elearning`; thiếu thì không gửi được thư và không in được chứng chỉ |
| [im_event_training](im_event_training/) | Lớp học nhiều buổi có điểm danh, chứng chỉ theo chuyên cần, vé early-bird | Luồng song song, không nối với `im_elearning` |

### Mua hàng

| Module | Vai trò | Ghi chú |
|---|---|---|
| [im_purchase_request](im_purchase_request/) | Đề nghị mua hàng, duyệt nhiều cấp theo hạn mức, so sánh báo giá, kiểm soát chi vượt dự toán | Cần `purchase`, `account`, `hr` |

### Chăm sóc khách hàng

| Module | Vai trò | Ghi chú |
|---|---|---|
| [im_helpdesk](im_helpdesk/) | Ticket, SLA, portal khách hàng, tự phân loại theo keyword | Độc lập |
| [im_marketing_journey](im_marketing_journey/) | Kịch bản nuôi dưỡng lead nhiều bước trên `crm.lead` | Cần `crm`. Phần gửi tin chưa nối |

### Hạ tầng và giao diện

| Module | Vai trò | Ghi chú |
|---|---|---|
| [im_web_backend_lab](im_web_backend_lab/) | Home Menu dạng lưới app, navbar riêng, chế độ tối | Độc lập |
| [im_user_default_app](im_user_default_app/) | Chọn app mở sẵn sau khi đăng nhập | Độc lập |
| [im_website_branding](im_website_branding/) | Gỡ "Powered by Odoo" ở chân trang | Độc lập |
| [im_brevo_mail](im_brevo_mail/) | Gửi mail qua HTTP API | Bắt buộc trên Railway vì cổng SMTP bị chặn |
| [im_calendar](im_calendar/) | Sự kiện lịch tạo link Google Meet | Cần đã nối Google Calendar |

## Phụ thuộc

```
im_elearning         -> website_slides, website_slides_survey, survey, hr, hr_skills
  im_theme           -> im_elearning (auto_install)
im_event_training    -> event, event_product, event_sale
im_purchase_request  -> purchase, account, hr
im_helpdesk          -> base_setup, mail, utm, rating, resource, portal
im_marketing_journey -> base, crm, mail
im_web_backend_lab   -> web, base_setup
im_user_default_app  -> web
im_website_branding  -> website
im_calendar          -> calendar, google_calendar
im_brevo_mail        -> base
```

Chỉ có một quan hệ giữa các module nhà: `im_theme` phụ thuộc `im_elearning`. Còn
lại độc lập, cài riêng lẻ được.

## Cron và tham số hệ thống

Bảng gộp để khỏi phải mở từng module:

| Module | Cron | Tham số hệ thống |
|---|---|---|
| im_elearning | Nhắc khoá sắp đến hạn, báo khoá quá hạn (1 ngày/lần, bật sẵn) | `im_elearning.video_upload_limit_mb` (512) |
| im_event_training | Refresh Early Bird Pricing (15 phút/lần, bật sẵn) | không |
| im_marketing_journey | Engine Process Participants (5 phút/lần, bật sẵn) | không |
| im_helpdesk | Automatically close the tickets (1 ngày/lần, **mặc định tắt**) | không |
| im_purchase_request | không | `allow_self_approval` (0), `overrun_tolerance_pct` (10), `min_quote_count` (3) |
| im_brevo_mail | không | `brevo.api_key`, `brevo.sender_email`, `brevo.sender_name` |
