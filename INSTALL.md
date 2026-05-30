# 📦 Hướng dẫn cài đặt — pfSense ALN Notify v2

> Hệ thống cảnh báo gateway pfSense qua Telegram  
> Công cụ kết nối: **Bitvise SSH Client** (xterm + SFTP)

---

## 📋 Mục lục

- [Yêu cầu](#-yêu-cầu)
- [Bước 0 — Tạo Telegram Bot](#-bước-0--tạo-telegram-bot)
- [Cài đặt qua Package (Khuyến nghị)](#-cài-đặt-qua-package-khuyến-nghị)
- [Cài đặt thủ công (Thay thế)](#-cài-đặt-thủ-công-thay-thế)
- [Cấu hình sau cài đặt](#-cấu-hình-sau-cài-đặt)
- [Forum Topics — Đa máy chủ](#-forum-topics--đa-máy-chủ)
- [Nâng cấp phiên bản](#-nâng-cấp-phiên-bản)
- [Gỡ cài đặt](#-gỡ-cài-đặt)
- [Quản lý dịch vụ hàng ngày](#-quản-lý-dịch-vụ-hàng-ngày)
- [Xử lý sự cố](#-xử-lý-sự-cố)
- [Lưu ý sau nâng cấp pfSense](#-lưu-ý-sau-nâng-cấp-pfsense)

---

## 🖥️ Yêu cầu

| Thành phần | Phiên bản / Ghi chú |
|-----------|---------------------|
| pfSense | 2.7 trở lên (FreeBSD) |
| Python | 3.11 — có sẵn tại `/usr/local/bin/python3.11` |
| Telegram Bot | Token từ @BotFather + Chat ID nhóm/kênh |
| Bitvise SSH Client | SFTP để upload file + xterm để chạy lệnh |
| Thư viện Python | **Không cần cài thêm** — chỉ dùng thư viện chuẩn |

---

## 📱 Bước 0 — Tạo Telegram Bot

1. Mở Telegram → tìm **@BotFather** → nhắn `/newbot`
2. Đặt tên bot (ví dụ: `Pf_HomeHoag_Bot`) → nhận **Token** dạng `123456789:AAFxxxxx`
3. Thêm bot vào nhóm Telegram → nhắn một tin bất kỳ trong nhóm
4. Mở URL sau để lấy **Chat ID** của nhóm:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Tìm `"chat":{"id": -1001234567890}` — giá trị âm là Chat ID nhóm.

> 💡 **Forum Topics (tùy chọn):** Nếu muốn mỗi pfSense gửi vào topic riêng biệt trong nhóm, bật **Topics** trong cài đặt nhóm Telegram (`Group Settings › Topics`) và cấp quyền bot là Admin với quyền `Manage Topics`.

---

## ⚡ Cài đặt qua Package (Khuyến nghị)

Thư mục `package/` chứa installer tự động: backup code cũ, copy files, phân quyền, đăng ký menu pfSense, kiểm tra sức khoẻ hệ thống.

### Bước 1 — Upload package lên pfSense qua Bitvise SFTP

1. Mở **Bitvise SSH Client** → kết nối vào pfSense
2. Chuyển sang tab **SFTP**
3. Trên máy Windows (bên trái), điều hướng đến thư mục `Noti_telegram\package\`
4. Trên pfSense (bên phải), điều hướng đến `/tmp/`
5. Tạo thư mục `pf_notify_pkg` trên pfSense (chuột phải → New folder)
6. Kéo thả **toàn bộ nội dung** thư mục `package\` vào `/tmp/pf_notify_pkg/`

Cấu trúc sau khi upload:
```
/tmp/pf_notify_pkg/
├── install.sh
├── uninstall.sh
└── files/
    ├── pf_notify.py
    ├── pf_notify.sh
    ├── pf_notify.php
    ├── pf_notify_api.php
    └── config.json.example
```

### Bước 2 — Chạy installer qua Bitvise xterm

Chuyển sang tab **Terminal** (xterm) trong Bitvise, chạy:

```sh
sh /tmp/pf_notify_pkg/install.sh
```

Installer tự động thực hiện:
- ✅ Backup code cũ → `/var/backups/pf_notify/YYYYmmdd-HHMMSS/`
- ✅ Dừng service cũ (nếu đang chạy)
- ✅ Copy tất cả files vào đúng vị trí
- ✅ Phân quyền (`chmod 755` scripts, `chmod 600` config)
- ✅ Tạo config từ template nếu chưa có (giữ nguyên nếu đã tồn tại)
- ✅ Đăng ký menu **Services › ALN Notify** vào pfSense
- ✅ Kiểm tra sức khoẻ: Python / files / config / token
- ✅ Khởi động service tự động

> **Muốn điền token trước khi service khởi động?**  
> Dùng flag `--no-start`, sau đó vào GUI điền token rồi nhấn Start:
> ```sh
> sh /tmp/pf_notify_pkg/install.sh --no-start
> ```

### Bước 3 — Cấu hình qua GUI

Sau khi installer hoàn tất, mở trình duyệt:
```
https://<IP_PFSENSE>/pf_notify.php
```
hoặc vào **Services › ALN Notify** trong pfSense.

1. Tab **⚙️ Cấu hình** → điền **Bot Token** và **Chat ID**
2. Nhấn **Lưu cấu hình** → service tự reload
3. Nhấn **Test gửi Telegram** để xác nhận hoạt động

---

## 🔧 Cài đặt thủ công (Thay thế)

> Dùng khi muốn kiểm soát từng bước hoặc không sử dụng package installer.

### Bước 1 — Upload file lên pfSense qua Bitvise SFTP

| File local (trong `Noti_telegram\`) | Đích trên pfSense |
|---|---|
| `upload_to__usr_local_sbin\pf_notify.py` | `/usr/local/sbin/pf_notify.py` |
| `upload_to__usr_local_etc_rc.d\pf_notify.sh` | `/usr/local/etc/rc.d/pf_notify.sh` |
| `upload_to__usr_local_www\pf_notify.php` | `/usr/local/www/pf_notify.php` |
| `upload_to__usr_local_www\pf_notify_api.php` | `/usr/local/www/pf_notify_api.php` |

### Bước 2 — Tạo thư mục và phân quyền

SSH vào pfSense (Bitvise xterm), chạy từng lệnh:

```sh
mkdir -p /usr/local/etc/pf_notify
mkdir -p /var/db/pf_notify
chmod +x /usr/local/sbin/pf_notify.py
chmod +x /usr/local/etc/rc.d/pf_notify.sh
```

### Bước 3 — Tạo file cấu hình

Upload file `upload_to__usr_local_etc_pf_notify\config.json.example` lên pfSense, sau đó:

```sh
cp /đường/dẫn/config.json.example /usr/local/etc/pf_notify/config.json
chmod 600 /usr/local/etc/pf_notify/config.json
```

Hoặc cấu hình trực tiếp qua GUI (không cần tạo thủ công).

### Bước 4 — Test kết nối Telegram

```sh
/usr/local/bin/python3.11 /usr/local/sbin/pf_notify.py test --single --config /usr/local/etc/pf_notify/config.json
```

Kết quả mong đợi:
```
[xx:xx:xx] 🧪 Gửi tin test...
✅ Đã gửi tin nhắn test thành công!
```

### Bước 5 — Khởi động service

```sh
/usr/local/etc/rc.d/pf_notify.sh start
/usr/local/etc/rc.d/pf_notify.sh status
```

Kết quả mong đợi:
```
pf_notify running (PID: 12345)
```

---

## ⚙️ Cấu hình sau cài đặt

### Qua GUI (Khuyến nghị)

Truy cập `https://<IP_PFSENSE>/pf_notify.php` → tab **⚙️ Cấu hình**.

GUI tự động tạo/cập nhật `/usr/local/etc/pf_notify/config.json` và reload service.

### Thủ công qua file

File cấu hình: `/usr/local/etc/pf_notify/config.json`

```json
{
  "telegram_token":   "123456789:AAFxxxxx",
  "telegram_chat_id": "-1001234567890",

  "log_files": [
    "/var/log/gateways.log",
    "/var/log/system.log",
    "/var/log/ppp.log"
  ],

  "delay_seconds":   3,
  "spam_cooldown":   300,

  "high_loss_threshold":     20,
  "critical_loss_threshold": 80,

  "gui_fail_threshold": 3,

  "retry_count":   3,
  "retry_backoff": 2,

  "rate_limit_per_min": 10,

  "use_topics": false,
  "topic_name": ""
}
```

Sau khi sửa file thủ công, áp dụng ngay (không cần restart):
```sh
/usr/local/etc/rc.d/pf_notify.sh reload
```

### Bảng tham số cấu hình

| Tham số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `telegram_token` | `""` | Bot Token lấy từ @BotFather |
| `telegram_chat_id` | `""` | Chat ID nhóm/kênh nhận thông báo |
| `delay_seconds` | `3` | Trì hoãn N giây trước khi gửi — lọc flap thoáng qua |
| `spam_cooldown` | `300` | Không gửi lại cùng trạng thái trong N giây |
| `high_loss_threshold` | `20` | Ngưỡng % mất gói tin → cảnh báo mức cao |
| `critical_loss_threshold` | `80` | Ngưỡng % mất gói tin → nghiêm trọng (xem như offline) |
| `gui_fail_threshold` | `3` | Số lần sai mật khẩu liên tiếp → cảnh báo bảo mật |
| `retry_count` | `3` | Số lần thử lại khi Telegram API trả lỗi |
| `retry_backoff` | `2` | Giây chờ ban đầu giữa các lần retry (nhân đôi mỗi lần) |
| `rate_limit_per_min` | `10` | Tối đa N tin/phút. `0` = không giới hạn |
| `use_topics` | `false` | Bật Forum Topics (gửi vào topic riêng của máy chủ) |
| `topic_name` | `""` | Tên topic trong nhóm Telegram (ví dụ: `homehoag`) |

---

## 🗂️ Forum Topics — Đa máy chủ

Tính năng này cho phép nhiều pfSense cùng gửi vào **một nhóm Telegram**, mỗi máy chủ có **topic riêng** để phân loại rõ ràng.

### Yêu cầu

1. Nhóm Telegram phải là **Supergroup** với **Topics** được bật  
   (`Group Settings › Topics › Enable Topics`)
2. Bot phải là **Admin** trong nhóm với quyền **Manage Topics**  
   (không cần các quyền khác như Pin Messages)

### Cấu hình

Trong `config.json` của **từng pfSense**, điền khác nhau ở `topic_name`:

**Máy chủ 1** (`homehoag.vnc.id.vn`):
```json
{
  "telegram_chat_id": "-1001234567890",
  "use_topics": true,
  "topic_name": "homehoag"
}
```

**Máy chủ 2** (`netphamgiang.vnc.id.vn`):
```json
{
  "telegram_chat_id": "-1001234567890",
  "use_topics": true,
  "topic_name": "netphamgiang"
}
```

Khi khởi động lần đầu, script tự động tạo topic nếu chưa tồn tại và lưu `thread_id` vào state file.

---

## ⬆️ Nâng cấp phiên bản

Chạy lại installer — config được **giữ nguyên**, code được **cập nhật**, service được **restart tự động**.

**Bước 1** — Upload package mới lên pfSense qua Bitvise SFTP (ghi đè `/tmp/pf_notify_pkg/`)

**Bước 2** — Chạy lại installer:
```sh
sh /tmp/pf_notify_pkg/install.sh
```

---

## 🗑️ Gỡ cài đặt

```sh
sh /tmp/pf_notify_pkg/uninstall.sh
```

---

## 🎮 Quản lý dịch vụ hàng ngày

```sh
# Khởi động
/usr/local/etc/rc.d/pf_notify.sh start

# Dừng
/usr/local/etc/rc.d/pf_notify.sh stop

# Khởi động lại
/usr/local/etc/rc.d/pf_notify.sh restart

# Áp dụng config mới ngay (không restart)
/usr/local/etc/rc.d/pf_notify.sh reload

# Kiểm tra trạng thái
/usr/local/etc/rc.d/pf_notify.sh status

# Xem log 50 dòng gần nhất
tail -50 /var/log/pf_notify.log

# Theo dõi log realtime
tail -f /var/log/pf_notify.log
```

### Kiểm tra process đang chạy

```sh
ps aux | grep pf_notify | grep -v grep
```

Kết quả bình thường (2 process):
```
root  10898  0.0  0.0  ... daemon: /usr/local/bin/python3.11[11231] (daemon)
root  11231  0.3  0.3  ... /usr/local/bin/python3.11 /usr/local/sbin/pf_notify.py
```

---

## 🔧 Xử lý sự cố

### Daemon không khởi động

```sh
# Kiểm tra Python tồn tại
/usr/local/bin/python3.11 --version

# Kiểm tra quyền thực thi
ls -la /usr/local/sbin/pf_notify.py
ls -la /usr/local/etc/rc.d/pf_notify.sh

# Kiểm tra syntax JSON config
/usr/local/bin/python3.11 -c "import json; json.load(open('/usr/local/etc/pf_notify/config.json')); print('Config OK')"

# Chạy thủ công để xem lỗi chi tiết
/usr/local/bin/python3.11 /usr/local/sbin/pf_notify.py watch --config /usr/local/etc/pf_notify/config.json
```

### Không nhận được tin Telegram

```sh
# Gửi tin test đơn
/usr/local/bin/python3.11 /usr/local/sbin/pf_notify.py test --single --config /usr/local/etc/pf_notify/config.json

# Xem nội dung config
cat /usr/local/etc/pf_notify/config.json

# Xác minh Bot Token còn hợp lệ
curl "https://api.telegram.org/bot<TOKEN>/getMe"
```

### Tin nhắn vào #General thay vì topic

```sh
# Xóa state cũ để tạo lại topic
rm -f /var/db/pf_notify/state.json

# Restart service
/usr/local/etc/rc.d/pf_notify.sh restart

# Kiểm tra log tạo topic
tail -20 /var/log/pf_notify.log
# Phải thấy: [TOPIC] Đã tạo topic '...' → thread_id=XX
```

### PID file còn nhưng process không chạy

```sh
rm -f /var/run/pf_notify.pid
/usr/local/etc/rc.d/pf_notify.sh start
```

### Nhiều process Python chạy song song (orphan)

```sh
# Dừng tất cả process liên quan
pkill -f "pf_notify.py"

# Xóa PID file cũ
rm -f /var/run/pf_notify.pid

# Khởi động lại
/usr/local/etc/rc.d/pf_notify.sh start

# Xác nhận chỉ có 2 process (daemon wrapper + python child)
ps aux | grep pf_notify | grep -v grep
```

### Cảnh báo spam quá nhiều

Tăng `spam_cooldown` (mặc định 300s = 5 phút) rồi reload:
```sh
# Sửa config
vi /usr/local/etc/pf_notify/config.json
# Đổi: "spam_cooldown": 600

# Áp dụng ngay
/usr/local/etc/rc.d/pf_notify.sh reload
```

---

## ⚠️ Lưu ý sau nâng cấp pfSense

Các thư mục cài đặt **tồn tại qua nâng cấp pfSense** (không bị xóa):
- `/usr/local/sbin/` — script Python chính
- `/usr/local/etc/` — service script và config
- `/usr/local/www/` — GUI files
- `/var/db/pf_notify/` — state file

Sau mỗi lần nâng cấp pfSense, kiểm tra:
```sh
/usr/local/etc/rc.d/pf_notify.sh status
tail -5 /var/log/pf_notify.log
```

Nếu service không tự khởi động sau nâng cấp:
```sh
# Kiểm tra quyền execute vẫn còn
ls -la /usr/local/etc/rc.d/pf_notify.sh
# Phải có: -rwxr-xr-x

# Khởi động lại thủ công
/usr/local/etc/rc.d/pf_notify.sh start
```

---

## 📁 Vị trí file sau khi cài đặt

| File trên pfSense | Mục đích |
|---|---|
| `/usr/local/sbin/pf_notify.py` | Script Python chính (daemon giám sát) |
| `/usr/local/etc/rc.d/pf_notify.sh` | Service script — tự khởi động khi boot |
| `/usr/local/etc/pf_notify/config.json` | Cấu hình (token, chat_id, ngưỡng cảnh báo) |
| `/usr/local/www/pf_notify.php` | Trang quản lý GUI |
| `/usr/local/www/pf_notify_api.php` | API backend cho GUI |
| `/var/db/pf_notify/state.json` | Trạng thái gateway + topic cache (tự tạo) |
| `/var/log/pf_notify.log` | Log hoạt động |
| `/var/run/pf_notify.pid` | PID của daemon wrapper |
| `/var/backups/pf_notify/` | Backup tự động khi nâng cấp |

---

## 📊 File log pfSense được giám sát

| File | Sự kiện theo dõi |
|------|-----------------|
| `/var/log/gateways.log` | Gateway ONLINE/OFFLINE, mất gói tin, RTT (dpinger) |
| `/var/log/system.log` | Khởi động/tắt máy, đăng nhập GUI pfSense |
| `/var/log/ppp.log` | PPPoE WAN kết nối / ngắt kết nối |
