#!/bin/sh
# =========================================================
#  PF Notify — Installer v2
#  Chạy trên pfSense: sh install.sh [--no-start]
# =========================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NO_START=0

for arg in "$@"; do
    case "$arg" in
        --no-start) NO_START=1 ;;
    esac
done

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

info()  { printf "${CYAN}[INFO]${NC}  %s\n" "$*"; }
ok()    { printf "${GREEN}[OK]${NC}    %s\n" "$*"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$*"; }
err()   { printf "${RED}[ERROR]${NC} %s\n" "$*"; exit 1; }
sep()   { printf "${CYAN}%s${NC}\n" "────────────────────────────────────────────"; }

# ── Kiểm tra root ────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || err "Cần chạy với quyền root (root): sh install.sh"
[ -d "$SCRIPT_DIR/files" ] || err "Không tìm thấy thư mục files/ cạnh install.sh"

sep
printf "${BOLD}  PF Notify Installer${NC}\n"
sep

# ── Backup code cũ ───────────────────────────────────────
BACKUP_TS=$(date '+%Y%m%d-%H%M%S')
BACKUP_DIR="/var/backups/pf_notify/${BACKUP_TS}"
NEED_BACKUP=0
for f in /usr/local/sbin/pf_notify.py \
          /usr/local/etc/rc.d/pf_notify.sh \
          /usr/local/www/pf_notify.php \
          /usr/local/www/pf_notify_api.php; do
    [ -f "$f" ] && NEED_BACKUP=1 && break
done
if [ "$NEED_BACKUP" -eq 1 ]; then
    info "Backup bản cũ → $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    for f in /usr/local/sbin/pf_notify.py \
              /usr/local/etc/rc.d/pf_notify.sh \
              /usr/local/www/pf_notify.php \
              /usr/local/www/pf_notify_api.php; do
        [ -f "$f" ] && cp "$f" "$BACKUP_DIR/" && true
    done
    ok "Backup xong: $BACKUP_DIR"
fi

# ── Dừng service cũ ──────────────────────────────────────
if [ -f /usr/local/etc/rc.d/pf_notify.sh ]; then
    info "Dừng service cũ..."
    sh /usr/local/etc/rc.d/pf_notify.sh stop 2>/dev/null || true
    sleep 1
fi

# ── Tạo thư mục ──────────────────────────────────────────
info "Tạo thư mục..."
mkdir -p /usr/local/sbin /usr/local/www
mkdir -p /usr/local/etc/pf_notify /usr/local/etc/rc.d
mkdir -p /var/db/pf_notify /var/log
chmod 750 /usr/local/etc/pf_notify
chmod 755 /var/db/pf_notify
ok "Thư mục sẵn sàng"

# ── Copy files ───────────────────────────────────────────
info "Cài đặt files..."

cp "$SCRIPT_DIR/files/pf_notify.py"     /usr/local/sbin/pf_notify.py
chmod 755 /usr/local/sbin/pf_notify.py
ok "  /usr/local/sbin/pf_notify.py"

cp "$SCRIPT_DIR/files/pf_notify.sh"     /usr/local/etc/rc.d/pf_notify.sh
chmod 755 /usr/local/etc/rc.d/pf_notify.sh
ok "  /usr/local/etc/rc.d/pf_notify.sh"

cp "$SCRIPT_DIR/files/pf_notify.php"     /usr/local/www/pf_notify.php
cp "$SCRIPT_DIR/files/pf_notify_api.php" /usr/local/www/pf_notify_api.php
chmod 644 /usr/local/www/pf_notify.php
chmod 644 /usr/local/www/pf_notify_api.php
ok "  /usr/local/www/pf_notify.php + pf_notify_api.php"

if [ ! -f /usr/local/etc/pf_notify/config.json ]; then
    cp "$SCRIPT_DIR/files/config.json.example" /usr/local/etc/pf_notify/config.json
    chmod 600 /usr/local/etc/pf_notify/config.json
    ok "  Config tạo mới từ template"
else
    ok "  Config hiện tại giữ nguyên (không ghi đè)"
fi

# ── Đăng ký menu Services ────────────────────────────────
info "Đăng ký menu Services > PF Notify..."
php -r "
require_once('/etc/inc/config.inc');
require_once('/etc/inc/util.inc');
if (!is_array(\$config['installedpackages'])) \$config['installedpackages'] = [];
if (!is_array(\$config['installedpackages']['menu'])) \$config['installedpackages']['menu'] = [];
foreach (\$config['installedpackages']['menu'] as \$k => \$m) {
    if (isset(\$m['url']) && strpos(\$m['url'], 'pf_notify') !== false)
        unset(\$config['installedpackages']['menu'][\$k]);
}
\$config['installedpackages']['menu'][] = [
    'name' => 'PF Notify', 'section' => 'Services',
    'url' => '/pf_notify.php', 'tooltip' => 'Telegram Gateway Notifier',
];
\$config['installedpackages']['menu'] = array_values(\$config['installedpackages']['menu']);
write_config('pf_notify: register menu item');
echo 'OK';
" 2>/dev/null && ok "Menu Services > PF Notify đã đăng ký" || \
    warn "Không đăng ký menu tự động được — vào Navigation thêm thủ công"

# ── Kiểm tra doctor ──────────────────────────────────────
sep
printf "${BOLD}  Kiểm tra hệ thống (Doctor)${NC}\n"
sep
DOCTOR_OK=1

# Python
PY=$(ls /usr/local/bin/python3* 2>/dev/null | tail -1)
if [ -n "$PY" ]; then
    ok "Python: $PY"
else
    warn "Không tìm thấy python3 trong /usr/local/bin/"
    DOCTOR_OK=0
fi

# Files
for f in /usr/local/sbin/pf_notify.py \
          /usr/local/etc/rc.d/pf_notify.sh \
          /usr/local/www/pf_notify.php \
          /usr/local/www/pf_notify_api.php; do
    [ -f "$f" ] && ok "File: $f" || { warn "THIẾU: $f"; DOCTOR_OK=0; }
done

# Config
if [ -f /usr/local/etc/pf_notify/config.json ]; then
    PERM=$(stat -f "%Lp" /usr/local/etc/pf_notify/config.json 2>/dev/null || \
           stat -c "%a"  /usr/local/etc/pf_notify/config.json 2>/dev/null || echo "?")
    ok "Config: /usr/local/etc/pf_notify/config.json (chmod $PERM)"
    TOKEN=$(php -r "
        \$c = json_decode(file_get_contents('/usr/local/etc/pf_notify/config.json'), true);
        echo (!empty(\$c['telegram_token']) && strpos(\$c['telegram_token'],'YOUR_BOT') === false) ? 'set' : 'empty';
    " 2>/dev/null)
    if [ "$TOKEN" = "set" ]; then
        ok "Telegram token: đã cấu hình"
    else
        warn "Telegram token: CHƯA cấu hình → vào GUI điền token"
        DOCTOR_OK=0
    fi
else
    warn "Config chưa có: /usr/local/etc/pf_notify/config.json"
    DOCTOR_OK=0
fi

# ── Start (hoặc thông báo skip) ──────────────────────────
sep
if [ "$NO_START" -eq 1 ]; then
    warn "Bỏ qua khởi động (--no-start). Sau khi điền token, chạy:"
    warn "  sh /usr/local/etc/rc.d/pf_notify.sh start"
else
    info "Khởi động service..."
    sh /usr/local/etc/rc.d/pf_notify.sh start || true
    sleep 2
    STATUS=$(sh /usr/local/etc/rc.d/pf_notify.sh status 2>&1)
    echo "$STATUS" | grep -qi "running" \
        && ok "Service đang chạy!" \
        || warn "Service chưa chạy — kiểm tra token trong GUI"
fi

# ── Tóm tắt ──────────────────────────────────────────────
sep
if [ "$DOCTOR_OK" -eq 1 ]; then
    ok "Cài đặt hoàn tất — tất cả kiểm tra đều qua!"
else
    warn "Cài đặt xong nhưng có cảnh báo ở trên — xem lại."
fi
info "Truy cập GUI: https://<pfsense-ip>/pf_notify.php"
info "Hoặc qua menu: Services > PF Notify"
sep