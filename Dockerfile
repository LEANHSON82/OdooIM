# Odoo 19 Community + module custom, deploy lên Railway.
# Nền là image chính thức odoo:19 (đã là FULL Odoo 19) — ta chỉ chồng custom_addons lên.
FROM odoo:19

# Chạy bằng root để GHI ĐƯỢC vào Volume Railway (/var/lib/odoo mount thuộc root).
# Odoo chỉ CẢNH BÁO khi chạy root, không chặn -> chấp nhận được trong container.
USER root

# Flush log ngay ra Railway (không bị buffer)
ENV PYTHONUNBUFFERED=1

# 1) Chép module custom vào thư mục extra-addons mà Odoo tự quét
COPY custom_addons /mnt/extra-addons

# 2) Cấu hình production + entrypoint riêng cho Railway
COPY odoo.conf /etc/odoo/odoo.conf
COPY entrypoint.sh /entrypoint-railway.sh

RUN chmod +x /entrypoint-railway.sh

# Railway gọi entrypoint này (chạy root); nó tự đọc $PORT + biến Postgres.
ENTRYPOINT ["/entrypoint-railway.sh"]
