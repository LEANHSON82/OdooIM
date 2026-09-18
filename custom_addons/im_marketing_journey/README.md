# im_marketing_journey

## Mô tả module

Máy chạy kịch bản nuôi dưỡng lead: lead vào một giai đoạn CRM thì tự động đi qua
chuỗi bước gửi tin, chờ, rẽ nhánh theo điều kiện. Odoo CE không có Marketing
Automation (chỉ Enterprise mới có), nên module dựng lại phần điều phối tối thiểu
cho CRM.

Lưu ý quan trọng: phần gửi tin thật CHƯA nối. `_send_node_message` hiện chỉ ghi
nhật ký, chưa gọi API Zalo ZNS và chưa tạo `mail.mail`. Toàn bộ phần điều phối
(lịch chạy, chống gửi trùng, giờ im lặng, rẽ nhánh, thoát) đã chạy đúng.

## Tính năng

- `im.journey`: kịch bản, trạng thái nháp/đang chạy/tạm dừng, giai đoạn CRM kích
  hoạt.
- `im.journey.node`: ba loại bước là chờ (giờ/ngày), gửi tin (ZNS/email), điều
  kiện (có điện thoại / có email).
- Tự ghi danh lead khi tạo mới hoặc khi đổi giai đoạn.
- Chống gửi trùng bằng hai lớp: giãn cách bước và kiểm tra nhật ký.
- Giờ im lặng 22:00-07:00 theo múi giờ của kịch bản.
- Chặn kịch bản có vòng lặp bằng duyệt DFS tô màu.
- Cho phép lead vào lại kịch bản, đánh số lần chạy.
- Nhật ký `im.journey.log` ghi từng bước: thành công, thất bại, hoãn.

## Phân quyền và cấu hình kỹ thuật

Không có nhóm quyền mới, không có tham số hệ thống hay API key (khi nối ZNS thật
sẽ cần thêm).

Cron bắt buộc: **Marketing Journey: Engine Process Participants**, chạy 5 phút
một lần (`data/ir_cron_data.xml`, mặc định bật). Không có cron thì không bước nào
chạy.

Cấu hình trên từng kịch bản: giai đoạn kích hoạt, giãn cách tối thiểu giữa hai
bước (mặc định 5 phút, không được dưới 1 phút), múi giờ giờ im lặng (mặc định
Asia/Ho_Chi_Minh), cho phép vào lại hay không.

## Workflow

1. Tạo kịch bản, chọn giai đoạn CRM kích hoạt.
2. Khai các bước và nối chúng lại (`next_node_id`, hoặc hai nhánh true/false cho
   bước điều kiện).
3. Bấm Bắt đầu để chuyển kịch bản sang đang chạy.
4. Lead được tạo mới hoặc chuyển vào đúng giai đoạn kích hoạt thì tự thành
   participant, đặt ở bước đầu tiên.
5. Cron 5 phút lấy participant đã tới hạn và chạy bước kế tiếp.
6. Kết thúc khi hết bước (done), hoặc khi lead bị lưu trữ / rời giai đoạn kích
   hoạt (exited, có ghi lý do).

Muốn nối kênh gửi thật thì chỉ sửa `_send_node_message` trong
`models/journey_participant.py`. Giữ nguyên đoạn kiểm tra `already_sent`, gửi
xong ghi `self._log(node, 'success', content)`, gửi lỗi thì ghi trạng thái
`failed`.

## Thành quả

- Phần điều phối đã chạy đủ: ghi danh, lịch chạy, chống gửi trùng, giờ im lặng,
  rẽ nhánh, thoát và vào lại kịch bản.
- Chưa nối kênh gửi thật, như nêu ở phần mô tả.
- Kịch bản tạm dừng thì mọi participant đứng yên, không mất chỗ đang đứng.
- Nhật ký là nguồn sự thật chống gửi trùng; xoá nhật ký là mở đường gửi lại.
