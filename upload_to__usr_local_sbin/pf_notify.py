#!/usr/bin/env python3
"""
pf_notify — pfSense Gateway Telegram Notifier v2
=================================================
Cài đặt:
  /usr/local/sbin/pf_notify.py      ← script này
  /usr/local/etc/pf_notify/config.json  ← config (token, chat_id, ...)
  /var/db/pf_notify/state.json      ← trạng thái gateway (tự tạo)

Chế độ chạy:
  python3.11 /usr/local/sbin/pf_notify.py watch     # daemon
  python3.11 /usr/local/sbin/pf_notify.py test      # gửi test
  python3.11 /usr/local/sbin/pf_notify.py send ...  # gửi 1 sự kiện
"""

import re
import json
import time
import sys
import os
import signal
import socket
import argparse
import threading
import queue
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Defaults — bị ghi đè bởi /usr/local/etc/pf_notify/config.json
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_FILE = "/usr/local/etc/pf_notify/config.json"

DEFAULT_CFG = {
    "telegram_token":            "",
    "telegram_chat_id":          "",
    "log_files": [
        "/var/log/gateways.log",
        "/var/log/system.log",
        "/var/log/ppp.log",
    ],
    "state_file":                "/var/db/pf_notify/state.json",
    "delay_seconds":             3,
    "spam_cooldown":             300,
    "high_loss_threshold":       20,
    "critical_loss_threshold":   80,
    "gui_fail_threshold":        3,
    "retry_count":               3,
    "retry_backoff":             2,
    "rate_limit_per_min":        10,
}


def load_config(path=CONFIG_FILE):
    """Đọc config từ file JSON, merge với DEFAULT_CFG."""
    cfg = dict(DEFAULT_CFG)
    try:
        with open(path, "r") as f:
            user = json.load(f)
        cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
    except FileNotFoundError:
        _err("Config không tìm thấy: %s — dùng mặc định" % path)
    except Exception as e:
        _err("Lỗi đọc config: %s" % e)
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# ISP / WAN classification
# ─────────────────────────────────────────────────────────────────────────────

ISP_MAP = {
    "VIETTEL":  {"icon": "🔴", "label": "Viettel"},
    "FPT":      {"icon": "🟠", "label": "FPT"},
    "VNPT":     {"icon": "🟡", "label": "VNPT"},
    "SCTV":     {"icon": "🟣", "label": "SCTV"},
    "CMC":      {"icon": "🔵", "label": "CMC"},
    "VDTS":     {"icon": "⚪", "label": "VDTS"},
    "MOBIFONE": {"icon": "🟤", "label": "MobiFone"},
}

SUBSTATUS_LABELS = {
    "loss":      "📉 Vượt ngưỡng mất gói tin",
    "delay":     "⏳ Vượt ngưỡng độ trễ",
    "highdelay": "⏳ Phát hiện độ trễ cao",
    "highloss":  "📉 Phát hiện mất gói tin cao",
    "none":      "",
    "":          "",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_pfsense_fqdn():
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse("/cf/conf/config.xml")
        root = tree.getroot()
        h = root.findtext("system/hostname", "").strip()
        d = root.findtext("system/domain", "").strip()
        if h and d:
            return "%s.%s" % (h, d)
        if h:
            return h
    except Exception:
        pass
    return socket.getfqdn()


def detect_isp(name):
    upper = name.upper()
    for key, info in ISP_MAP.items():
        if key in upper:
            return info
    return {"icon": "🌐", "label": "Không xác định"}


def load_state(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        _err("Không thể lưu trạng thái: %s" % e)


def should_send(state, gateway, new_status, cooldown):
    gw = state.get(gateway, {})
    if gw.get("status") != new_status:
        return True
    return (time.time() - gw.get("last_sent", 0)) >= cooldown


def _err(msg):
    print("[ERR] %s" % msg, file=sys.stderr, flush=True)


def _log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print("[%s] %s" % (ts, msg), flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter
# ─────────────────────────────────────────────────────────────────────────────

_rate_sent_times = []
_rate_lock = threading.Lock()


def _rate_allowed(limit_per_min):
    """Trả về True nếu được phép gửi; False nếu đã quá giới hạn."""
    if limit_per_min <= 0:
        return True
    now = time.time()
    with _rate_lock:
        _rate_sent_times[:] = [t for t in _rate_sent_times if now - t < 60]
        if len(_rate_sent_times) >= limit_per_min:
            return False
        _rate_sent_times.append(now)
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Telegram sender — retry + exponential backoff
# ─────────────────────────────────────────────────────────────────────────────

def send_telegram(token, chat_id, text, retry=3, backoff=2, rate_limit=10):
    """Gửi HTML message qua Telegram Bot API. Có retry + backoff + rate limit."""
    if not _rate_allowed(rate_limit):
        _err("⏸️  Rate limit: tạm dừng gửi Telegram")
        return False

    url = "https://api.telegram.org/bot%s/sendMessage" % token
    payload = urllib.parse.urlencode({
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    for attempt in range(retry + 1):
        try:
            req = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                return result.get("ok", False)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", backoff * (attempt + 1)))
                _err("Telegram 429 Too Many Requests — chờ %ds" % wait)
                time.sleep(wait)
            else:
                _err("Telegram HTTP %d: %s" % (e.code, body))
                if attempt < retry:
                    time.sleep(backoff * (2 ** attempt))
        except Exception as e:
            _err("Gửi Telegram thất bại (lần %d/%d): %s" % (attempt + 1, retry + 1, e))
            if attempt < retry:
                time.sleep(backoff * (2 ** attempt))
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Message formatters
# ─────────────────────────────────────────────────────────────────────────────

def format_message(gateway, status, monitor_ip="", gateway_ip="",
                   rtt_avg="", rtt_stddev="", loss_pct=0.0,
                   substatus="", group="", action="", pfsense="",
                   high_loss_threshold=20):
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    if status == "offline":
        header = "🔴 <b>GATEWAY MẤT KẾT NỐI</b>"
    elif status == "online":
        header = "🟢 <b>GATEWAY KẾT NỐI TRỞ LẠI</b>"
    else:
        header = "⚠️ <b>CẢNH BÁO GATEWAY</b>"

    lines = [header, ""]
    if pfsense:
        lines.append("🖥️ Máy chủ: <code>%s</code>" % pfsense)
        lines.append("")

    lines.append("🌐 WAN: <code>%s</code>" % gateway)
    if monitor_ip:
        lines.append("📡 IP Monitor: <code>%s</code>" % monitor_ip)
    if gateway_ip:
        lines.append("🔗 IP Gateway: <code>%s</code>" % gateway_ip)
    lines.append("")

    if loss_pct >= 100:
        lines.append("⚠️ Mất gói tin: <b>100%</b>")
        lines.append("⚠️ Hết thời gian chờ RTT")
    else:
        if loss_pct > 0:
            icon = "⚠️" if loss_pct >= high_loss_threshold else "📊"
            lines.append("%s Mất gói tin: <b>%.0f%%</b>" % (icon, loss_pct))
        if rtt_avg and rtt_avg not in ("~", "0.000ms", "0ms", ""):
            lines.append("⏱️ RTT: %s" % rtt_avg)
            if rtt_stddev and rtt_stddev not in ("~", "0.000ms", ""):
                lines[-1] += " ± %s" % rtt_stddev
        elif status == "offline":
            lines.append("⚠️ Hết thời gian chờ RTT")

    sub_label = SUBSTATUS_LABELS.get(substatus.lower() if substatus else "", "")
    if not sub_label and substatus and substatus.lower() not in ("none", ""):
        sub_label = "ℹ️ %s" % substatus
    if sub_label:
        lines.append(sub_label)

    lines.append("")
    if group:
        if status == "offline" or any(w in action.lower() for w in ("remov", "omit")):
            lines.append("🛣️ Xóa khỏi nhóm định tuyến:")
        else:
            lines.append("🛣️ Thêm vào nhóm định tuyến:")
        lines.append("<code>%s</code>" % group)
        lines.append("")

    lines.append("⏰ %s" % now)
    return "\n".join(lines)


def format_dyndns_message(hostname, new_ip, pfsense=""):
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    lines = ["🔄 <b>CẬP NHẬT IP ĐỘNG</b>", ""]
    if pfsense:
        lines.append("🖥️ Máy chủ: <code>%s</code>" % pfsense)
        lines.append("")
    lines.append("🌐 Hostname: <code>%s</code>" % hostname)
    lines.append("📍 IP mới: <code>%s</code>" % new_ip)
    lines.append("")
    lines.append("⏰ %s" % now)
    return "\n".join(lines)


def format_system_message(event, pfsense=""):
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    if event == "bootup":
        header = "🟢 <b>HỆ THỐNG KHỞI ĐỘNG</b>"
        detail = "✅ pfSense đã khởi động hoàn tất"
    elif event == "shutdown":
        header = "🔴 <b>HỆ THỐNG TẮT MÁY</b>"
        detail = "⚠️ pfSense đang thực hiện tắt máy"
    else:
        return None
    lines = [header, ""]
    if pfsense:
        lines.append("🔧 pfSense: <code>%s</code>" % pfsense)
        lines.append("")
    lines.append(detail)
    lines.append("")
    lines.append("⏰ %s" % now)
    return "\n".join(lines)


def format_ppp_message(event, interface="", remote_ip="", reason="", pfsense=""):
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    if event == "connect":
        header = "🟢 <b>WAN PPPoE KẾT NỐI</b>"
        detail = "✅ Đường truyền PPPoE đã kết nối thành công"
    elif event == "remote_ip":
        header = "🟢 <b>WAN PPPoE CÓ IP</b>"
        detail = "📍 IP WAN đã được cấp: <code>%s</code>" % remote_ip
    elif event == "disconnect":
        header = "🔴 <b>WAN PPPoE MẤT KẾT NỐI</b>"
        detail = "⚠️ Nguyên nhân: <code>%s</code>" % reason
    elif event == "auth_fail":
        header = "🔴 <b>WAN PPPoE XÁC THỰC THẤT BẠI</b>"
        detail = "🔑 %s — Kiểm tra lại user/password ISP!" % reason
    else:
        return None
    lines = [header, ""]
    if pfsense:
        lines.append("🖥️ Máy chủ: <code>%s</code>" % pfsense)
        lines.append("")
    if interface:
        lines.append("🔌 Interface: <code>%s</code>" % interface)
    lines.append(detail)
    lines.append("")
    lines.append("⏰ %s" % now)
    return "\n".join(lines)


def format_auth_message(event, user="", src_ip="", count=1, pfsense=""):
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    if event in ("fail", "invalid"):
        if count >= 5:
            header = "🚨 <b>TẤN CÔNG BRUTE FORCE SSH</b>"
            detail = "🔴 Phát hiện <b>%d lần</b> đăng nhập thất bại!" % count
        else:
            header = "⚠️ <b>ĐĂNG NHẬP SSH THẤT BẠI</b>"
            detail = "❌ Đăng nhập không thành công"
    elif event == "fail_gui":
        if count >= 3:
            header = "🚨 <b>ĐĂNG NHẬP WEB THẤT BẠI NHIỀU LẦN</b>"
            detail = "❌ Sai mật khẩu <b>%d lần</b> trong 5 phút" % count
        else:
            header = "⚠️ <b>ĐĂNG NHẬP GIAO DIỆN WEB THẤT BẠI</b>"
            detail = "❌ Sai mật khẩu đăng nhập pfSense GUI"
    elif event == "ok":
        header = "🔑 <b>ĐĂNG NHẬP SSH THÀNH CÔNG</b>"
        detail = "✅ Phiên SSH đã được chấp nhận"
    else:
        return None
    lines = [header, ""]
    if pfsense:
        lines.append("🖥️ Máy chủ: <code>%s</code>" % pfsense)
        lines.append("")
    if user:
        lines.append("👤 Tài khoản: <code>%s</code>" % user)
    if src_ip:
        lines.append("🌍 IP: <code>%s</code>" % src_ip)
    lines.append(detail)
    lines.append("")
    lines.append("⏰ %s" % now)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Log parsers (regex)
# ─────────────────────────────────────────────────────────────────────────────

RE_ACTION = re.compile(
    r"MONITOR:\s+(\S+)\s+is\s+(available|unavailable)\s+now[,.]?\s*"
    r"(adding to|removing from)\s+routing group\s+(\S+)",
    re.IGNORECASE
)
RE_ACTION_OMIT = re.compile(
    r"MONITOR:\s+(\S+)\s+has packet loss,\s+omitting from\s+routing group\s+(\S+)",
    re.IGNORECASE
)
RE_STATS = re.compile(
    r"(\d{1,3}(?:\.\d{1,3}){3})"
    r"\|(\d{1,3}(?:\.\d{1,3}){3})"
    r"\|(\S+?)"
    r"\|([^|]*)"
    r"\|([^|]*)"
    r"\|(\d+\.?\d*)%"
    r"\|(online|offline|down)"
    r"\|([^|\s]*)"
)
RE_DOWN_SIMPLE = re.compile(r"MONITOR:\s+(\S+)\s+is\s+down", re.IGNORECASE)
RE_UP_SIMPLE   = re.compile(r"MONITOR:\s+(\S+)\s+is\s+up",   re.IGNORECASE)
RE_DYNDNS      = re.compile(
    r"phpDynDNS: updating cache file[^']*'([^']+)'\d+\.cache:\s*([\d.]+)",
    re.IGNORECASE
)
RE_BOOTUP   = re.compile(r"Bootup complete",      re.IGNORECASE)
RE_SHUTDOWN = re.compile(r"pfSense will shutdown", re.IGNORECASE)
RE_SYSLOG_HOST = re.compile(r"^\w{3}\s+\d+\s+[\d:]+\s+(\S+)\s+")

RE_PPP_CONNECT    = re.compile(r"pppd\[\d+\][^:]*:\s+Connect:\s+(\S+)\s+<-->",  re.IGNORECASE)
RE_PPP_REMOTE_IP  = re.compile(r"pppd\[\d+\][^:]*:\s+remote IP address\s+([\d.]+)", re.IGNORECASE)
RE_PPP_DISCONNECT = re.compile(
    r"pppd\[\d+\][^:]*:\s+(Connection terminated|LCP terminated|"
    r"Hangup \(SIGHUP\)|SIGTERM received|Modem hangup)", re.IGNORECASE
)
RE_PPP_AUTH_FAIL = re.compile(
    r"pppd\[\d+\][^:]*:\s+(PAP authentication failed|CHAP authentication failed|"
    r"Authentication failed)", re.IGNORECASE
)
RE_AUTH_FAIL_GUI = re.compile(
    r"php(?:-fpm)?\[\d+\][^:]*:\s+.*(?:authentication error|Wrong password|login failed)"
    r".*user[:\s]+['\"]?([^\s'\"]+)['\"]?.*from[:\s]+([0-9a-fA-F:.]+)",
    re.IGNORECASE
)
RE_AUTH_FAIL_GUI_NOIP = re.compile(
    r"php(?:-fpm)?\[\d+\][^:]*:\s+.*(?:authentication error|Wrong password|login failed)"
    r".*user[:\s]+['\"]?([^\s'\"]+)['\"]?",
    re.IGNORECASE
)


def parse_line(line):
    host_m  = RE_SYSLOG_HOST.match(line)
    pfsense = host_m.group(1) if host_m else ""

    m = RE_ACTION.search(line)
    if m:
        return {"type": "action", "gateway": m.group(1),
                "status": "online" if m.group(2).lower() == "available" else "offline",
                "action": m.group(3), "group": m.group(4), "pfsense": pfsense}

    m = RE_ACTION_OMIT.search(line)
    if m:
        return {"type": "action", "gateway": m.group(1), "status": "offline",
                "action": "omitting from", "group": m.group(2), "pfsense": pfsense}

    m = RE_STATS.search(line)
    if m:
        raw_status = m.group(7).lower()
        return {"type": "stats", "gateway_ip": m.group(1), "monitor_ip": m.group(2),
                "gateway": m.group(3), "rtt_avg": m.group(4).strip(),
                "rtt_stddev": m.group(5).strip(), "loss_pct": float(m.group(6)),
                "status": "offline" if raw_status == "down" else raw_status,
                "substatus": m.group(8).strip(), "pfsense": pfsense}

    m = RE_DOWN_SIMPLE.search(line)
    if m:
        return {"type": "action", "gateway": m.group(1), "status": "offline",
                "action": "removing from", "group": "", "pfsense": pfsense}

    m = RE_UP_SIMPLE.search(line)
    if m:
        return {"type": "action", "gateway": m.group(1), "status": "online",
                "action": "adding to", "group": "", "pfsense": pfsense}

    m = RE_DYNDNS.search(line)
    if m:
        return {"type": "dyndns", "hostname": m.group(1), "new_ip": m.group(2),
                "pfsense": pfsense}

    if RE_BOOTUP.search(line):
        return {"type": "system", "event": "bootup", "pfsense": pfsense}
    if RE_SHUTDOWN.search(line):
        return {"type": "system", "event": "shutdown", "pfsense": pfsense}

    m = RE_PPP_CONNECT.search(line)
    if m:
        return {"type": "ppp", "event": "connect", "interface": m.group(1),
                "pfsense": pfsense}
    m = RE_PPP_REMOTE_IP.search(line)
    if m:
        return {"type": "ppp", "event": "remote_ip", "remote_ip": m.group(1),
                "pfsense": pfsense}
    m = RE_PPP_DISCONNECT.search(line)
    if m:
        return {"type": "ppp", "event": "disconnect", "reason": m.group(1),
                "pfsense": pfsense}
    m = RE_PPP_AUTH_FAIL.search(line)
    if m:
        return {"type": "ppp", "event": "auth_fail", "reason": m.group(1),
                "pfsense": pfsense}

    m = RE_AUTH_FAIL_GUI.search(line)
    if m:
        return {"type": "auth", "event": "fail_gui",
                "user": m.group(1), "src_ip": m.group(2), "pfsense": pfsense}
    m = RE_AUTH_FAIL_GUI_NOIP.search(line)
    if m:
        return {"type": "auth", "event": "fail_gui",
                "user": m.group(1), "src_ip": "", "pfsense": pfsense}

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Pending event buffer
# ─────────────────────────────────────────────────────────────────────────────

class PendingBuffer:
    def __init__(self, delay):
        self.delay = delay   # anti-flap: chờ tối thiểu trước khi flush mỗi gateway
        self._buf  = {}
        self._ts   = {}

    def add(self, event):
        gw = event.get("gateway")
        if not gw:
            return
        if gw not in self._buf:
            self._buf[gw] = dict(event)
            self._ts[gw]  = time.time()
        else:
            for k, v in event.items():
                if v not in (None, "", 0, 0.0):
                    self._buf[gw][k] = v

    def flush_ready(self):
        now   = time.time()
        ready = []
        for gw in list(self._ts):
            if now - self._ts[gw] >= self.delay:
                ready.append(self._buf.pop(gw))
                del self._ts[gw]
        return ready


# ─────────────────────────────────────────────────────────────────────────────
# Core processing
# ─────────────────────────────────────────────────────────────────────────────

def process_event(event, state, cfg):
    gw     = event.get("gateway", "")
    status = event.get("status", "")
    if not gw or not status:
        return

    loss = float(event.get("loss_pct", 0))

    # Xác định effective_status TRƯỚC khi kiểm tra spam/cooldown,
    # để should_send so sánh đúng với trạng thái thực sự sẽ được gửi.
    effective_status = status
    if status == "online" and loss >= cfg["critical_loss_threshold"]:
        effective_status = "offline"
        _log("[%s] 📉 mất gói nghiêm trọng %.0f%% → leo thang MẤT KẾT NỐI" % (gw, loss))

    if not should_send(state, gw, effective_status, cfg["spam_cooldown"]):
        _log("[%s] ⏭️  chống spam - bỏ qua (%s)" % (gw, effective_status))
        return

    msg = format_message(
        gateway     = gw,
        status      = effective_status,
        monitor_ip  = event.get("monitor_ip", ""),
        gateway_ip  = event.get("gateway_ip", ""),
        rtt_avg     = event.get("rtt_avg", ""),
        rtt_stddev  = event.get("rtt_stddev", ""),
        loss_pct    = loss,
        substatus   = event.get("substatus", ""),
        group       = event.get("group", ""),
        action      = event.get("action", ""),
        pfsense     = event.get("pfsense", ""),
        high_loss_threshold = cfg["high_loss_threshold"],
    )

    ok = send_telegram(
        cfg["telegram_token"], cfg["telegram_chat_id"], msg,
        retry=cfg["retry_count"], backoff=cfg["retry_backoff"],
        rate_limit=cfg["rate_limit_per_min"]
    )
    if ok:
        state.setdefault(gw, {})
        # Lưu effective_status (không phải status gốc) để cooldown/should_send
        # phản ánh đúng trạng thái đã gửi — tránh suppress event online thật sau này.
        state[gw]["status"]    = effective_status
        state[gw]["last_sent"] = time.time()
        save_state(cfg["state_file"], state)
        _log("[%s] ✅ đã gửi %s (mất gói=%.0f%%)" % (gw, effective_status, loss))
    else:
        _log("[%s] ❌ gửi thất bại" % gw)


def process_events(events, state, cfg):
    """Gửi từng GW event riêng biệt (không gộp batch)."""
    for ev in events:
        process_event(ev, state, cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Watch mode — multi-file log tailer
# ─────────────────────────────────────────────────────────────────────────────

_WATCH_KEYS = (
    "MONITOR:", "|online|", "|offline|", "|down|",
    "DynDNS updated", "phpDynDNS", "Bootup complete", "pfSense will shutdown",
    "pppd[", "Connect:", "Connection terminated", "LCP terminated",
    "PAP authentication failed", "CHAP authentication failed",
    "authentication error",
)

# SIGHUP flag — set by signal handler → reload config
_reload_flag = threading.Event()


def _sighup_handler(sig, frame):
    _reload_flag.set()


def _tail_worker(log_path, out_queue):
    try:
        fh = open(log_path, "r", encoding="utf-8", errors="replace")
    except OSError:
        _log("[%s] ⚠️  File không tồn tại — bỏ qua" % log_path)
        return

    fh.seek(0, 2)
    inode = os.fstat(fh.fileno()).st_ino
    _log("[%s] 👀 Bắt đầu theo dõi" % log_path)

    while True:
        try:
            cur_inode = os.stat(log_path).st_ino
        except OSError:
            cur_inode = inode

        if cur_inode != inode:
            fh.close()
            try:
                fh    = open(log_path, "r", encoding="utf-8", errors="replace")
                inode = os.fstat(fh.fileno()).st_ino
                _log("[%s] 🔄 Log xoay vòng — đã mở lại" % log_path)
            except OSError:
                time.sleep(2)
                continue

        for line in fh:
            line = line.rstrip("\n\r")
            if not any(k in line for k in _WATCH_KEYS):
                continue
            event = parse_line(line)
            if event:
                out_queue.put(event)

        time.sleep(0.3)


def watch_log(cfg):
    """Daemon chính: theo dõi log files, gửi Telegram khi có sự kiện."""
    signal.signal(signal.SIGHUP, _sighup_handler)

    log_files = cfg.get("log_files", [])
    state     = load_state(cfg["state_file"])
    buf  = PendingBuffer(cfg["delay_seconds"])
    ev_queue  = queue.Queue()
    local_fqdn = get_pfsense_fqdn()
    gui_fail_tracker = {}

    def _print_startup(c):
        _log("🖥️  Máy chủ: %s" % local_fqdn)
        _log("📡 Telegram chat: %s" % c["telegram_chat_id"])
        _log("⏳ Trì hoãn cảnh báo: %ds | 🔕 Chặn spam: %ds | 🔁 Retry: %d" % (
            c["delay_seconds"], c["spam_cooldown"], c["retry_count"]))
        _log("📊 Rate limit: %d tin/phút" % c["rate_limit_per_min"])
        _log("📂 Theo dõi %d file log:" % len(log_files))
        for lf in log_files:
            _log("   • %s" % lf)

    _print_startup(cfg)

    for lf in log_files:
        t = threading.Thread(target=_tail_worker, args=(lf, ev_queue), daemon=True)
        t.start()

    try:
        while True:
            # Kiểm tra SIGHUP — reload config
            if _reload_flag.is_set():
                _reload_flag.clear()
                new_cfg = load_config()
                cfg.update(new_cfg)
                buf.delay = cfg["delay_seconds"]
                _log("🔄 [SIGHUP] Đã reload config")
                _print_startup(cfg)

            while not ev_queue.empty():
                try:
                    event = ev_queue.get_nowait()
                except queue.Empty:
                    break

                etype = event.get("type")
                ps    = event.get("pfsense", "")

                if etype in ("action", "stats"):
                    _log("[GW] %s → %s" % (event.get("gateway"), event.get("status")))
                    buf.add(event)

                elif etype == "dyndns":
                    msg = format_dyndns_message(event["hostname"], event["new_ip"], pfsense=ps)
                    ok  = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg,
                                        retry=cfg["retry_count"], backoff=cfg["retry_backoff"],
                                        rate_limit=cfg["rate_limit_per_min"])
                    _log("[DynDNS] %s %s → %s" % ("✅" if ok else "❌",
                                                    event["hostname"], event["new_ip"]))

                elif etype == "system":
                    msg = format_system_message(event["event"], ps)
                    if msg:
                        ok    = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg,
                                              retry=cfg["retry_count"], backoff=cfg["retry_backoff"],
                                              rate_limit=cfg["rate_limit_per_min"])
                        label = "🟢 Khởi động" if event["event"] == "bootup" else "🔴 Tắt máy"
                        _log("[HỆ THỐNG] %s %s" % (label, "✅" if ok else "❌"))

                elif etype == "ppp":
                    ev = event["event"]
                    _log("[PPP] sự kiện: %s" % ev)
                    if ev == "remote_ip":
                        continue
                    msg = format_ppp_message(event=ev, interface=event.get("interface", ""),
                                             remote_ip=event.get("remote_ip", ""),
                                             reason=event.get("reason", ""), pfsense=ps)
                    if msg:
                        ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg,
                                           retry=cfg["retry_count"], backoff=cfg["retry_backoff"],
                                           rate_limit=cfg["rate_limit_per_min"])
                        _log("[PPP] %s gửi %s" % ("✅" if ok else "❌", ev))

                elif etype == "auth":
                    ev     = event["event"]
                    src_ip = event.get("src_ip", "")
                    user   = event.get("user", "")
                    threshold = cfg.get("gui_fail_threshold", 3)

                    if ev == "fail_gui":
                        key   = "%s@%s" % (user, ps)
                        now_t = time.time()
                        gui_fail_tracker.setdefault(key, [])
                        gui_fail_tracker[key] = [
                            t for t in gui_fail_tracker[key] if now_t - t < 300
                        ]
                        gui_fail_tracker[key].append(now_t)
                        count = len(gui_fail_tracker[key])
                        if count >= threshold and (count == threshold or count % 5 == 0):
                            msg = format_auth_message(event=ev, user=user, src_ip=src_ip,
                                                      count=count, pfsense=ps)
                            if msg:
                                ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"],
                                                   msg, retry=cfg["retry_count"],
                                                   backoff=cfg["retry_backoff"],
                                                   rate_limit=cfg["rate_limit_per_min"])
                                _log("[AUTH] %s GUI fail x%d user=%s" % (
                                    "✅" if ok else "❌", count, user))
                        else:
                            _log("[AUTH] GUI fail x%d (chưa đủ %d) user=%s" % (
                                count, threshold, user))
                    else:
                        msg = format_auth_message(event=ev, user=user, src_ip=src_ip, pfsense=ps)
                        if msg:
                            ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg,
                                               retry=cfg["retry_count"], backoff=cfg["retry_backoff"],
                                               rate_limit=cfg["rate_limit_per_min"])
                            _log("[AUTH] %s %s" % ("✅" if ok else "❌", ev))

            # Flush gateway events (tách biệt từng gateway)
            ready = buf.flush_ready()
            if ready:
                process_events(ready, state, cfg)

            time.sleep(0.4)

    except KeyboardInterrupt:
        _log("⏹️  Đã dừng.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _collect_recent_events(cfg, max_lines=300, max_events=5):
    log_files = cfg.get("log_files", [])
    events = []
    for lf in log_files:
        try:
            with open(lf, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            for line in lines[-max_lines:]:
                line = line.rstrip("\n\r")
                if not any(k in line for k in _WATCH_KEYS):
                    continue
                ev = parse_line(line)
                if ev:
                    events.append(ev)
        except OSError:
            continue
    seen = {}
    for ev in events:
        key = (ev.get("type"), ev.get("gateway", ""), ev.get("status", ""),
               ev.get("event", ""), ev.get("src_ip", ""))
        seen[key] = ev
    return list(seen.values())[-max_events:]


def _format_event_to_msg(event, pfsense="", cfg=None):
    cfg = cfg or DEFAULT_CFG
    etype = event.get("type")
    if etype in ("action", "stats"):
        return format_message(
            gateway    = event.get("gateway", ""),
            status     = event.get("status", ""),
            monitor_ip = event.get("monitor_ip", ""),
            gateway_ip = event.get("gateway_ip", ""),
            rtt_avg    = event.get("rtt_avg", ""),
            rtt_stddev = event.get("rtt_stddev", ""),
            loss_pct   = float(event.get("loss_pct", 0)),
            substatus  = event.get("substatus", ""),
            group      = event.get("group", ""),
            action     = event.get("action", ""),
            pfsense    = pfsense,
            high_loss_threshold = cfg["high_loss_threshold"],
        )
    if etype == "dyndns":
        return format_dyndns_message(event.get("hostname", ""), event.get("new_ip", ""), pfsense)
    if etype == "system":
        return format_system_message(event.get("event", ""), pfsense)
    if etype == "ppp":
        return format_ppp_message(event=event.get("event", ""),
                                  interface=event.get("interface", ""),
                                  remote_ip=event.get("remote_ip", ""),
                                  reason=event.get("reason", ""), pfsense=pfsense)
    if etype == "auth":
        return format_auth_message(event=event.get("event", ""), user=event.get("user", ""),
                                   src_ip=event.get("src_ip", ""), count=event.get("count", 1),
                                   pfsense=pfsense)
    return None


def main():
    p = argparse.ArgumentParser(description="pf_notify — pfSense Telegram Notifier v2")
    sub = p.add_subparsers(dest="mode", metavar="MODE")
    sub.required = True

    # watch
    wp = sub.add_parser("watch", help="Daemon: theo dõi log files")
    wp.add_argument("--config", default=CONFIG_FILE, metavar="PATH",
                    help="Đường dẫn file config JSON")
    wp.add_argument("--logs",   default=None, nargs="+", metavar="PATH")
    wp.add_argument("--token",  default=None, metavar="TOKEN")
    wp.add_argument("--chat-id",default=None, metavar="ID", dest="chat_id")

    # send
    sp = sub.add_parser("send", help="Gửi 1 sự kiện trực tiếp")
    sp.add_argument("--config",   default=CONFIG_FILE, metavar="PATH")
    sp.add_argument("--gateway",  required=True)
    sp.add_argument("--status",   required=True, choices=["online", "offline"])
    sp.add_argument("--monitor",  default="", metavar="IP")
    sp.add_argument("--gw-ip",    default="", metavar="IP", dest="gw_ip")
    sp.add_argument("--rtt",      default="", metavar="VAL")
    sp.add_argument("--loss",     type=float, default=0.0)
    sp.add_argument("--substatus",default="")
    sp.add_argument("--group",    default="")
    sp.add_argument("--token",    default=None)
    sp.add_argument("--chat-id",  default=None, dest="chat_id")
    sp.add_argument("--no-delay", action="store_true")

    # test
    tp = sub.add_parser("test", help="Gửi thông báo test")
    tp.add_argument("--config",  default=CONFIG_FILE, metavar="PATH")
    tp.add_argument("--token",   default=None)
    tp.add_argument("--chat-id", default=None, dest="chat_id")
    tp.add_argument("--gateway", default="VIETTEL_TAYNINH")
    tp.add_argument("--status",  default="offline", choices=["online", "offline"])

    args = p.parse_args()

    cfg = load_config(args.config)
    if getattr(args, "token",   None): cfg["telegram_token"]   = args.token
    if getattr(args, "chat_id", None): cfg["telegram_chat_id"] = args.chat_id

    if args.mode == "watch":
        if getattr(args, "logs", None):
            cfg["log_files"] = args.logs
        watch_log(cfg)

    elif args.mode == "send":
        state = load_state(cfg["state_file"])
        if not args.no_delay and cfg["delay_seconds"] > 0:
            _log("⏳ Đợi %ds…" % cfg["delay_seconds"])
            time.sleep(cfg["delay_seconds"])
        event = {"gateway": args.gateway, "status": args.status,
                 "monitor_ip": args.monitor, "gateway_ip": args.gw_ip,
                 "rtt_avg": args.rtt, "loss_pct": args.loss,
                 "substatus": args.substatus, "group": args.group,
                 "action": "removing from" if args.status == "offline" else "adding to"}
        process_event(event, state, cfg)

    elif args.mode == "test":
        hostname = get_pfsense_fqdn()
        token    = cfg["telegram_token"]
        chat_id  = cfg["telegram_chat_id"]

        if not token or "YOUR_BOT_TOKEN" in token:
            print("⚠️  Chưa cài đặt telegram_token trong config!")
            return

        real_events = _collect_recent_events(cfg)
        if real_events:
            print("=" * 60)
            print("📋 Tìm thấy %d sự kiện thực tế:" % len(real_events))
            print("=" * 60)
            sent = 0
            for ev in real_events:
                ps  = ev.get("pfsense") or hostname
                msg = _format_event_to_msg(ev, ps, cfg)
                if not msg:
                    continue
                print(re.sub(r"<[^>]+>", "", msg).strip())
                print("-" * 40)
                ok = send_telegram(token, chat_id, msg)
                if ok:
                    sent += 1
                time.sleep(1)
            print("✅ Đã gửi %d tin nhắn" % sent if sent else "❌ Gửi thất bại")
            return

        _log("⚠️  Không đọc được log — gửi demo")
        msg = format_message(gateway="VIETTEL_TAYNINH", status="offline",
                             monitor_ip="10.123.234.2", gateway_ip="10.123.234.1",
                             rtt_avg="", loss_pct=100.0, substatus="loss",
                             group="FPT_st1", action="removing from", pfsense=hostname)
        ok = send_telegram(token, chat_id, msg)
        print("✅ Demo gửi thành công" if ok else "❌ Gửi thất bại")


if __name__ == "__main__":
    main()
