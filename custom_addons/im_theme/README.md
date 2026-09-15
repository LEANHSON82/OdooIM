# im_theme

Phần **nhìn thấy** của `im_elearning`: thư, chứng chỉ PDF, trang thi. Tách riêng
để sửa giao diện mà không đụng vào logic, và để thay bộ mặt khác cho khách khác
bằng cách thay module này.

Tự cài kèm `im_elearning` (`auto_install`). Gỡ đi thì `im_elearning` vẫn chạy
nhưng không gửi thư và không in được chứng chỉ; log ghi rõ lý do.

## Cách nối với im_elearning

`im_elearning` không biết mẫu thư nào tồn tại. Nó gọi
`slide.channel._im_get_mail_template(key)` với `key` là một trong
`certificate_issued`, `exam_failed`, `assignment_reminder`, `assignment_overdue`,
và module này trả về mẫu tương ứng (`models/slide_channel.py`). Muốn làm một
theme khác thì kế thừa đúng hàm đó.

## Nội dung

| File | Việc |
|---|---|
| `data/mail_layout.xml` | Khung thư, kế thừa `mail.mail_notification_light`: đầu thư ghi loại thư và **tên khoá học** thay cho "Your Survey User Input", bỏ dòng Powered by Odoo |
| `data/mail_template_data.xml` | Bốn mẫu thư: gửi chứng chỉ (đính kèm PDF), báo trượt, nhắc hạn, báo quá hạn (cc quản lý) |
| `report/certificate_report.xml` | Chứng chỉ A4 ngang: logo, tên học viên, khoá, điểm, mã tra cứu, QR; dựng bằng bảng vì wkhtmltopdf không tin được flexbox |
| `views/survey_templates.xml` | Trang bắt đầu bài thi của khoá, kể cả khi mở bằng nút Kiểm thử trên form survey: dòng "Bài thi khoá học …", nút "Bắt đầu làm bài", không có huy hiệu Odoo. Survey không gắn với khoá nào giữ nguyên |
| `views/survey_survey_views.xml` | Cảnh báo trên form bài thi khi đặt thêm mẫu thư của CE (học viên sẽ nhận hai thư) |
| `static/src/scss/survey.scss` | Ô đáp án nổi rõ khi chọn, thanh tiến độ mảnh, khối trắng trên ảnh nền; nạp vào bundle `survey.survey_assets` |

## Sửa mẫu

Mẫu thư và report **không** nằm trong `noupdate`. Sửa trong file rồi

```bash
./odoo-bin -c odoo.conf -d <db> -u im_theme --stop-after-init
```

là thư đổi theo. Đừng sửa trên giao diện *Settings ▸ Email Templates*: lần nâng
cấp sau ghi đè lại.

Người gửi thư là người phụ trách khoá (`slide.channel.user_id`), rồi tới email
công ty. Không lấy `create_uid` vì khi học viên tự đỗ bài thi thì `create_uid`
chính là học viên.

## Kiểm thử

```bash
./odoo-bin -c odoo.conf -d <db> -i im_elearning,im_theme --test-enable \
    --test-tags /im_theme --stop-after-init
```

Phủ: bốn thư đúng người nhận, đúng người gửi, đầu thư ghi tên khoá, chứng chỉ có
đính kèm PDF, gửi hỏng không làm mất chứng chỉ, report có mã và QR, dấu thu hồi,
trang thi của khoá hiện tên khoá và nút tiếng Việt còn survey thường thì không.
