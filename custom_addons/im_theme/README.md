# im_theme

## Mô tả module

Phần nhìn thấy của `im_elearning`: mẫu thư, chứng chỉ PDF, trang bắt đầu bài thi.
Tách riêng để sửa giao diện mà không đụng vào logic, và để thay bộ mặt khác cho
khách khác bằng cách thay module này.

## Tính năng

- Khung thư riêng: đầu thư ghi loại thư và tên khoá học thay cho "Your Survey
  User Input", bỏ dòng Powered by Odoo.
- Bốn mẫu thư: gửi chứng chỉ (đính kèm PDF), báo trượt, nhắc hạn, báo quá hạn
  (cc quản lý).
- Report chứng chỉ A4 ngang: logo, tên học viên, khoá, điểm, mã tra cứu, QR.
- Trang bắt đầu bài thi của khoá học, kể cả khi mở bằng nút Kiểm thử trên form
  survey.
- Cảnh báo trên form bài thi khi đặt thêm mẫu thư của CE (học viên sẽ nhận hai
  thư).

## Phân quyền và cấu hình kỹ thuật

Không có cron, không có tham số hệ thống, không có nhóm quyền mới.

`auto_install = True` nên tự cài kèm `im_elearning`.

Điểm nối duy nhất với `im_elearning`:

```python
self.env['slide.channel']._im_get_mail_template(key)
# key: certificate_issued | exam_failed | assignment_reminder | assignment_overdue
```

`im_elearning` không biết mẫu thư nào tồn tại, nó chỉ gọi hàm này; module trả về
mẫu tương ứng. Muốn làm theme khác thì kế thừa đúng hàm đó.

## Workflow

Không có thao tác người dùng. Sửa mẫu thư hoặc report thì sửa trong file rồi nâng
cấp module:

```bash
./odoo-bin -c odoo.conf -d <db> -u im_theme --stop-after-init
```

Đừng sửa trên giao diện Settings > Email Templates: mẫu không nằm trong
`noupdate` nên lần nâng cấp sau ghi đè lại.

## Thành quả

- Toàn bộ phần nhìn thấy của eLearning gom về một module, đổi bộ mặt khác chỉ cần
  thay module này.
- Gỡ module đi thì `im_elearning` vẫn chạy nhưng không gửi thư và không in được
  chứng chỉ; log ghi rõ lý do.
- Người gửi thư là người phụ trách khoá (`slide.channel.user_id`), rồi tới email
  công ty. Không lấy `create_uid` vì khi học viên tự đỗ bài thi thì `create_uid`
  chính là học viên.
- Chứng chỉ dựng bằng bảng chứ không dùng flexbox, vì wkhtmltopdf không tin được.
