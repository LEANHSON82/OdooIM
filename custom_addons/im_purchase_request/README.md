# im_purchase_request

## Mô tả module

Phiếu đề nghị mua hàng nội bộ, đứng trước đơn mua của Odoo. Nhân viên lập phiếu,
so sánh báo giá nhiều nhà cung cấp, phiếu được ký lần lượt theo hạn mức rồi mới
sinh đơn mua; khâu hoá đơn bị chặn nếu chi vượt dự toán đã duyệt. Odoo CE chỉ có
đơn mua, không có bước đề nghị và ký duyệt nội bộ.

Toàn bộ cấp duyệt, hạn mức và quyền hạn là dữ liệu cấu hình từng công ty, không
hard-code trong code.

## Tính năng

- Phiếu đề nghị với vòng đời 5 trạng thái, chỉ đổi được bằng nút.
- Duyệt nhiều cấp: mỗi cấp gồm nhóm ký, dải tiền áp dụng và phạm vi (toàn công ty
  hoặc theo phòng của người đề nghị).
- Bảng báo giá nhiều nhà cung cấp cho từng dòng hàng, bắt buộc nêu lý do nếu
  không chọn nơi rẻ nhất.
- Số nhà cung cấp tối thiểu: cố định, hoặc thay đổi theo giá trị từng dòng hàng.
- Tạo đơn mua gộp theo nhà cung cấp, mỗi nhà cung cấp một đơn.
- Kiểm soát chi vượt dự toán ở cả bước xác nhận đơn mua và bước vào sổ hoá đơn.
- Một màn hình thiết lập cho mỗi công ty, và tab cấu hình cá nhân trên người dùng.
- Giao việc tự động cho người ký cấp tiếp theo.

## Phân quyền và cấu hình kỹ thuật

Không có cron.

Nhóm quyền dựng sẵn (`security/security.xml`): Trưởng bộ phận, Trưởng phòng vật
tư, Giám đốc (ba nhóm duyệt), Quản trị đề nghị mua hàng (chỉ để cấu hình), và hai
nhóm phụ bật bằng công tắc là Tạo sản phẩm mới, Tạo nhà cung cấp mới.

Nhóm duyệt là dữ liệu chứ không phải hằng số trong code: tick `im_is_approver_role`
trên `res.groups` là nhóm đó hiện ra ở cấp duyệt và ở mục "Là người duyệt" trên
form người dùng. Gõ tên mới vào ô Nhóm duyệt là tạo nhóm luôn.

Ai thấy phiếu nào do năm lớp record rule cộng dồn, tất cả chỉ đọc trừ lớp đầu:
phiếu của chính mình (đọc và ghi), phiếu mình nằm trong chuỗi ký, phiếu của phòng
mình quản lý, người ký cấp toàn công ty thấy mọi phiếu công ty đó, người tạo đơn
mua thấy phiếu đã duyệt và người duyệt vượt thấy phiếu đã ra đơn.

Ba tham số hệ thống (`data/ir_config_parameter_data.xml`, chỉ là giá trị mặc định
ban đầu, sau đó chỉnh trong màn hình Thiết lập):

| Tham số | Mặc định | Việc |
|---|---|---|
| `im_purchase_request.allow_self_approval` | `0` | Cho người đề nghị tự ký cấp mà họ là người duy nhất ký được |
| `im_purchase_request.overrun_tolerance_pct` | `10` | Phần trăm cho phép chi vượt dự toán |
| `im_purchase_request.min_quote_count` | `3` | Số nhà cung cấp tối thiểu mỗi dòng hàng |

Ba cấp duyệt mẫu được nạp sẵn: 0 / trên 5 triệu / trên 50 triệu
(`data/approval_level_data.xml`, `noupdate="1"` nên sửa trong giao diện không bị
ghi đè).

## Workflow

```
draft --submit--> waiting --approve xN--> approved --create PO--> po_created
                     |                       ^                        |
                     | refuse                +---- huỷ hết đơn mua ---+
                     v
                  refused --reset--> draft
```

1. Nhân viên lập phiếu, nhập dòng hàng và báo giá của từng nhà cung cấp.
2. Bấm Trình duyệt. Hệ thống kiểm tra bốn thứ: đúng người đề nghị, mọi dòng có
   đơn giá và nhà cung cấp gợi ý, đủ số nhà cung cấp tối thiểu và có lý do nếu
   không chọn nơi rẻ nhất, và có cấp duyệt khớp số tiền.
3. Chuỗi ký được dựng: lấy các cấp của công ty có dải tiền chứa tổng dự toán, sắp
   theo thứ tự, mỗi cấp một dòng chờ ký. Ký xong một cấp thì giao việc cho người
   ký cấp sau.
4. Duyệt xong, người có quyền bấm Tạo đơn mua; dòng hàng được gộp theo nhà cung
   cấp.
5. Trần chi = tổng đã duyệt nhân (1 + phần trăm cho phép vượt). Xác nhận đơn mua
   hoặc vào sổ hoá đơn vượt trần sẽ bị chặn cho tới khi có người bấm Duyệt vượt
   dự toán và nhập lý do; lý do và người duyệt được ghi thẳng lên hoá đơn.

Người đề nghị có thể rút phiếu khi chưa cấp nào ký. Phiếu bị từ chối quay về Nháp
để sửa rồi trình lại; chuỗi ký cũ bị xoá và dựng lại từ đầu.

## Thành quả

- Cấp duyệt, hạn mức và quyền hạn đều cấu hình được trong giao diện, mỗi công ty
  một bộ, không phải sửa code.
- Lấy một nhóm lõi của Odoo (ví dụ Purchase / Administrator) làm nhóm duyệt thì
  nhóm đó thành vai trò duyệt và hiện trong ô tick cá nhân; bỏ tick ở đó là gỡ
  luôn quyền lõi của người dùng. Nên tạo nhóm duyệt riêng.
- Trần chi tính trên tổng của cả phiếu, không phải từng đơn: một đơn tăng 14% vẫn
  lọt nếu đơn khác giảm bù.
- Ngưỡng duyệt tính trên tổng dự toán chưa thuế.
- Cấp duyệt đã có lịch sử ký thì không xoá được, chỉ tắt `active`.
- `_ensure_company_configs` chạy mỗi lần nâng cấp và phải chạy lại được nhiều lần
  mà không đổi kết quả.
