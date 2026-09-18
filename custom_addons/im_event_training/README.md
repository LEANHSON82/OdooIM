# im_event_training

## Mô tả module

Biến module Sự kiện của Odoo thành lớp đào tạo nhiều buổi: điểm danh từng buổi,
tính tỉ lệ chuyên cần, cấp chứng chỉ theo ngưỡng và bán vé early-bird có hạn mức.
Module Sự kiện gốc chỉ biết một sự kiện là một mốc thời gian, không có khái niệm
buổi học và điểm danh.

## Tính năng

- `event.session`: chia một sự kiện thành nhiều buổi học.
- `event.session.attendance`: điểm danh từng buổi với ba trạng thái có mặt, vắng,
  được miễn.
- Tự sinh bảng điểm danh khi thêm buổi học hoặc thêm học viên; chỉ tạo phần còn
  thiếu nên chạy lại bao nhiêu lần cũng an toàn.
- Tính tỉ lệ chuyên cần và đánh dấu ai đủ điều kiện nhận chứng chỉ.
- Cấp chứng chỉ lẻ hoặc hàng loạt, có thu hồi.
- Vé early-bird: hai mức giá, hết ưu đãi theo hạn chót hoặc theo số lượng.

## Phân quyền và cấu hình kỹ thuật

Không có nhóm quyền mới; dùng nhóm của module Sự kiện.

Cron bắt buộc: **Event Training: Refresh Early Bird Pricing**, chạy 15 phút một
lần (`data/ir_cron_data.xml`, mặc định bật). Giá vé phụ thuộc thời gian nên không
có sự kiện nào kích hoạt tính lại khi hạn chót trôi qua; thiếu cron thì vé vẫn
bán giá ưu đãi sau khi hết hạn.

Sequence `event.training.certificate` sinh mã chứng chỉ. Không cần tham số hệ
thống hay API key.

Cấu hình trên từng sự kiện: tick "Là khoá đào tạo" và đặt "Ngưỡng chứng chỉ (%)",
mặc định 80. Sự kiện không tick thì không đổi gì.

## Workflow

1. Tạo sự kiện, tick "Là khoá đào tạo", đặt ngưỡng chứng chỉ.
2. Khai báo các buổi học trong tab Buổi học.
3. Học viên đăng ký; bảng điểm danh tự sinh cho từng cặp buổi và học viên.
4. Mỗi buổi, mở nút Điểm danh và đánh dấu có mặt, vắng hoặc được miễn.
5. Hết khoá, bấm "Cấp chứng chỉ hàng loạt"; chỉ người đạt ngưỡng mới được cấp.

Tỉ lệ chuyên cần = số buổi có mặt / (tổng số buổi trừ số buổi được miễn). Được
miễn dùng cho người vào lớp giữa chừng, chuyển lớp, học bù: miễn 2/10 buổi và đi
đủ 8 buổi còn lại vẫn đạt 100%.

## Thành quả

- Khi cấp chứng chỉ, bốn giá trị được ghi cứng vào bản ghi: mã, ngày, tỉ lệ và
  ngưỡng tại thời điểm cấp. Sửa ngưỡng của lớp sau này không làm sai chứng chỉ đã
  cấp. Thu hồi chỉ đổi trạng thái sang `revoked`, không xoá dấu vết.
- Không xoá được sự kiện đã có người đăng ký (`unlink` chặn), vì sẽ mất luôn dữ
  liệu điểm danh, chứng chỉ và liên kết đơn hàng. Huỷ đăng ký hoặc lưu trữ sự kiện.
- `is_early_bird_sale` được đóng dấu lúc đăng ký được tạo, không suy ra sau; nếu
  suy ra sau thì đúng lúc vé hết ưu đãi mọi đơn cũ sẽ bị tính lại thành giá thường.
- `_compute_price` gọi `super()` trên tập con vé không phải early-bird; đổi thành
  gọi trên `self` sẽ làm vé early-bird bị tính lại về giá sản phẩm.
