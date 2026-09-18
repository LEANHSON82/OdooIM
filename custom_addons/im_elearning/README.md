# im_elearning

## Mô tả module

Mở rộng eLearning của Odoo 19 CE (`website_slides` + `survey`) đúng bốn phần CE
còn thiếu cho đào tạo nội bộ doanh nghiệp: video tự host, chứng chỉ tra cứu được,
chặn thi khi chưa học xong, và giao khoá học bắt buộc.

Nguyên tắc: không viết lại thứ CE đã có. Soạn bài giảng, mời học viên ngoài, lọc
khoá theo danh mục đều dùng lại nguyên vẹn của CE.

## Tính năng

- **Video tự host**: thêm nguồn `local` vào `video_source_type`, phát bằng thẻ
  video HTML5, tải lên nhiều tệp một lượt, mỗi tệp thành một bài giảng. Route
  phát video kiểm tra tư cách thành viên khoá học.
- **Chứng chỉ tra cứu được**: mã dạng `CERT/2026/00042-K7M2QX`, trang tra cứu
  công khai, QR trên bản PDF, thu hồi không xoá bản ghi, tự ghi một dòng
  `hr.resume.line` vào hồ sơ nhân viên.
- **Chặn thi sớm**: phải học đủ tỉ lệ bài giảng mới mở được bài thi, chặn ở
  controller chứ không chỉ ẩn nút.
- **Giao khoá học**: giao cho nhân viên hoặc cả phòng ban kèm hạn, có nhắc trước
  hạn và báo quá hạn.
- Nạp bài giảng hàng loạt từ danh sách liên kết YouTube / Vimeo / Google Drive.
- Sửa nhanh phần và cờ Xem trước theo lô; công cụ chuyển nhiều bài sang phần khác.

## Phân quyền và cấu hình kỹ thuật

Hai cron, cả hai chạy 1 ngày một lần và mặc định bật (`data/ir_cron_data.xml`):
**eLearning: nhắc khoá học sắp đến hạn** và **eLearning: báo khoá học quá hạn**.
Không có cron thì phần giao khoá vẫn chạy nhưng không ai được nhắc.

Một tham số hệ thống: `im_elearning.video_upload_limit_mb`, mặc định 512. Đừng
nâng quá tay: `ir.attachment` chỉ nhận nội dung qua `raw` nên tệp phải nằm trọn
trong bộ nhớ một lần khi ghi, đỉnh RAM xấp xỉ kích thước tệp.

Cấu hình trên từng khoá học (tab Thi và chứng chỉ): `exam_unlock_completion` là
ngưỡng phần trăm mở bài thi, mặc định 80, đặt 0 để không chặn; và công tắc bật
tắt cấp chứng chỉ.

Nút "Nạp bài giảng từ danh sách liên kết" chỉ hiện với nhóm eLearning: Officer
hoặc Manager. Người dùng thường không có nhóm này sẵn, kể cả tài khoản quản trị.
Muốn tự lấy tiêu đề và thời lượng thì cần khoá API Google khai ở cấu hình website
(YouTube và Google Drive cần, Vimeo không cần); không có khoá thì phần này lặng
lẽ bỏ qua chứ không làm hỏng cả mẻ.

Giao diện (thư, chứng chỉ PDF, trang thi) nằm ở module `im_theme`, tự cài kèm.

Ba đường dẫn: `/certificate/verify` (ô nhập mã), `/certificate/verify/<mã>` (kết
quả, công khai), `/im_elearning/video/<slide_id>` (phát video, yêu cầu là thành
viên khoá).

## Workflow

1. Tạo khoá học, đặt ngưỡng mở bài thi và bật cấp chứng chỉ.
2. Thêm bài giảng: dán liên kết, tải tệp video lên, hoặc nạp cả danh sách liên
   kết một lượt.
3. Giao khoá cho nhân viên hoặc phòng ban kèm hạn. Giao khoá là ghi danh luôn.
4. Học viên học; muốn vào bài thi phải đạt ngưỡng phần trăm bài giảng đã học.
   Ngưỡng tính trên bài giảng đã đăng và không tính chính bài thi.
5. Đỗ thì chứng chỉ được cấp tự động, gửi thư kèm PDF có QR, và ghi một dòng vào
   hồ sơ nhân viên. Trượt thì có thư báo điểm đạt được và điểm cần đạt.
6. Người ngoài cầm bản in vào `/certificate/verify`, gõ mã, thấy tên học viên,
   tên khoá, ngày cấp và trạng thái thu hồi. Không lộ email, không lộ điểm.

## Thành quả

- Bốn phần CE còn thiếu đều đã chạy: video tự host, chứng chỉ tra cứu được, chặn
  thi sớm, giao khoá học kèm nhắc hạn.
- Trên form bài thi phải ĐỂ TRỐNG ô `Certified Email Template` của CE. Đặt thêm
  mẫu ở đó thì học viên nhận hai thư mang hai số chứng chỉ khác nhau; form có
  cảnh báo tại chỗ.
- Gửi thư hỏng (SMTP chết, wkhtmltopdf chết) không cuộn ngược việc cấp chứng chỉ.
  Lọc "Chưa gửi được" trên danh sách chứng chỉ ra những bản cần gửi lại.
- Chưa hỗ trợ tải tệp Office (Word, Excel, PowerPoint) làm bài giảng; hiện chỉ
  video, PDF và ảnh.
- Xem video yêu cầu đăng nhập và là thành viên khoá, kể cả khi bài giảng bật cờ
  Xem trước. Đây là đánh đổi có chủ ý: route `/web/content` chỉ kiểm quyền đọc
  bản ghi mà `slide.slide` thì portal đọc được.
- Video nằm trong filestore (`data_dir`), không nằm trong Postgres. Trên Railway
  phải có volume mount ở `/var/lib/odoo`, thiếu volume là mất hết sau mỗi lần
  redeploy. Cấu hình hiện tại chạy `workers = 0` nên mỗi lượt xem video chiếm một
  thread của process phục vụ cả site; vượt khoảng 5GB video hoặc đông người xem
  cùng lúc thì nên chuyển video sang R2/S3 và cho Odoo giữ URL.
