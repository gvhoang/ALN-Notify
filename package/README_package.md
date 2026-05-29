# PF Notify — Package Mini

Đóng gói tất cả files cần thiết để cài đặt PF Notify trên pfSense chỉ bằng 1 lệnh.

## Cấu trúc

```
package/
├── install.sh          ← Cài đặt tất cả
├── uninstall.sh        ← Gỡ cài đặt
└── files/
    ├── pf_notify.py            → /usr/local/sbin/
    ├── pf_notify.sh            → /usr/local/etc/rc.d/
    ├── pf_notify.php           → /usr/local/www/
    ├── pf_notify_api.php       → /usr/local/www/
    └── config.json.example     → /usr/local/etc/pf_notify/config.json
```

## Cài đặt (1 lệnh)

```bash
# 1. Tạo thư mục đích trên pfSense rồi copy nội dung vào
ssh admin@192.168.0.1 "mkdir -p /tmp/pf_notify_pkg"
scp -r package/* admin@192.168.0.1:/tmp/pf_notify_pkg/

# 2. SSH vào pfSense và chạy installer
ssh admin@192.168.0.1
sh /tmp/pf_notify_pkg/install.sh
```

### Tùy chọn: cài xong cấu hình token trước khi start

```bash
sh /tmp/pf_notify_pkg/install.sh --no-start
# → Vào GUI điền Bot Token + Chat ID → Save
# → Services > PF Notify → Start
```

Installer tự động:
- ✅ Backup code cũ vào `/var/backups/pf_notify/YYYYmmdd-HHMMSS/`
- ✅ Copy tất cả files vào đúng vị trí
- ✅ Set quyền (chmod 600 config, 755 scripts)
- ✅ Tạo config từ template nếu chưa có
- ✅ Đăng ký menu **Services > PF Notify** vào pfSense
- ✅ Doctor check: Python / files / config / token
- ✅ Khởi động service (hoặc skip với `--no-start`)

## Sau cài đặt

Mở GUI: **Services > PF Notify** hoặc `https://<pfsense>/pf_notify.php`

Điền Bot Token + Chat ID → **Lưu cấu hình** → **Test gửi Telegram**.

## Nâng cấp

Chạy lại `install.sh` — config được giữ nguyên, chỉ update code.  
Bản cũ được backup tự động trước khi overwrite.

## Gỡ cài đặt

```bash
sh /tmp/pf_notify_pkg/uninstall.sh
```