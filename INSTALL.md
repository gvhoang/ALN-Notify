# 📦 Hướng dẫn cài đặt pfSense Telegram Notifier

> Hệ thống cảnh báo chuyên nghiệp qua Telegram cho pfSense 2.7+  
> Shell mặc định pfSense là **tcsh** — xem lưu ý ở từng bước.

---

## Yêu cầu

| Thành phần | Phiên bản |
|-----------|-----------|
| pfSense | 2.7+ (FreeBSD) |
| Python | 3.11 (`/usr/local/bin/python3.11`) |
| Telegram Bot | Token + Chat ID |

Không cần cài thêm thư viện — script chỉ dùng thư viện chuẩn Python.

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

## Bước 2 — Copy file lên pfSense

**Từ Windows** (dùng WinSCP hoặc SCP):
```
SCP source : Noti_telegram\pfsense_gw_notify.py
SCP dest   : root@<IP_PFSENSE>:/root/pfsense_gw_notify.py
```

**Hoặc lệnh SCP:**
```bash
scp pfsense_gw_notify.py root@192.168.1.1:/root/
```

**Kiểm tra trên pfSense:**
```tcsh
ls -la /root/pfsense_gw_notify.py
```

---

## Bước 3 — Cấu hình Token & Chat ID

SSH vào pfSense, mở file bằng `vi`:
```tcsh
vi /root/pfsense_gw_notify.py
```

Tìm và sửa phần CONFIG (khoảng dòng 46-75):
```python
CONFIG = {
    "telegram_token":   "ĐẶT_TOKEN_CỦA_BẠN_VÀO_ĐÂY",
    "telegram_chat_id": "ĐẶT_CHAT_ID_VÀO_ĐÂY",
    ...
}
```

> **Mẹo vi:** Nhấn `i` để sửa, `Esc` để thoát edit, `:wq` để lưu.

---

## Bước 4 — Test thử

```tcsh
python3.11 /root/pfsense_gw_notify.py test
```

**Kết quả mong đợi:**
```
📋 Tìm thấy 5 sự kiện thực tế gần nhất từ log:
🟢 GATEWAY KẾT NỐI TRỞ LẠI
🖥️ Máy chủ: homehoag
...
✅ Đã gửi 5 tin nhắn thực tế thành công!
```

Nếu chưa có log thực, sẽ gửi 2 tin demo — bình thường.

---

## Bước 5 — Chạy daemon (nền)

> ⚠️ pfSense dùng **tcsh** — phải dùng `>&` thay `2>&1`

```tcsh
nohup python3.11 /root/pfsense_gw_notify.py watch >& /var/log/pf_notify.log & echo $! > /var/run/pf_notify.pid
```

**Kiểm tra đang chạy:**
```tcsh
ps aux | grep pfsense_gw_notify | grep -v grep
cat /var/run/pf_notify.pid
```

**Xem log realtime:**
```tcsh
tail -f /var/log/pf_notify.log
```

---

## Bước 6 — Tự động chạy khi reboot

Tạo startup script (file này dùng `/bin/sh` bên trong — OK):

```tcsh
cat > /usr/local/etc/rc.d/pf_notify.sh << 'EOF'
#!/bin/sh
case "$1" in
start)
    pkill -f pfsense_gw_notify.py 2>/dev/null
    sleep 1
    /usr/sbin/daemon -f -o /var/log/pf_notify.log -p /var/run/pf_notify.pid \
        /usr/local/bin/python3.11 /root/pfsense_gw_notify.py watch
    echo "pf_notify started (PID: $(cat /var/run/pf_notify.pid))"
    ;;
stop)
    pkill -f pfsense_gw_notify.py 2>/dev/null
    rm -f /var/run/pf_notify.pid
    echo "pf_notify stopped"
    ;;
status)
    if [ -f /var/run/pf_notify.pid ]; then
        PID=`cat /var/run/pf_notify.pid`
        if kill -0 $PID 2>/dev/null; then
            echo "pf_notify running (PID: $PID)"
        else
            echo "pf_notify: PID file tồn tại nhưng process đã chết"
        fi
    else
        echo "pf_notify not running"
    fi
    ;;
*)
    echo "Usage: $0 {start|stop|status}"
    ;;
esac
EOF

chmod +x /usr/local/etc/rc.d/pf_notify.sh
```

**Test start/stop:**
```tcsh
/usr/local/etc/rc.d/pf_notify.sh start
/usr/local/etc/rc.d/pf_notify.sh status
```

> Script đặt trong `/usr/local/etc/rc.d/` sẽ tự chạy khi pfSense boot lên.

---

## Bước 7 — Kiểm tra tự động chạy khi reboot

**Xác nhận điều kiện để tự chạy:**

```tcsh
# 1. File phải có quyền execute
ls -la /usr/local/etc/rc.d/pf_notify.sh
# Phải thấy: -rwxr-xr-x

# 2. File Python phải tồn tại đúng vị trí
ls -la /root/pfsense_gw_notify.py

# 3. Config hợp lệ
python3.11 /root/pfsense_gw_notify.py test 2>&1 | head -5
```

**Test thực tế — reboot và kiểm tra:**

```tcsh
reboot
```

Sau khi boot xong (~60 giây), đăng nhập SSH và kiểm tra:

```tcsh
# Daemon có đang chạy không?
/usr/local/etc/rc.d/pf_notify.sh status

# Log có ghi từ thời điểm boot không?
tail -20 /var/log/pf_notify.log
```

**Kết quả mong đợi:**
- `pf_notify running (PID: XXXXX)` ✅
- Log có dòng `👀 Bắt đầu theo dõi` với timestamp sau thời điểm reboot ✅

> **Cơ chế:** pfSense tự gọi tất cả `*.sh` trong `/usr/local/etc/rc.d/` với tham số `start` khi boot — không cần cấu hình thêm.

---

## Lệnh quản lý hàng ngày

```tcsh
# Dừng
/usr/local/etc/rc.d/pf_notify.sh stop

# Khởi động lại
/usr/local/etc/rc.d/pf_notify.sh stop
/usr/local/etc/rc.d/pf_notify.sh start

# Xem trạng thái
/usr/local/etc/rc.d/pf_notify.sh status

# Xem log gần nhất
tail -50 /var/log/pf_notify.log

# Xem log realtime
tail -f /var/log/pf_notify.log
```

---

## Cập nhật script mới

Khi có phiên bản mới, chỉ cần copy đè file và restart:

```tcsh
# Copy file mới lên (từ máy tính)
scp pfsense_gw_notify.py root@<IP_PFSENSE>:/root/

# Restart trên pfSense
/usr/local/etc/rc.d/pf_notify.sh stop
/usr/local/etc/rc.d/pf_notify.sh start
```

---

## ⚠️ Lưu ý sau nâng cấp pfSense

Sau mỗi lần **upgrade pfSense**, các file trong `/root/` có thể bị xóa.  
Kiểm tra và copy lại nếu cần:

```tcsh
ls /root/pfsense_gw_notify.py
/usr/local/etc/rc.d/pf_notify.sh status
```

---

## Cấu trúc file log pfSense được theo dõi

| File | Nội dung |
|------|----------|
| `/var/log/gateways.log` | Gateway ONLINE/OFFLINE (dpinger) |
| `/var/log/system.log` | Khởi động, tắt máy, DynDNS |
| `/var/log/ppp.log` | PPPoE WAN kết nối/ngắt |
| `/var/log/auth.log` | SSH đăng nhập, brute force |
