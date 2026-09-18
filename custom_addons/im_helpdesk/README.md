# im_helpdesk

## Mô tả module

Helpdesk cho Odoo 19 Community: team, ticket, stage, SLA, cổng portal khách hàng,
đánh giá và hai báo cáo phân tích. Odoo chỉ có Helpdesk ở bản Enterprise; module
này dựng lại trên CE, không phụ thuộc module trả phí nào.

Nhãn trường và chuỗi giao diện để tiếng Anh, bản dịch tiếng Việt đi qua `i18n/`
như module Odoo chuẩn.

## Tính năng

- Team với mail alias riêng, ba mức quyền xem, lịch làm việc riêng và dashboard.
- Ticket vào từ ba đường: backend, email gửi vào alias, và portal khách hàng.
- Stage dùng chung nhiều team; stage `fold` nghĩa là đã đóng. Có wizard hỏi trước
  khi lưu trữ hoặc xoá stage còn ticket.
- Tự phân loại ba bước: gắn tag theo keyword có trọng số, chuyển ticket về team
  phù hợp, rồi chọn người xử lý.
- SLA theo giờ làm việc; stage bị loại trừ làm dừng đồng hồ SLA.
- Phân công tự động chia đều hoặc cân bằng theo số ticket đang mở.
- Tự đóng ticket không hoạt động.
- Khách hàng tự đóng ticket trên portal nếu team cho phép, và đánh giá sau khi
  đóng.
- Hai báo cáo SQL: phân tích ticket và phân tích trạng thái SLA.

## Phân quyền và cấu hình kỹ thuật

Không có tham số hệ thống hay API key.

Cron: **Helpdesk Ticket: Automatically close the tickets**, chạy hằng ngày lúc
1:00 (`data/ir_cron_data.xml`). Mặc định TẮT; bật "Tự động đóng" trên một team
nào đó thì `_update_cron` tự bật cron lên.

Ba nhóm quyền: Helpdesk User (nền), cộng hai nhóm tính năng bật tắt theo cấu hình
team là SLA và Rating. Bật `use_sla` ở bất kỳ team nào là nhóm SLA được cấp qua
nhóm nền; tắt ở team cuối cùng thì nhóm bị gỡ và policy của team đó bị deactivate.

`privacy_visibility` của team có ba mức: chỉ người được mời, mọi nhân viên nội bộ,
và portal. Đổi mức này có tác động phụ lên follower: chuyển sang portal thì khách
hàng của ticket được subscribe; rời portal thì portal user bị gỡ khỏi follower của
cả team lẫn ticket.

`post_init_hook = _create_helpdesk_team` tạo team Customer Care cho mọi công ty
chưa có, kèm 5 stage chuẩn (New, In Progress, On Hold, Solved, Cancelled; hai
stage cuối `fold`). Công ty tạo mới sau đó cũng tự có team.

Cấu hình trên từng team: alias mail, quyền xem, lịch làm việc, bật/tắt SLA và
rating, cho khách tự đóng ticket, tự động phân công, tự động đóng sau bao nhiêu
ngày và từ stage nào sang stage nào.

## Workflow

Ticket vào hệ thống, rồi chạy qua ba bước tự phân loại:

1. **Gắn tag.** Mỗi tag có danh sách keyword (`auto_apply_keywords`, phân tách
   bằng dấu phẩy, chấm phẩy hoặc xuống dòng) và ngưỡng `auto_apply_min_score`.
   Keyword ghi được trọng số: `hoá đơn::3` đóng 3 điểm thay vì 1. Tổng điểm đạt
   ngưỡng thì tag được gắn. So khớp theo biên token nên không dính nhầm chuỗi con,
   và có bước chuẩn hoá riêng cho tiếng Việt.
2. **Chuyển team.** Mỗi rule `helpdesk.tag.assignment` khớp cộng `route_weight`
   cho team của nó; team điểm cao nhất thắng. Nếu team đang có cũng nằm trong
   nhóm cao nhất thì giữ nguyên, không ghi đè lựa chọn sẵn có.
3. **Chọn người.** Trong team thắng, người khớp rule tag mạnh nhất được ưu tiên;
   hoà thì xét ngày làm việc gần nhất theo lịch làm việc, rồi số ticket đang mở,
   rồi ID.

Ba bước này chạy khi tạo ticket và chạy lại sau khi body email trở thành mô tả
ticket, vì lúc tạo ban đầu nội dung để tìm kiếm có thể chưa tồn tại.

SLA: mỗi policy nói ticket của team X, priority Y, tag Z, khách hàng W phải tới
stage đích trong N giờ làm việc. Mỗi ticket sinh các `helpdesk.sla.status` tương
ứng. Ticket nằm trong stage bị loại trừ thì đồng hồ dừng và deadline tạm bị xoá,
quay lại stage tính SLA thì hiện lại.

## Thành quả

- Chạy đủ vòng đời ticket trên CE: nhận từ ba đường vào, tự phân loại, SLA theo
  giờ làm việc, portal khách hàng và hai báo cáo phân tích.
- `data/helpdesk_data.xml` gán thẳng `base.user_admin` làm thành viên team
  Customer Care, nên bản cài mới nào cũng để admin làm người xử lý mặc định. Cân
  nhắc đổi thành viên thật trước khi chạy thật.
- Alias `customer-care` là cố định trong data; nhiều công ty trên cùng database
  thì `_ensure_unique_email_alias` tự thêm hậu tố để không đụng nhau.
- `fold` chứ không phải tên stage mới là thứ quyết định đã đóng. Đặt tên stage là
  "Solved" mà quên tick `fold` thì ticket vẫn tính là đang mở.
- Hai model report là `_auto = False`: sửa `_select` hoặc `_from` xong phải nâng
  cấp module thì `init()` mới dựng lại view SQL.
