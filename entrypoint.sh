#!/usr/bin/env bash
# Entrypoint cho Odoo trên Railway.
# - Odoo 19 từ chối user 'postgres' -> tự tạo role 'odoo'.
# - Ngắt kết nối cũ + lock_timeout để tránh treo vì lock từ lần deploy trước.
# - Tự phục hồi nếu lần init trước bị cắt giữa chừng.
set -e
export LANG=C.UTF-8 LC_ALL=C.UTF-8   # tắt cảnh báo "perl: locale failed"

SU_HOST="${PGHOST:-${DB_HOST:-localhost}}"
SU_PORT="${PGPORT:-${DB_PORT:-5432}}"
SU_USER="${PGUSER:-postgres}"
SU_PASS="${PGPASSWORD:-postgres}"
DB_NAME="${PGDATABASE:-${DB_NAME:-railway}}"

ODOO_USER="odoo"
ODOO_PASS="${ODOO_DB_PASSWORD:-$SU_PASS}"

WEB_PORT="${PORT:-8069}"
# Module moi nhat dat CUOI danh sach co chu dich: LAST_MODULE ben duoi lay phan tu
# cuoi lam sentinel "da cai du chua", nen them module moi vao cuoi thi lan deploy
# sau se tu dong cai bu. im_elearning keo theo ~28 module phu thuoc (website, hr,
# survey, gamification...) nen lan init dau se lau hon binh thuong.
INIT_MODULES="${INIT_MODULES:-base,web,event,website_event,im_web_backend_lab,im_brevo_mail,im_user_default_app,contacts,project_todo,im_elearning,im_purchase_request,im_theme}"

su_psql() { PGPASSWORD="$SU_PASS" psql -h "$SU_HOST" -p "$SU_PORT" -U "$SU_USER" -d "$DB_NAME" "$@"; }
odoo_psql() { PGPASSWORD="$ODOO_PASS" psql -h "$SU_HOST" -p "$SU_PORT" -U "$ODOO_USER" -d "$DB_NAME" "$@"; }

echo ">> Cho Postgres tai ${SU_HOST}:${SU_PORT} ..."
until su_psql -c 'SELECT 1' >/dev/null 2>&1; do sleep 2; done
echo ">> Postgres san sang."

# --- Ngat cac ket noi cu (tranh treo vi lock tu lan deploy truoc) ---
echo ">> Ngat ket noi cu (neu co) ..."
su_psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true

# --- Role 'odoo' + quyen (idempotent, co lock_timeout) ---
if ! su_psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${ODOO_USER}'" | grep -q 1; then
  echo ">> Tao role '${ODOO_USER}' ..."
  su_psql -v ON_ERROR_STOP=1 -c "CREATE ROLE ${ODOO_USER} LOGIN PASSWORD '${ODOO_PASS}' CREATEDB;"
fi
echo ">> Cap quyen cho '${ODOO_USER}' ..."
su_psql -v ON_ERROR_STOP=1 -c "SET lock_timeout='30s'; GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${ODOO_USER}; GRANT ALL ON SCHEMA public TO ${ODOO_USER}; ALTER SCHEMA public OWNER TO ${ODOO_USER};"
# Cho odoo SO HUU database -> Odoo moi 'nhin thay' DB (list_dbs loc theo chu so huu),
# tranh bi day sang /web/database/selector.
su_psql -v ON_ERROR_STOP=1 -c "ALTER DATABASE ${DB_NAME} OWNER TO ${ODOO_USER};" 2>/dev/null || true

export PGUSER="$ODOO_USER"
export PGPASSWORD="$ODOO_PASS"
DB_ARGS=(--db_host="$SU_HOST" --db_port="$SU_PORT" --db_user="$ODOO_USER" --db_password="$ODOO_PASS")

# --- Trang thai init ---
# State queries must not swallow errors: a failed query that reads as "empty"
# would make a populated DB look uninitialised. With `set -e` a failure here
# stops the container instead.
HAS_TABLES=$(odoo_psql -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ir_module_module' LIMIT 1")
LAST_MODULE="${INIT_MODULES##*,}"   # module cuoi danh sach, dung lam sentinel "da cai du chua"
BASE_STATE=""
BASE_EVER_INSTALLED=""
LAST_STATE=""
if [ "$HAS_TABLES" = "1" ]; then
  BASE_STATE=$(odoo_psql -v ON_ERROR_STOP=1 -tAc "SELECT state FROM ir_module_module WHERE name='base'")
  # latest_version is written only when a module finishes installing
  # (odoo/modules/loading.py), in the same commit as the schema created by the
  # first init. Set means this DB completed an install at least once and holds
  # real data, whatever the current state ('to upgrade' after an interrupted
  # "Upgrade" click, for example).
  BASE_EVER_INSTALLED=$(odoo_psql -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM ir_module_module WHERE name='base' AND latest_version IS NOT NULL")
  LAST_STATE=$(odoo_psql -v ON_ERROR_STOP=1 -tAc "SELECT state FROM ir_module_module WHERE name='${LAST_MODULE}'")
fi

terminate_others() {
  echo ">> Ngat ket noi khac truoc khi init ..."
  su_psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true
}

if [ "$BASE_EVER_INSTALLED" != "1" ]; then
  # Empty DB, or leftovers from a first init that never got base installed:
  # nothing of value yet, so it is safe to reset the schema and install.
  terminate_others
  if [ "$HAS_TABLES" = "1" ]; then
    echo ">> !! DB init do dang, base chua tung cai xong (base=${BASE_STATE:-none}) -> don sach schema de init lai"
    su_psql -v ON_ERROR_STOP=1 -c "SET lock_timeout='30s'; DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ${ODOO_USER}; ALTER SCHEMA public OWNER TO ${ODOO_USER};"
  fi
  echo ">> Khoi tao DB (co the mat 5-15 phut tren Railway): ${INIT_MODULES}"
  odoo -c /etc/odoo/odoo.conf -d "$DB_NAME" "${DB_ARGS[@]}" \
    -i "$INIT_MODULES" --without-demo=True --stop-after-init
  echo ">> Khoi tao xong."
elif [ "$BASE_STATE" != "installed" ] || [ "$LAST_STATE" != "installed" ]; then
  # Never wipe here. Either modules are missing, or a module operation was cut
  # off (base left in 'to upgrade'). Running with -i puts Odoo in update mode,
  # which also finishes every pending 'to install'/'to upgrade'/'to remove'.
  terminate_others
  echo ">> Cai bo sung / hoan tat thao tac module dang do (base=${BASE_STATE}, ${LAST_MODULE}=${LAST_STATE:-none}): ${INIT_MODULES}"
  odoo -c /etc/odoo/odoo.conf -d "$DB_NAME" "${DB_ARGS[@]}" \
    -i "$INIT_MODULES" --without-demo=True --stop-after-init
  echo ">> Cai bo sung xong."
else
  echo ">> Da cai du module -> bo qua init."
fi

# --- Nang cap module custom moi lan deploy ---
# Odoo chi doc lai view/menu/data/quyen khi module duoc NANG CAP. Code Python va
# asset JS thi nap luc khoi dong, nhung XML thi khong. Khong co buoc nay thi sua
# view xong deploy van khong thay gi, va rat kho doan ra vi sao.
#
# Chi nang cap dung nhung module nam trong custom_addons VA dang installed:
# lay danh sach tu thu muc de khong dinh nham module core co ten giong
# (vd im_livechat la module cua Odoo, khong phai cua minh).
# Dat SKIP_UPGRADE=1 tren Railway de bo qua buoc nay khi can deploy that nhanh.
if [ "${SKIP_UPGRADE:-0}" = "1" ]; then
  echo ">> SKIP_UPGRADE=1 -> bo qua nang cap module custom."
else
  CUSTOM_LIST=$(ls -1 /mnt/extra-addons 2>/dev/null | paste -sd, -)
  if [ -n "$CUSTOM_LIST" ]; then
    TO_UPGRADE=$(odoo_psql -tAc \
      "SELECT string_agg(name, ',') FROM ir_module_module
        WHERE state = 'installed'
          AND name = ANY(string_to_array('${CUSTOM_LIST}', ','))" 2>/dev/null || true)
    TO_UPGRADE=$(echo "$TO_UPGRADE" | tr -d '[:space:]')
    if [ -n "$TO_UPGRADE" ]; then
      terminate_others
      echo ">> Nang cap module custom: ${TO_UPGRADE}"
      odoo -c /etc/odoo/odoo.conf -d "$DB_NAME" "${DB_ARGS[@]}" \
        -u "$TO_UPGRADE" --stop-after-init
      echo ">> Nang cap xong."
    else
      echo ">> Khong co module custom nao dang cai -> bo qua nang cap."
    fi
  fi
fi

# --- Tai khoan admin: doi login/mat khau (chi 1 lan, khi login moi chua ton tai) ---
# Dat qua bien moi truong tren Railway de KHONG lo mat khau trong code:
#   ODOO_ADMIN_LOGIN=kurinthefox   ODOO_ADMIN_PASSWORD=<mat khau>
if [ -n "${ODOO_ADMIN_LOGIN:-}" ] && [ -n "${ODOO_ADMIN_PASSWORD:-}" ]; then
  ADMIN_EXISTS=$(odoo_psql -tAc "SELECT 1 FROM res_users WHERE login='${ODOO_ADMIN_LOGIN}'" 2>/dev/null || true)
  if [ "$ADMIN_EXISTS" != "1" ]; then
    echo ">> Doi tai khoan admin -> ${ODOO_ADMIN_LOGIN}"
    printf '%s\n' \
      "admin = env.ref('base.user_admin')" \
      "admin.login = '${ODOO_ADMIN_LOGIN}'" \
      "admin.password = '${ODOO_ADMIN_PASSWORD}'" \
      "env.cr.commit()" \
      "print('>> admin login set to', admin.login)" \
      | odoo shell -c /etc/odoo/odoo.conf -d "$DB_NAME" "${DB_ARGS[@]}" --no-http || true
  fi
fi

echo ">> Khoi dong Odoo (web port ${WEB_PORT}) ..."
exec odoo -c /etc/odoo/odoo.conf -d "$DB_NAME" "${DB_ARGS[@]}" \
  --http-port="$WEB_PORT" --db-filter="^${DB_NAME}\$" "$@"
