# im_elearning

Mở rộng eLearning của **Odoo 19 CE** (`website_slides` + `survey`) đúng bốn phần
CE còn thiếu cho đào tạo nội bộ doanh nghiệp.

Nguyên tắc: **không viết lại thứ CE đã có.** Soạn bài giảng, email đỗ/trượt,
report chứng chỉ PDF, mời học viên ngoài, lọc khoá theo danh mục — CE làm sẵn cả
rồi, module này dùng lại nguyên vẹn.

## Bốn hạng mục

### A. Video tự host

CE chỉ phát được YouTube, Vimeo và Google Drive (`video_source_type` được suy ra
từ `video_url`). Tài liệu đào tạo nội bộ thường không được phép đẩy lên nền tảng
công cộng, kể cả chế độ unlisted.

- Thêm nguồn `local` vào `video_source_type`, kích hoạt khi có tệp tải lên.
- Nhánh player HTML5 `<video>` trong trình xem toàn màn hình, bám đúng quy ước
  hoàn thành của CE (còn 30 giây cuối coi như đã học xong).
- Route `/im_elearning/video/<id>` **kiểm tra quyền thành viên khoá** — không
  dùng `/web/content` vì route đó chỉ kiểm quyền đọc bản ghi, mà `slide.slide`
  thì portal đọc được.
- Tua video hoạt động: Odoo hỗ trợ HTTP Range sẵn.

### B. Chứng chỉ tra cứu được

CE đánh số chứng chỉ bằng chính ID trong database (`str(user_input.id)` đệm 0) và
không có trang nào để người ngoài xác minh.

- Mã dạng `CERT/2026/00042-K7M2QX`: phần đầu theo `ir.sequence` cho dễ đọc, phần
  đuôi ngẫu nhiên 6 ký tự để **đếm lên không dò ra chứng chỉ của người khác**.
  Bảng chữ cái bỏ ký tự dễ nhìn nhầm (0/O, 1/I) vì người ta gõ lại từ bản in.
- Trang `/certificate/verify/<mã>` để `auth='public'`, có QR trên PDF.
- **Có lối vào**: ô nhập mã ngay dưới thanh lọc của `/slides` — gõ mã vào là ra
  kết quả, không phải chuyển trang — và địa chỉ trang nhập mã in dạng chữ cạnh
  QR trên bản PDF. Route để `sitemap=False` nên không có hai thứ này thì người
  cầm bản in mà không quét được QR sẽ không tìm ra đường nào. Chuỗi gốc tiếng
  Anh, bản tiếng Việt ở `i18n/vi_VN.po`.
- Chỉ trả **tên học viên, tên khoá, ngày cấp** và trạng thái thu hồi. Không lộ
  email, không lộ điểm.
- **Không có hạn hiệu lực.** Đây là eLearning học kiến thức; hạn hiệu lực thuộc
  về chứng chỉ tuân thủ bên `hr_skills`, không thuộc về loại này.
- Thu hồi **không xoá bản ghi**: mã đã in ra và phát đi thì phải tra được mãi,
  trả về *"đã thu hồi"* mới đúng chứ *"không tồn tại"* thì người tra không phân
  biệt được với một mã bịa.
- Đỗ khoá thì ghi một dòng `hr.resume.line` vào hồ sơ nhân viên. Học viên ngoài
  (CTV) không có `hr.employee` thì bỏ qua, không lỗi.
- **Gửi thẳng cho học viên** kèm bản PDF có QR. CE cũng gửi thư khi đỗ nhưng đính
  bản PDF của CE — bản đó đánh số bằng ID database và không có QR, cầm nó thì
  không tra được ở đâu. Gửi hỏng (SMTP chết, wkhtmltopdf chết) **không** cuộn
  ngược việc cấp chứng chỉ, vì hàm gửi chạy chung giao dịch với lúc nộp bài thi;
  lọc `Chưa gửi được` trên danh sách chứng chỉ ra những bản cần gửi lại.
- **Người gửi** là người phụ trách khoá (`slide.channel.user_id`), không có thì
  email công ty. Không lấy theo `create_uid`: học viên tự nộp bài thi thì
  `create_uid` chính là học viên, thư sẽ mang tên họ gửi cho họ và dễ bị SPF/DMARC
  chặn nếu họ dùng email ngoài.
- **Trượt cũng có thư.** CE chỉ báo trượt khi bài thi *giới hạn số lần* và đã hết
  lần, kèm theo gỡ luôn học viên khỏi khoá; với mặc định không giới hạn thì trượt
  là im lặng. Module gửi thư sau **mỗi** lần trượt, ghi điểm đạt được, điểm cần
  đạt và đường về khoá. Đúng trường hợp CE đã gửi (hết lần) thì module không gửi
  nữa để học viên không nhận hai thư.

### C. Chặn thi khi chưa học xong

CE không có gating: gõ thẳng URL bài thi là làm được dù chưa xem bài nào.

- `slide.channel.exam_unlock_completion` — ngưỡng phần trăm, mặc định `80`. Đặt
  `0` để không chặn, giữ nguyên hành vi CE.
- Ngưỡng tính trên **bài giảng đã đăng, không tính chính bài thi**. Con số
  `completion` của CE tính cả bài thi vào mẫu số, nên khoá N bài chỉ lên được
  N/(N+1) trước khi thi: khoá 3 bài dừng ở 67% và không bao giờ mở được ở ngưỡng
  80%. Vì vậy module tính riêng qua `_get_lesson_completion`. Bài nháp chưa đăng
  không tính; khoá chỉ có bài thi thì mở luôn.
- Chặn ở **controller**, không chỉ ẩn nút.
- Bị chặn thì quay về trang khoá học với **thông báo nói rõ còn thiếu bao nhiêu**,
  không phải một lỗi 403 cụt lủn. URL chỉ mang cờ `exam_locked=1`; lý do được tính
  lại lúc dựng trang, nên không ai chèn được chữ lạ qua link và thông báo tự biến
  mất khi học viên đã học đủ.
- Người có quyền quản trị khoá vẫn vào được để kiểm thử đề thi.

### D. Giao khoá bắt buộc

CE trả lời được *"ai đã học tới đâu"* nhưng không có khái niệm khoá được **giao**:
không biết ai đáng lẽ phải học mà chưa đụng tới.

- `im.course.assignment`: giao cho nhân viên hoặc cả phòng ban kèm hạn.
- Giao khoá là **ghi danh luôn** — không ghi danh thì khoá không hiện trong danh
  sách của nhân viên và cũng không có gì để đo tiến độ.
- Hai cron: nhắc trước hạn, và báo quá hạn cho cả nhân viên lẫn quản lý trực tiếp.
- Trạng thái `not_started / in_progress / overdue / done` **không lưu vào bảng**,
  vì "quá hạn" phụ thuộc ngày hôm nay nên một trường đã lưu sẽ cũ đi ngay hôm
  sau. Kèm `_search_state` để bộ lọc trên dashboard vẫn chạy đúng.

## Giao diện

Phần nhìn thấy — **thư, chứng chỉ PDF, trang thi** — không nằm ở đây mà ở module
`im_theme`, tự cài kèm. Module này chỉ giữ logic và gọi mẫu thư qua
một điểm nối duy nhất:

```python
self.env['slide.channel']._im_get_mail_template(key)
# key: certificate_issued | exam_failed | assignment_reminder | assignment_overdue
```

Ở đây hàm trả về rỗng; theme kế thừa và trả về mẫu của nó. Không có theme thì
chứng chỉ vẫn được cấp, khoá vẫn được giao, nhưng không thư nào đi và log ghi
rõ lý do; cron nhắc hạn cũng **không** đánh dấu "đã nhắc", để cài theme sau vẫn
gửi đủ. Muốn một bộ mặt khác thì viết module khác kế thừa đúng hàm đó.

## Cấu hình

| Nơi | Thiết lập |
|---|---|
| Khoá học ▸ tab *Thi và chứng chỉ* | Ngưỡng mở bài thi (**mặc định 80%**), bật/tắt cấp chứng chỉ |
| Bài thi ▸ tab *Options* | **Để trống** `Certified Email Template` — module đã tự gửi thư kèm chứng chỉ. Đặt thêm mẫu ở đây thì học viên nhận hai thư mang hai số khác nhau; form có cảnh báo tại chỗ |
| Bài giảng video | Dán liên kết, **hoặc** tải tệp `.mp4/.webm/.mov` lên |
| eLearning ▸ Đào tạo nội bộ | Giao khoá học, xem chứng chỉ đã cấp, **Cấp chứng chỉ còn thiếu** cho người đã đỗ trước khi cài module |

Danh mục khoá học (Nhân sự, Kế toán, Kỹ thuật, Marketing, Kinh doanh) được nạp
sẵn dưới dạng `slide.channel.tag` — hạ tầng lọc trên `/slides` là của CE, module
chỉ nạp dữ liệu.

## Đường dẫn

```
/certificate/verify              ô nhập mã
/certificate/verify/<mã>         kết quả tra cứu (công khai)
/im_elearning/video/<slide_id>   phát video, yêu cầu là thành viên khoá
```

## Cài đặt

```bash
./odoo-bin -c odoo.conf -d <db> -i im_elearning --stop-after-init
```

`im_theme` (thư, chứng chỉ, trang thi) tự cài theo. Phụ thuộc:
`website_slides`, `website_slides_survey`, `survey`, `hr`, `hr_skills`.

Nâng cấp từ bản 1.x: `migrations/19.0.2.0.0` xoá bốn mẫu thư cũ từng nằm trong
module này, theme mang bốn mẫu mới vào.

> Phụ thuộc `hr_skills` là do phần ghi chứng chỉ vào hồ sơ nhân viên. Nếu sau này
> cần chạy ở nơi không cài HR thì tách phần đó ra module bridge riêng.

## Kiểm thử

```bash
./odoo-bin -c odoo.conf -d <db> -i im_elearning --test-enable \
    --test-tags /im_elearning,/im_theme --stop-after-init
```

128 test ở đây, 35 test ở theme. Phủ: định dạng và tính duy nhất của mã, chống
dò mã, thu hồi giữ bản ghi, nối hồ sơ HR, cấp chứng chỉ qua đường thi thật,
không theme thì vẫn cấp nhưng không gửi, ngưỡng chặn thi không tính bài thi,
thông báo khoá thi trên trang khoá qua HTTP thật, trạng thái và bộ lọc khoá
được giao, hai cron, và việc **ba nguồn video sẵn có của CE không bị phá**.
Nội dung thư, report và trang thi kiểm ở theme.

## Tải video lên

Ngay trên trang khoá học: **Thêm nội dung ▸ Video ▸ Upload from Device**, chọn
được **nhiều tệp một lượt**, mỗi tệp thành một bài giảng lấy tên tệp làm tiêu đề.

CE chặn việc này ở bốn chỗ, module gỡ cả bốn: ô input không có `multiple`;
`onChangeFileInput` chỉ nhận ảnh và PDF; chặn cứng 25 MB phía trình duyệt; và
`_formValidateGetValues` ép `source_type = "external"` cho mọi video. Tệp video
không đi kèm lời gọi tạo bài giảng mà gửi riêng qua route multipart, nên không
vướng trần 128 MiB.

Hoặc trên form bài giảng ở backend, bấm **Tải tệp video lên**.
Có thanh tiến trình; lưu bài giảng trước rồi mới tải được (route cần id của bài).

Nút này **không dùng ô upload mặc định của Odoo**, vì ô đó gửi base64 trong một
lời gọi JSON-RPC: vướng trần 128 MiB của request, phồng thêm 1/3 nên tệp thật chỉ
lọt ~96 MB, và với video lớn thì chính tab trình duyệt cũng đuối vì phải giữ cả
chuỗi base64. Thay vào đó có route `/im_elearning/video/upload` nhận multipart.

Trần mặc định **512 MB**, chỉnh bằng tham số hệ thống:

```
Settings ▸ Technical ▸ System Parameters
  im_elearning.video_upload_limit_mb = 512
```

Đừng nâng quá tay: `ir.attachment` chỉ nhận nội dung qua `raw` nên tệp phải nằm
trọn trong bộ nhớ một lần khi ghi — đỉnh RAM xấp xỉ kích thước tệp. Trên Railway
1 GB RAM thì 512 MB đã là sát trần.

## Nạp bài giảng từ danh sách liên kết

Mở khoá học ở backend, bấm nút **Nạp bài giảng từ danh sách liên kết** trên
thanh đầu form (hoặc menu ⚙ Actions). Dán cả
danh sách, mỗi dòng một liên kết YouTube / Vimeo / Google Drive:

```
https://www.youtube.com/watch?v=aaa
https://www.youtube.com/watch?v=bbb | Bài 2 - Quy trình
https://vimeo.com/123456789
# dòng bắt đầu bằng # được bỏ qua
```

Mỗi dòng thành một bài giảng, thứ tự theo đúng thứ tự dòng. Dạng
`liên kết | tiêu đề` để tự đặt tên — tiện khi dán từ bảng tính.

Bật *Tự lấy tiêu đề và thời lượng* thì hệ thống hỏi nền tảng để lấy tiêu đề, mô
tả, ảnh và thời lượng. **YouTube và Google Drive cần khoá API Google** khai ở
cấu hình website; không có khoá thì phần này lặng lẽ bỏ qua và dùng tiêu đề bạn
tự ghi, chứ không làm hỏng cả mẻ. Vimeo không cần khoá.

Chạy lại nhiều lần được: liên kết đã có trong khoá sẽ bỏ qua, nên thêm link mới
vào danh sách cũ rồi chạy lại là chỉ nạp phần thiếu.

> Nút chỉ hiện với người thuộc nhóm **eLearning: Officer** hoặc **Manager**
> (Settings ▸ Users ▸ Access Rights ▸ eLearning). Người dùng thường không có
> nhóm này sẵn, kể cả tài khoản quản trị.

## Sửa nhanh phần và xem trước

Trong **eLearning ▸ Courses ▸ Contents**, hai cột **Phần** và **Xem trước** sửa
trực tiếp được. List này bật `multi_edit`, nên chọn nhiều dòng rồi đặt một lần
là đổi cả loạt — không phải kéo thả từng bài.

Cột *Xem trước* là thứ cho người **chưa đăng nhập** xem được bài giảng: bật nó
cộng với `visibility = public` trên khoá thì khách vãng lai mở link là xem, khỏi
tạo tài khoản. Đổi lại không theo dõi được tiến độ, không thi và không cấp chứng
chỉ — ba thứ đó cần biết người học là ai.

CE để `category_id` là trường tính từ vị trí sequence và chỉ đọc. Module cho ghi
được bằng cách chặn ở `write()` rồi dời bài tới đúng vị trí. Không dùng inverse:
`category_id` là trường tính-toán-có-lưu nên đọc nó bên trong inverse chỉ nhận
lại giá trị cũ, không phải giá trị vừa ghi.

## Chuyển bài giảng sang phần khác

Trong danh sách nội dung, chọn nhiều bài rồi **⚙ Actions ▸ Chuyển sang phần
khác**. Dùng khi bài nằm sai phần và kéo thả từng bài là không khả thi.

Odoo không lưu quan hệ bài giảng - phần mà **suy ra từ vị trí sequence**: bài
thuộc về phần đứng ngay trước nó. Nên công cụ này chèn các bài vào đúng khoảng
giữa phần đích và phần kế tiếp, rồi đẩy phần phía sau xuống lấy chỗ.

## Ghi chú khi triển khai

Video lưu trong filestore (`data_dir`), không nằm trong Postgres. Trên Railway
filestore nằm trên volume mount ở `/var/lib/odoo` — thiếu volume là mất hết sau
mỗi lần redeploy.

Cấu hình Railway hiện tại chạy `workers = 0` (một process threaded), nên mỗi lượt
xem video chiếm một thread của chính process phục vụ cả site. Khi tổng video vượt
khoảng 5GB hoặc bắt đầu đông người xem cùng lúc thì nên chuyển video sang
R2/S3 và cho Odoo giữ URL. Model đã thiết kế quanh URL nên đổi được mà không phải
migrate dữ liệu.
