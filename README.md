# 🔔 pfSense ALN Notify — Cảnh báo Telegram chuyên nghiệp

> Hệ thống giám sát gateway pfSense và gửi thông báo qua Telegram  
> Dành cho quản trị viên mạng — hỗ trợ đa máy chủ, đa WAN, Forum Topics

---

## 📋 Mục lục

- [Tính năng](#-tính-năng)
- [Ví dụ thông báo](#-ví-dụ-thông-báo)
- [Yêu cầu hệ thống](#-yêu-cầu-hệ-thống)
- [Cài đặt nhanh](#-cài-đặt-nhanh)
- [Quản lý dịch vụ](#-quản-lý-dịch-vụ)
- [Giao diện quản lý GUI](#-giao-diện-quản-lý-gui)
- [Cấu hình tham chiếu](#-cấu-hình-tham-chiếu)
- [Forum Topics — Đa máy chủ](#-forum-topics--đa-máy-chủ)
- [Xử lý sự cố](#-xử-lý-sự-cố)
- [Cấu trúc thư mục](#-cấu-trúc-thư-mục)

---

## ✨ Tính năng

| Tính năng | Mô tả |
|-----------|-------|
| 🔴🟢 Gateway ONLINE/OFFLINE | Phát hiện tức thì khi WAN mất/khôi phục kết nối |
| 📊 Cảnh báo mất gói tin | Hai ngưỡng tùy chỉnh: cao (20%) và nghiêm trọng (80%) |
| 🌐 Phân loại nhà mạng | Tự động nhận diện Viettel 🔴, FPT 🟠, VNPT 🟡, CMC 🔵, v.v. |
| 🔌 Theo dõi PPPoE | Giám sát kết nối/ngắt kết nối đường truyền PPPoE WAN |
| 🔐 Cảnh báo bảo mật | Phát hiện đăng nhập sai mật khẩu pfSense liên tiếp |
| 🚫 Chống spam | Không gửi lặp lại cùng trạng thái trong khoảng thời gian cấu hình |
| ⏱️ Delay thông minh | Trì hoãn N giây trước khi gửi, loại bỏ flap thoáng qua |
| 🔁 Tự động retry | Tự thử lại khi Telegram lỗi mạng (exponential backoff) |
| ⚡ Rate limiting | Giới hạn số tin nhắn/phút tránh flood kênh |
| 🔄 Hot reload | Áp dụng cấu hình mới ngay lập tức, không cần khởi động lại |
| 🗂️ Forum Topics | Mỗi máy chủ pfSense gửi vào topic riêng trong nhóm Telegram |
| 🖥️ Đa máy chủ | Triển khai độc lập trên nhiều pfSense, cùng 1 nhóm Telegram |
| 🌐 Giao diện Web GUI | Quản lý cấu hình, điều khiển service, xem log từ trình duyệt |
| 📦 Package Installer | Cài đặt tự động: copy, phân quyền, đăng ký menu, kiểm tra sức khoẻ |

---

## 📱 Ví dụ thông báo

**Gateway mất kết nối:**
```
🔴 GATEWAY MẤT KẾT NỐI

🖥️ Máy chủ: homehoag.vnc.id.vn
🔴 WAN (Viettel): VIETTEL_TAYNINH
📡 IP Monitor: 10.123.234.2
🔗 IP Gateway: 10.123.234.1

⚠️ Mất gói tin: 100%
⚠️ RTT: timeout

🛣️ Xóa khỏi nhóm định tuyến:
FPT_st1

⏰ 30/05/2026 12:49:02
```

**Gateway khôi phục kết nối:**
```
🟢 GATEWAY KẾT NỐI TRỞ LẠI

🖥️ Máy chủ: homehoag.vnc.id.vn
🔴 WAN (Viettel): VIETTEL_TAYNINH
📡 IP Monitor: 10.123.234.2
🔗 IP Gateway: 10.123.234.1

⏱️ RTT: 12.607ms ± 1.22ms

🛣️ Thêm vào nhóm định tuyến:
FPT_st1

⏰ 30/05/2026 12:51:45
```

**Cảnh báo mất gói tin cao:**
```
⚠️ CẢNH BÁO MẤT GÓI TIN CAO

🖥️ Máy chủ: homehoag.vnc.id.vn
🟠 WAN (FPT): FPT_TPHCM
📡 IP Monitor: 203.113.131.1

📉 Mất gói tin: 45%

⏰ 30/05/2026 14:22:10
```

**Cảnh báo bảo mật GUI:**
```
🚨 CẢNH BÁO BẢO MẬT

🖥️ Máy chủ: homehoag.vnc.id.vn
⚠️ Sai mật khẩu 3 lần liên tiếp
👤 Tài khoản: admin
🌍 IP nguồn: 192.168.1.252

⏰ 30/05/2026 03:05:09
```

---

## 🖥️ Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|-----------|---------|
| pfSense | 2.7 trở lên (FreeBSD) |
| Python | 3.11 — có sẵn tại `/usr/local/bin/python3.11` |
| Telegram Bot | Token từ @BotFather + Chat ID nhóm/kênh |
| Thư viện Python | **Không cần cài thêm** — chỉ dùng thư viện chuẩn |
| Công cụ upload | **Bitvise SSH Client** (SFTP + xterm) hoặc SCP |

---

## ⚡ Cài đặt nhanh

> Chi tiết đầy đủ xem **[INSTALL.md](INSTALL.md)**.

```sh
# 1. Upload thư mục package/ lên pfSense qua Bitvise SFTP → /tmp/pf_notify_pkg/

# 2. SSH vào pfSense (Bitvise xterm), chạy installer:
sh /tmp/pf_notify_pkg/install.sh

# 3. Mở GUI cấu hình:
#    https://<IP_PFSENSE>/pf_notify.php
#    Services > ALN Notify
```

---

## 🎮 Quản lý dịch vụ

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
```

### Xem log

```sh
# 50 dòng gần nhất
tail -50 /var/log/pf_notify.log

# Theo dõi realtime
tail -f /var/log/pf_notify.log
```

---

## 🌐 Giao diện quản lý GUI

Truy cập: `https://<IP_PFSENSE>/pf_notify.php` hoặc **Services › ALN Notify**

### Tab ⚙️ Cấu hình
- Nhập / cập nhật **Bot Token** và **Chat ID**
- Bật **Forum Topics** — chỉ định topic name cho máy chủ này
- Chỉnh **ngưỡng mất gói tin** (cảnh báo / nghiêm trọng)
- Điều chỉnh **delay**, **cooldown spam**, **rate limit**
- Nút **Test gửi Telegram** — kiểm tra kết nối ngay lập tức
- Nút **Lưu cấu hình** → service tự động reload

### Tab 🚀 Dịch vụ
- Badge trạng thái: `✅ Đang chạy` / `🔴 Không chạy`
- Nút **Start / Stop / Restart / Reload**
- **Log viewer** — tự làm mới mỗi 5 giây
- Chọn số dòng hiển thị: 20 / 50 / 100 / 200

---

## ⚙️ Cấu hình tham chiếu

File: `/usr/local/etc/pf_notify/config.json`

| Tham số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `telegram_token` | `""` | Bot Token từ @BotFather |
| `telegram_chat_id` | `""` | Chat ID nhóm/kênh nhận thông báo |
| `delay_seconds` | `3` | Trì hoãn N giây trước khi gửi (lọc flap thoáng qua) |
| `spam_cooldown` | `300` | Không gửi lại cùng trạng thái trong N giây (5 phút) |
| `high_loss_threshold` | `20` | Ngưỡng % mất gói tin → cảnh báo mức cao |
| `critical_loss_threshold` | `80` | Ngưỡng % mất gói tin → nghiêm trọng (xem như offline) |
| `gui_fail_threshold` | `3` | Số lần sai mật khẩu liên tiếp → cảnh báo bảo mật |
| `retry_count` | `3` | Số lần thử lại khi Telegram API lỗi |
| `retry_backoff` | `2` | Giây chờ giữa các lần retry (nhân đôi theo cấp số nhân) |
| `rate_limit_per_min` | `10` | Tối đa N tin/phút. `0` = không giới hạn |
| `use_topics` | `false` | Bật tính năng Forum Topics (yêu cầu Supergroup) |
| `topic_name` | `""` | Tên topic trong nhóm Telegram (ví dụ: `homehoag`) |

---

## 🗂️ Forum Topics — Đa máy chủ

Tính năng **Forum Topics** cho phép nhiều máy chủ pfSense cùng gửi vào **một nhóm Telegram duy nhất**, mỗi máy chủ có **topic riêng biệt** để dễ phân loại.

### Yêu cầu
- Nhóm Telegram phải là **Supergroup** với **Topics** được bật (`Group Settings › Topics`)
- Bot phải có quyền **Admin** trong nhóm: `Manage Topics` ✅ (không cần `Pin Messages`)

### Cấu hình

Trong `config.json` của **từng pfSense**:
```json
{
  "telegram_chat_id": "-1001234567890",
  "use_topics": true,
  "topic_name": "homehoag"
}
```

Khi khởi động lần đầu, script tự động:
1. Tìm kiếm topic có tên `homehoag` trong nhóm
2. Nếu chưa có → tạo topic mới tự động
3. Lưu `thread_id` vào state file, tái sử dụng cho các lần sau

### Kịch bản triển khai đa máy chủ

| Máy chủ pfSense | `topic_name` | Topic trong nhóm Telegram |
|---|---|---|
| `homehoag.vnc.id.vn` | `homehoag` | `#homehoag` |
| `netphamgiang.vnc.id.vn` | `netphamgiang` | `#netphamgiang` |
| `vpnserver.domain.vn` | `vpnserver` | `#vpnserver` |

Tất cả đều dùng cùng `telegram_chat_id` → thông báo phân loại rõ ràng trong từng topic.

---

## 🔧 Xử lý sự cố

### Daemon không khởi động

```sh
# Kiểm tra Python
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
# Gửi tin test
/usr/local/bin/python3.11 /usr/local/sbin/pf_notify.py test --single --config /usr/local/etc/pf_notify/config.json

# Xem nội dung config
cat /usr/local/etc/pf_notify/config.json

# Kiểm tra Bot Token còn hợp lệ
curl "https://api.telegram.org/bot<TOKEN>/getMe"
```

### Tin nhắn vào General thay vì topic

Xảy ra khi `message_thread_id` không được truyền đúng. Kiểm tra:
```sh
# Xóa state cũ để script tạo lại topic
rm -f /var/db/pf_notify/state.json

# Restart service
/usr/local/etc/rc.d/pf_notify.sh restart

# Xem log khởi tạo topic
tail -20 /var/log/pf_notify.log
```

### PID file còn nhưng process không chạy

```sh
rm -f /var/run/pf_notify.pid
/usr/local/etc/rc.d/pf_notify.sh start
```

### Cảnh báo spam quá nhiều

Tăng `spam_cooldown` trong config (mặc định 300s = 5 phút):
```json
"spam_cooldown": 600
```
Sau đó: `/usr/local/etc/rc.d/pf_notify.sh reload`

---

## ⚠️ Sau khi nâng cấp pfSense

Các thư mục `/usr/local/sbin/`, `/usr/local/etc/`, `/usr/local/www/` **tồn tại qua nâng cấp** pfSense (khác với `/root/` có thể bị xóa).

Sau mỗi lần nâng cấp pfSense, kiểm tra lại:
```sh
/usr/local/etc/rc.d/pf_notify.sh status
tail -5 /var/log/pf_notify.log
```

---

## 📁 Cấu trúc thư mục

```
Noti_telegram/
├── package/                          ← Package installer (cách cài được khuyến nghị)
│   ├── install.sh                    ← Installer tự động
│   ├── uninstall.sh                  ← Gỡ cài đặt
│   └── files/                        ← Tất cả files triển khai
│
├── upload_to__usr_local_sbin/
│   └── pf_notify.py                  ← Script Python chính
│
├── upload_to__usr_local_etc_rc.d/
│   └── pf_notify.sh                  ← Service script (tự chạy khi boot)
│
├── upload_to__usr_local_etc_pf_notify/
│   └── config.json.example           ← Mẫu cấu hình
│
├── upload_to__usr_local_www/
│   ├── pf_notify.php                 ← Trang quản lý GUI
│   └── pf_notify_api.php             ← API backend cho GUI
│
├── INSTALL.md                        ← Hướng dẫn cài đặt chi tiết
└── README.md                         ← File này
```

**Vị trí file trên pfSense sau khi cài:**

| File | Mục đích |
|------|---------|
| `/usr/local/sbin/pf_notify.py` | Script Python chính (daemon) |
| `/usr/local/etc/rc.d/pf_notify.sh` | Service script — tự khởi động khi boot |
| `/usr/local/etc/pf_notify/config.json` | File cấu hình (token, chat_id, ngưỡng…) |
| `/usr/local/www/pf_notify.php` | Trang quản lý GUI |
| `/usr/local/www/pf_notify_api.php` | API backend cho GUI |
| `/var/db/pf_notify/state.json` | Trạng thái gateway + topic cache (tự tạo) |
| `/var/log/pf_notify.log` | File log hoạt động |
| `/var/run/pf_notify.pid` | PID file của daemon wrapper |

---

## 📊 File log pfSense được giám sát

| File | Sự kiện theo dõi |
|------|-----------------|
| `/var/log/gateways.log` | Gateway ONLINE/OFFLINE, mất gói tin, RTT (dpinger) |
| `/var/log/system.log` | Khởi động/tắt máy, đăng nhập GUI pfSense |
| `/var/log/ppp.log` | PPPoE WAN kết nối / ngắt kết nối |

---

*Xây dựng cho hạ tầng mạng pfSense Việt Nam 🇻🇳*
