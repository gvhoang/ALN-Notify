# 📦 Hướng dẫn cài đặt pfSense Telegram Notifier v2

> Hệ thống cảnh báo chuyên nghiệp qua Telegram cho pfSense 2.7+  
> Shell mặc định pfSense là **tcsh** — xem lưu ý ở từng bước.

---

## ⚡ Cài đặt nhanh qua Package (Khuyến nghị)

Thư mục `package/` chứa installer tự động xử lý toàn bộ: copy files, phân quyền, đăng ký menu, kiểm tra sức khoẻ hệ thống.

### Bước 1 — Copy package lên pfSense

Từ máy Windows (PowerShell/cmd):
```bash
# Tạo thư mục đích rồi copy toàn bộ package
ssh admin@192.168.0.1 "mkdir -p /tmp/pf_notify_pkg"
scp -r package/* admin@192.168.0.1:/tmp/pf_notify_pkg/
```

Hoặc dùng **WinSCP**: kéo thả toàn bộ thư mục `package/` vào `/tmp/pf_notify_pkg/` trên pfSense.

### Bước 2 — Chạy installer

```bash
ssh admin@192.168.0.1
sudo sh /tmp/pf_notify_pkg/install.sh
```

Installer tự động:
- ✅ Backup code cũ vào `/var/backups/pf_notify/YYYYmmdd-HHMMSS/`
- ✅ Copy tất cả files vào đúng vị trí
- ✅ Set quyền (`chmod 600` config, `chmod 755` scripts)
- ✅ Tạo config từ template nếu chưa có
- ✅ Đăng ký menu **Services › PF Notify** vào pfSense
- ✅ Doctor check: Python / files / config / token
- ✅ Khởi động service tự động

> **Muốn điền token trước khi khởi động?**  
> Dùng flag `--no-start`, sau đó vào GUI điền token rồi bấm Start:
> ```bash
> sudo sh /tmp/pf_notify_pkg/install.sh --no-start
> ```

### Bước 3 — Mở GUI cấu hình

Sau cài đặt, vào:
```
Services > PF Notify
```
hoặc truy cập thẳng: `https://<IP_PFSENSE>/pf_notify.php`

Điền **Bot Token** + **Chat ID** → **Lưu cấu hình** → bấm **Test** để xác nhận.

---

## ⬆️ Nâng cấp lên phiên bản mới

Nâng cấp **giống hệt cài lần đầu** — chạy lại `install.sh`:

```bash
# Copy package mới lên (ghi đè)
ssh admin@192.168.0.1 "mkdir -p /tmp/pf_notify_pkg"
scp -r package/* admin@192.168.0.1:/tmp/pf_notify_pkg/

# Chạy installer — config được giữ nguyên, code được cập nhật
ssh admin@192.168.0.1 "sudo sh /tmp/pf_notify_pkg/install.sh"
```

- Config `/usr/local/etc/pf_notify/config.json` **không bị ghi đè** nếu đã tồn tại
- Code cũ được **backup tự động** trước khi overwrite
- Service được **restart tự động** sau khi update

---

## 🗑️ Gỡ cài đặt

```bash
ssh admin@192.168.0.1 "sudo sh /tmp/pf_notify_pkg/uninstall.sh"
```

---

## 🔧 Cài đặt thủ công (thay thế)

> Dùng cách này nếu bạn muốn kiểm soát từng bước hoặc không dùng installer.

---

## Yêu cầu

| Thành phần | Phiên bản |
|-----------|-----------|
| pfSense | 2.7+ (FreeBSD) |
| Python | 3.11 (`/usr/local/bin/python3.11`) |
| Telegram Bot | Token + Chat ID |

Không cần cài thêm thư viện — script chỉ dùng thư viện chuẩn Python.

---

## Cấu trúc file v2

| File local | Upload lên pfSense | Mục đích |
|---|---|---|
| `upload_to__usr_local_sbin/pf_notify.py` | `/usr/local/sbin/pf_notify.py` | Script chính |
| `upload_to__usr_local_etc_rc.d/pf_notify.sh` | `/usr/local/etc/rc.d/pf_notify.sh` | Service script |
| `upload_to__usr_local_etc_pf_notify/config.json.example` | `/usr/local/etc/pf_notify/config.json` | File cấu hình |
| `upload_to__usr_local_www/pf_notify.php` | `/usr/local/www/pf_notify.php` | Trang GUI quản lý |
| `upload_to__usr_local_www/pf_notify_api.php` | `/usr/local/www/pf_notify_api.php` | API backend cho GUI |

---

## Bước 1 — Tạo Telegram Bot

1. Nhắn tin `@BotFather` trên Telegram → `/newbot`
2. Đặt tên bot, lấy **Token** (dạng `123456:ABCdef...`)
3. Nhắn tin bot một lần, sau đó mở URL để lấy **Chat ID**:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Tìm trường `"chat":{"id": <SỐ>}` — đó là Chat ID.

---

## Bước 2 — Upload file lên pfSense

**Dùng WinSCP hoặc SCP từ Windows:**
```
upload_to__usr_local_sbin\pf_notify.py        → /usr/local/sbin/pf_notify.py
upload_to__usr_local_etc_rc.d\pf_notify.sh    → /usr/local/etc/rc.d/pf_notify.sh
upload_to__usr_local_www\pf_notify.php        → /usr/local/www/pf_notify.php
upload_to__usr_local_www\pf_notify_api.php    → /usr/local/www/pf_notify_api.php
```

**Lệnh SCP (batch):**
```bash
scp upload_to__usr_local_sbin/pf_notify.py       root@<IP>:/usr/local/sbin/
scp upload_to__usr_local_etc_rc.d/pf_notify.sh   root@<IP>:/usr/local/etc/rc.d/
scp upload_to__usr_local_www/pf_notify.php        root@<IP>:/usr/local/www/
scp upload_to__usr_local_www/pf_notify_api.php    root@<IP>:/usr/local/www/
```

**Phân quyền trên pfSense:**
```tcsh
chmod +x /usr/local/sbin/pf_notify.py
chmod +x /usr/local/etc/rc.d/pf_notify.sh
```

---

## Bước 3 — Tạo thư mục và file config

```tcsh
mkdir -p /usr/local/etc/pf_notify
mkdir -p /var/db/pf_notify
```

Tạo `/usr/local/etc/pf_notify/config.json` — điền token và chat_id của bạn:
```json
{
    "telegram_token": "TOKEN_CỦA_BẠN",
    "telegram_chat_id": "CHAT_ID_CỦA_BẠN",
    "log_files": [
        "/var/log/gateways.log",
        "/var/log/system.log",
        "/var/log/ppp.log"
    ],
    "delay_seconds": 3,
    "spam_cooldown": 300,
    "high_loss_threshold": 20,
    "critical_loss_threshold": 80,
    "gui_fail_threshold": 3,
    "retry_count": 3,
    "retry_backoff": 2,
    "rate_limit_per_min": 10
}
```

> Sau khi cài GUI, bạn có thể chỉnh tất cả cài đặt này từ trình duyệt.

---

## Bước 4 — Test thử

```tcsh
/usr/local/bin/python3.11 /usr/local/sbin/pf_notify.py test \
    --config /usr/local/etc/pf_notify/config.json
```

**Kết quả mong đợi:**
```
📋 Tìm thấy N sự kiện thực tế gần nhất từ log:
...
✅ Đã gửi tin nhắn test thành công!
```

---

## Bước 5 — Khởi động service

```tcsh
/usr/local/etc/rc.d/pf_notify.sh start
/usr/local/etc/rc.d/pf_notify.sh status
```

**Xem log:**
```tcsh
tail -f /var/log/pf_notify.log
```

---

## Bước 6 — Sử dụng GUI quản lý

Mở trình duyệt, truy cập:
```
https://<IP_PFSENSE>/pf_notify.php
```

Trang GUI bao gồm:
- **Cột trái** — Cấu hình Telegram (Token, Chat ID, Test), File Log, Delay/Cooldown, Retry/Rate Limit → **Lưu cấu hình**
- **Cột phải (sidebar)** — Start / Stop / Restart / Reload, trạng thái PID, log realtime tự động làm mới

---

## Lệnh quản lý hàng ngày

```tcsh
/usr/local/etc/rc.d/pf_notify.sh start
/usr/local/etc/rc.d/pf_notify.sh stop
/usr/local/etc/rc.d/pf_notify.sh restart
/usr/local/etc/rc.d/pf_notify.sh reload    # reload config không restart
/usr/local/etc/rc.d/pf_notify.sh status

tail -50 /var/log/pf_notify.log
tail -f  /var/log/pf_notify.log
```

---

## Cập nhật script

```tcsh
# Từ máy Windows copy đè
scp upload_to__usr_local_sbin/pf_notify.py root@<IP>:/usr/local/sbin/

# Reload (không cần restart, nhận config mới qua SIGHUP)
/usr/local/etc/rc.d/pf_notify.sh reload
```

---

## ⚠️ Lưu ý sau nâng cấp pfSense

- `/usr/local/sbin/` và `/usr/local/etc/` **bền qua nâng cấp** (không bị xóa như `/root/`)
- Sau upgrade, kiểm tra lại:
```tcsh
/usr/local/etc/rc.d/pf_notify.sh status
tail -5 /var/log/pf_notify.log
```

---

## Migration từ v1 (pfsense_gw_notify.py)

```tcsh
# Dừng script cũ
pkill -f pfsense_gw_notify.py

# Xóa PID file cũ
rm -f /var/run/pf_notify.pid

# Upload file mới và cài đặt theo hướng dẫn trên
```

---

## Cấu trúc file log pfSense được theo dõi

| File | Nội dung |
|------|----------|
| `/var/log/gateways.log` | Gateway ONLINE/OFFLINE (dpinger) |
| `/var/log/system.log` | Khởi động, tắt máy, GUI auth |
| `/var/log/ppp.log` | PPPoE WAN kết nối/ngắt |
