# im_calendar

## Mô tả module

Sự kiện lịch tạo link Google Meet thay vì phòng họp Discuss, cho các đơn vị đã
dùng Google Workspace.

## Tính năng

- Nút tạo phòng họp trên form lịch đổi thành "Google Meet".
- Sự kiện mới đồng bộ lên Google luôn kèm yêu cầu tạo phòng họp.
- Chưa nối Google Calendar thì rơi về Discuss như Odoo gốc.

## Phân quyền và cấu hình kỹ thuật

Không có cron, không có tham số hệ thống riêng.

Điều kiện: người dùng phải đã nối Google Calendar (có `google_calendar_token`),
tức là đã cấu hình Google Calendar API trong Cài đặt > Tổng quan > Google
Calendar theo hướng dẫn của Odoo.

## Workflow

1. Người dùng nối tài khoản Google Calendar của mình.
2. Tạo sự kiện lịch, bấm "Google Meet".
3. Module tạo một sự kiện tạm trên Google có `conferenceData`, đọc link Meet
   trong kết quả trả về, rồi xoá sự kiện tạm đó đi. Google không có API cấp
   riêng một link Meet nên đây là cách duy nhất.
4. Link được ghi vào `videocall_location` của sự kiện.

## Thành quả

- Người đã nối Google Calendar bấm một nút là có link Meet ngay trên sự kiện.
- Mọi lỗi (Google hỏng, token hết hạn, hết quota) đều được nuốt và rơi về Discuss,
  người dùng vẫn có phòng họp. Xem log mức warning nếu Meet không ra.
- Thời gian gửi cho Google là UTC không có tzinfo, vì chuỗi `dateTime` tự nối thêm
  hậu tố `Z`; dùng datetime có tzinfo sẽ thành `+00:00Z` và Google từ chối.
