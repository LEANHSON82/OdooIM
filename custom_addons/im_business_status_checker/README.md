# im_business_status_checker

## Mô tả

Tra cứu **doanh nghiệp còn hoạt động hay không** trên Cổng thông tin quốc gia về
đăng ký doanh nghiệp (`dangkykinhdoanh.gov.vn`).

- **Vào**: mã số thuế hoặc tên doanh nghiệp
- **Ra**: tình trạng doanh nghiệp — Đang hoạt động / Tạm ngừng kinh doanh /
  Ngừng hoạt động / Khác / Chưa rõ

Module tự chứa: chỉ thêm một menu **Tình trạng doanh nghiệp**, không sửa Liên hệ hay bất kỳ
phần nào khác của Odoo.

## Cách dùng

Menu **Tình trạng doanh nghiệp** mở danh sách kết quả với bốn cột: **Tên**, **Mã số thuế**,
**Tình trạng**, **Ngày tra cứu**.

Bấm nút **Tra cứu** trên thanh công cụ (thay cho nút Thêm mới, vì danh sách chỉ
được tạo từ đây), nhập mã số thuế, rồi bấm **Tra cứu**.

Cổng trả lời trong **1–3 phút** vì phải chờ dịch vụ giải captcha, nên việc tra
cứu do cron chạy nền: bản ghi hiện ra ngay ở trạng thái *Chờ tra cứu*. Danh sách
tự nạp lại khi tra xong, không phải bấm F5. Nút **Tra cứu lại** trên form của
bản ghi dùng khi muốn tra mới.

## Cấu hình

Cổng chặn bằng reCAPTCHA ở đúng bước trả kết quả, nên cần khóa dịch vụ của một
nhà cung cấp captcha. Vào **Cài đặt → Tra cứu đăng ký doanh nghiệp**, chọn dịch vụ
(2captcha, Capsolver, Anti-Captcha) và dán khóa. Không có khóa thì bản ghi báo
lỗi kèm hướng dẫn, không có đường vòng miễn phí.

Có thể đặt cả hai qua biến môi trường thay vì lưu trong database:
`CAPTCHA_PROVIDER` và `CAPTCHA_API_KEY`. Cấu hình trong Cài đặt được ưu tiên hơn;
biến môi trường chỉ dùng khi database chưa có giá trị.

Mọi tham số dưới đây chỉnh được ở **Cài đặt → Tra cứu đăng ký doanh nghiệp**;
bảng này để tra nhanh khoá và giá trị mặc định.

| Tham số hệ thống | Mặc định | Việc |
|---|---|---|
| `im_business_status_checker.captcha_provider` | `none` | `none`, `2captcha`, `capsolver`, `anticaptcha` |
| `im_business_status_checker.captcha_api_key` | rỗng | Khóa dịch vụ captcha |
| `im_business_status_checker.captcha_timeout` | `180` | Số giây chờ token tối đa |
| `im_business_status_checker.batch_size` | `10` | Số doanh nghiệp mỗi lần cron chạy |
| `im_business_status_checker.request_delay` | `3` | Nghỉ giữa hai lần gọi cổng (giây) |
| `im_business_status_checker.portal_timeout` | `45` | Số giây chờ cổng mỗi request |
| `im_business_status_checker.portal_retries` | `1` | Số lần thử lại khi cổng bận hoặc chậm |

Cron **Tình trạng doanh nghiệp: tra cứu hàng đợi** chạy 5 phút một lần, xử
lý các bản ghi đang *Chờ tra cứu*. Bấm nút Tra cứu là cron được đánh thức ngay.

## Cách hoạt động

Trang thông tin của cổng không có địa chỉ dùng lại được: cổng chỉ dựng nó cho
một phiên đã đi qua chuỗi postback của chính cổng. Module đi đúng chuỗi đó bằng
HTTP, không dùng trình duyệt:

```
1. GET  /inf/default.aspx                     lấy view state
2. POST postback nhóm sản phẩm "Thông tin về một doanh nghiệp cụ thể"
                                              -> ProductCatalog.aspx?h=<phiên>
3. giải reCAPTCHA của trang đó, POST ô mã số thuế + nút Tìm kiếm
4. bấm dòng kết quả -> trang đơn hàng có dòng "Tình trạng doanh nghiệp"
```

Một lượt tra cứu mất 30–200 giây, chủ yếu là chờ dịch vụ giải captcha; phần mở
form và đọc kết quả chỉ vài chục giây.

Cổng chỉ kiểm captcha **một lần cho mỗi phiên**: vé đã qua dùng lại được cho
những lượt tra sau, nên cron dùng chung một phiên cho cả lô. Đổi lại, sau khi mở
trang chi tiết của một doanh nghiệp thì cổng chỉ vẽ lại kết quả cũ chứ không tra
mới, nên mỗi lượt tra tiếp theo phải mở lại form tra cứu — mở lại form thì không
tốn thêm captcha. Đo thật với 2captcha: **bốn mã số thuế chỉ tốn một lần giải
captcha**; lượt đầu 53 giây, các lượt sau 5–16 giây.

Cổng trả **cùng một trang trống** cho vé captcha hỏng và cho "không tìm thấy",
không phân biệt được bằng nội dung trang. Nên khi dùng lại vé mà không ra kết
quả, module giải vé mới rồi thử lại một lần trước khi kết luận; nhờ vậy không ghi
nhầm "không tìm thấy" chỉ vì vé hết hạn.

Module không lưu tình trạng của doanh nghiệp khác với từ khoá đã hỏi: cổng
render lại bảng kết quả cũ khi không tìm thấy, nên kết quả được đối chiếu mã số
thuế trước khi ghi. Mã số chi nhánh (có dấu `-`) hiện không tra được qua form của
cổng; dùng mã số thuế của công ty mẹ.

### Tra bằng tên doanh nghiệp hiện không dùng được

Thủ tục `GetListByFilterDynamicSqlSelect` trong database của cổng dựng SQL thiếu
biến bind, nên khi ô **Tên doanh nghiệp** có giá trị thì cổng trả
`ORA-01006: bind variable does not exist`. Đã đo ngày 23/09/2026: lỗi xảy ra với
cả ba ô tên (tên doanh nghiệp, tên quốc tế, tên viết tắt), trong khi ô **mã số
thuế** và ô *tên người đại diện theo pháp luật* vẫn chạy bình thường. Đây là lỗi
phía cổng, không sửa được từ phía client.

Cách module xử lý:

- nhận diện trang lỗi đó và báo đúng nguyên nhân, thay vì báo nhầm "cổng đang bận"
- không thử lại vô ích, vì lỗi này lặp lại y hệt
- **bỏ phiên đang hỏng**: trang lỗi làm hỏng cả phiên cổng, nên bản ghi kế tiếp
  trong cùng lô đi bằng phiên mới, không bị lây lỗi
- nhắc người dùng chuyển sang tra bằng mã số thuế

Endpoint autocomplete công khai `/inf/Public/Srv.aspx/GetSearch` cũng đã thử và
trả `{"d":null}` cho mọi từ khoá, nên không dùng làm đường vòng được.

## Thành quả

Trả lời được câu hỏi "doanh nghiệp còn hoạt động hay không" ngay trong Odoo, kèm
ngày tra cứu và tên doanh nghiệp lấy từ cổng, không phải mở trình duyệt tra tay.

## Yêu cầu

`depends`: `base`, `web`. Thư viện Python: `requests`, `lxml` — cả hai đều là
thư viện lõi của Odoo nên image `odoo:19` đã có sẵn.
