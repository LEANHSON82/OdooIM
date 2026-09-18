# im_website_branding

## Mô tả module

Gỡ khối quảng bá "Powered by Odoo" ở chân trang website công khai. Xoá tay trong
trình sửa giao diện sẽ mất mỗi lần nâng cấp module `website`, nên phải làm thành
một addon.

## Tính năng

- Kế thừa template `web.brand_promotion` và xoá khối `o_brand_promotion`.

## Phân quyền và cấu hình kỹ thuật

Không cần nhóm quyền, cron hay tham số hệ thống. Cài là chạy.

## Workflow

Cài module. Mở một trang website ở chế độ ẩn danh, kéo xuống chân trang: không
còn dòng quảng bá.

## Thành quả

- Chân trang sạch và không mất lại sau mỗi lần nâng cấp `website`.
- `priority` để 99 là có chủ ý. `website.brand_promotion` và
  `website_sale.brand_promotion` cũng kế thừa đúng khối này; nếu module mình chạy
  trước, xpath của hai template kia không tìm thấy đích và cả trang vỡ.
- Sau khi cài nên mở thêm trang `/shop` (nếu có `website_sale`) để chắc chắn
  trang vẫn load.
