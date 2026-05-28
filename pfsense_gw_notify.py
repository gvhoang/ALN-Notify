#!/usr/bin/env python3
"""
pfSense Gateway Monitor - Professional Telegram Notifier
=========================================================
Features:
  - Parse pfSense dpinger/gateway log format
  - Beautiful Telegram HTML notifications
  - Anti-spam (cooldown per gateway)
  - 5s delay before alert (anti-flap)
  - Event merging (group stats + action into one message)
  - Multi-WAN with ISP auto-detection
  - Packet loss / high delay alerts
  - ONLINE / OFFLINE auto detect

Modes:
  python pfsense_gw_notify.py watch            # Daemon: tail log file
  python pfsense_gw_notify.py send --help      # Direct call from shell
  python pfsense_gw_notify.py test             # Send test notification

pfSense Integration:
  Place at /root/pfsense_gw_notify.py
  Run in background: python3 /root/pfsense_gw_notify.py watch &
  Or add to /etc/rc.d as a service

Author: Auto-generated for gvhoang/auto_ppoe_fpt
"""

import re
import json
import time
import sys
import os
import argparse
import threading
import queue
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — Edit before deploying
# ─────────────────────────────────────────────────────────────────────────────

CONFIG = {
    # Telegram Bot credentials
    "telegram_token":   "8506670215:AAHOR-zBY-4TbaSTCLztxumUH2y5PdfcDlg",
    "telegram_chat_id": "1015285796",

    # Log files to watch — pfSense separates events into dedicated files
    "log_files": [
        "/var/log/gateways.log",    # Gateway ONLINE/OFFLINE (dpinger) — ưu tiên 1
        "/var/log/system.log",      # Bootup, shutdown, DynDNS
        "/var/log/ppp.log",         # PPPoE WAN kết nối/ngắt kết nối
        "/var/log/auth.log",        # SSH brute force, đăng nhập trái phép
    ],

    # State file to persist gateway statuses across restarts
    "state_file": "/tmp/pf_gw_states.json",

    # Delay (seconds) before sending alert — absorbs brief flapping
    "delay_seconds": 5,

    # How long (seconds) to suppress duplicate same-status notifications
    "spam_cooldown": 300,

    # Packet loss % thresholds
    "high_loss_threshold":     20,   # ⚠️  warn even if "online"
    "critical_loss_threshold": 80,   # 🔴  treat as offline

    # Auth: group brute force alerts within this window (seconds)
    "auth_brute_window": 60,
    "auth_brute_threshold": 5,       # alerts per window before escalating
}

# ─────────────────────────────────────────────────────────────────────────────
# ISP / WAN classification — add your own gateway name patterns
# ─────────────────────────────────────────────────────────────────────────────

ISP_MAP = {
    "VIETTEL": {"icon": "🔴", "label": "Viettel"},
    "FPT":     {"icon": "🟠", "label": "FPT"},
    "VNPT":    {"icon": "🟡", "label": "VNPT"},
    "SCTV":    {"icon": "🟣", "label": "SCTV"},
    "CMC":     {"icon": "🔵", "label": "CMC"},
    "VDTS":    {"icon": "⚪", "label": "VDTS"},
    "MOBIFONE":{"icon": "🟤", "label": "MobiFone"},
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

def detect_isp(name):
    """Return ISP info dict for a gateway name, or a default."""
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
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        _err("Không thể lưu trạng thái: %s" % e)


def should_send(state, gateway, new_status, cooldown):
    """Anti-spam: True if we should send this notification."""
    gw = state.get(gateway, {})
    # Always send on status change
    if gw.get("status") != new_status:
        return True
    # Allow repeat after cooldown
    return (time.time() - gw.get("last_sent", 0)) >= cooldown


def _err(msg):
    print("[ERR] %s" % msg, file=sys.stderr)


def _log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print("[%s] %s" % (ts, msg))


# ─────────────────────────────────────────────────────────────────────────────
# Telegram sender  (stdlib only — no requests)
# ─────────────────────────────────────────────────────────────────────────────

def send_telegram(token, chat_id, text):
    """Send an HTML message via Telegram Bot API. Returns True on success."""
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    payload = urllib.parse.urlencode({
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            return result.get("ok", False)
    except urllib.error.HTTPError as e:
        _err("Telegram HTTP %d: %s" % (e.code, e.read().decode()))
    except Exception as e:
        _err("Gửi Telegram thất bại: %s" % e)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Message formatter
# ─────────────────────────────────────────────────────────────────────────────

def format_message(gateway, status, monitor_ip="", gateway_ip="",
                   rtt_avg="", rtt_stddev="", loss_pct=0.0,
                   substatus="", group="", action="", pfsense=""):
    """Build a beautiful Telegram HTML notification string."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    isp = detect_isp(gateway)

    # ── Header ──
    if status == "offline":
        header = "🔴 <b>GATEWAY MẤT KẾT NỐI</b>"
    elif status == "online":
        header = "🟢 <b>GATEWAY KẾT NỐI TRỞ LẠI</b>"
    else:
        header = "⚠️ <b>CẢNH BÁO GATEWAY</b>"

    lines = [header, ""]

    # ── Server identity ──
    if pfsense:
        lines.append("🖥️ Máy chủ: <code>%s</code>" % pfsense)
        lines.append("")

    # ── WAN identity ──
    lines.append("🌐 WAN: <code>%s</code>" % gateway)
    if monitor_ip:
        lines.append("📡 IP Monitor: <code>%s</code>" % monitor_ip)
    if gateway_ip:
        lines.append("🔗 IP Gateway: <code>%s</code>" % gateway_ip)

    lines.append("")

    # ── Loss & RTT ──
    if loss_pct >= 100:
        lines.append("⚠️ Mất gói tin: <b>100%</b>")
        lines.append("⚠️ Hết thời gian chờ RTT")
    else:
        if loss_pct > 0:
            icon = "⚠️" if loss_pct >= CONFIG["high_loss_threshold"] else "📊"
            lines.append("%s Mất gói tin: <b>%.0f%%</b>" % (icon, loss_pct))
        if rtt_avg and rtt_avg not in ("~", "0.000ms", "0ms", ""):
            lines.append("⏱️ RTT: %s" % rtt_avg)
            if rtt_stddev and rtt_stddev not in ("~", "0.000ms", ""):
                lines[-1] += " ± %s" % rtt_stddev
        elif status == "offline":
            lines.append("⚠️ Hết thời gian chờ RTT")

    # ── Substatus detail ──
    sub_label = SUBSTATUS_LABELS.get(substatus.lower() if substatus else "", "")
    if not sub_label and substatus and substatus.lower() not in ("none", ""):
        sub_label = "ℹ️ %s" % substatus
    if sub_label:
        lines.append(sub_label)

    lines.append("")

    # ── Routing group ──
    if group:
        if status == "offline" or any(w in action.lower() for w in ("remov", "omit")):
            lines.append("🛣️ Xóa khỏi nhóm định tuyến:")
        else:
            lines.append("🛣️ Thêm vào nhóm định tuyến:")
        lines.append("<code>%s</code>" % group)
        lines.append("")

    # ── Timestamp ──
    lines.append("⏰ %s" % now)

    return "\n".join(lines)


def format_dyndns_message(hostname, isp, iface, new_ip, pfsense=""):
    """Format a DynDNS IP update notification."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    isp_info = detect_isp(isp)
    lines = [
        "🔄 <b>CẬP NHẬT IP ĐỘNG</b>",
        "",
        "🖥️ Host: <code>%s</code>" % hostname,
        "🌐 Kết nối: <code>%s</code>  <i>(%s)</i>" % (isp, iface),
        "📍 IP mới: <code>%s</code>" % new_ip,
    ]
    if pfsense:
        lines.append("🔧 pfSense: <code>%s</code>" % pfsense)
    lines.append("")
    lines.append("⏰ %s" % now)
    return "\n".join(lines)


def format_system_message(event, pfsense=""):
    """Format pfSense system event (bootup / shutdown)."""
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
    """Format PPP/PPPoE WAN connection event notification."""
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
    """Format authentication / security event notification."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    if event in ("fail", "invalid"):
        if count >= 5:
            header = "🚨 <b>TẤN CÔNG BRUTE FORCE SSH</b>"
            detail = "🔴 Phát hiện <b>%d lần</b> đăng nhập thất bại!" % count
        else:
            header = "⚠️ <b>ĐĂNG NHẬP SSH THẤT BẠI</b>"
            detail = "❌ Đăng nhập không thành công"
    elif event == "fail_gui":
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
        lines.append("🌍 Nguồn IP: <code>%s</code>" % src_ip)
    lines.append(detail)
    lines.append("")
    lines.append("⏰ %s" % now)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Log parser
# ─────────────────────────────────────────────────────────────────────────────

# "MONITOR: GW_NAME is available now, adding to routing group GROUP_NAME"
RE_ACTION = re.compile(
    r"MONITOR:\s+(\S+)\s+is\s+(available|unavailable)\s+now[,.]?\s*"
    r"(adding to|removing from)\s+routing group\s+(\S+)",
    re.IGNORECASE
)

# "MONITOR: GW_NAME has packet loss, omitting from routing group GROUP_NAME"
RE_ACTION_OMIT = re.compile(
    r"MONITOR:\s+(\S+)\s+has packet loss,\s+omitting from\s+routing group\s+(\S+)",
    re.IGNORECASE
)

# "10.0.0.1|10.0.0.2|GW_NAME|12.5ms|0.3ms|5%|online|none"
# status: online | offline | down  (down = offline in pfSense dpinger)
RE_STATS = re.compile(
    r"(\d{1,3}(?:\.\d{1,3}){3})"    # gateway_ip
    r"\|(\d{1,3}(?:\.\d{1,3}){3})"  # monitor_ip
    r"\|(\S+?)"                       # gateway name
    r"\|([^|]*)"                      # rtt_avg
    r"\|([^|]*)"                      # rtt_stddev
    r"\|(\d+\.?\d*)%"                 # loss %
    r"\|(online|offline|down)"        # status (down treated as offline)
    r"\|([^|\s]*)"                    # substatus
)

# Older dpinger format: "MONITOR: GW is down / up"
RE_DOWN_SIMPLE = re.compile(r"MONITOR:\s+(\S+)\s+is\s+down", re.IGNORECASE)
RE_UP_SIMPLE   = re.compile(r"MONITOR:\s+(\S+)\s+is\s+up",   re.IGNORECASE)

# "DynDNS updated IP Address for HOST on ISP (interface) to IP"
RE_DYNDNS = re.compile(
    r"DynDNS updated IP Address for (\S+)\s+on\s+(\S+)\s+\(([^)]+)\)\s+to\s+([\d.]+)",
    re.IGNORECASE
)

# System events
RE_BOOTUP   = re.compile(r"Bootup complete",     re.IGNORECASE)
RE_SHUTDOWN = re.compile(r"pfSense will shutdown", re.IGNORECASE)

# Extract hostname from syslog line prefix (e.g. "May 28 12:49:02 homehoag dpinger: ...")
RE_SYSLOG_HOST = re.compile(r"^\w{3}\s+\d+\s+[\d:]+\s+(\S+)\s+")

# ── PPP / PPPoE WAN events ────────────────────────────────────────────────────
# pppd connect: "pppd[1234]: Connect: ppp0 <--> /dev/..."
RE_PPP_CONNECT    = re.compile(r"pppd\[\d+\][^:]*:\s+Connect:\s+(\S+)\s+<-->", re.IGNORECASE)
# pppd assigned IP: "pppd[1234]: remote IP address X.X.X.X"
RE_PPP_REMOTE_IP  = re.compile(r"pppd\[\d+\][^:]*:\s+remote IP address\s+([\d.]+)", re.IGNORECASE)
# pppd disconnect variants
RE_PPP_DISCONNECT = re.compile(
    r"pppd\[\d+\][^:]*:\s+(Connection terminated|LCP terminated|"
    r"Hangup \(SIGHUP\)|SIGTERM received|Modem hangup)",
    re.IGNORECASE
)
# pppd auth failure
RE_PPP_AUTH_FAIL  = re.compile(
    r"pppd\[\d+\][^:]*:\s+(PAP authentication failed|CHAP authentication failed|"
    r"Authentication failed)",
    re.IGNORECASE
)

# ── Auth / Security events ────────────────────────────────────────────────────
# SSH login failed
RE_AUTH_FAIL_SSH    = re.compile(
    r"sshd\[\d+\][^:]*:\s+Failed (?:password|publickey) for (\S+) from ([\d.]+)",
    re.IGNORECASE
)
# Invalid/nonexistent user attempt
RE_AUTH_INVALID_SSH = re.compile(
    r"sshd\[\d+\][^:]*:\s+Invalid user (\S+) from ([\d.]+)",
    re.IGNORECASE
)
# Successful SSH login
RE_AUTH_OK_SSH      = re.compile(
    r"sshd\[\d+\][^:]*:\s+Accepted (?:password|publickey|keyboard-interactive\S*) for (\S+) from ([\d.]+)",
    re.IGNORECASE
)
# pfSense GUI / php-fpm auth failure
RE_AUTH_FAIL_GUI    = re.compile(
    r"php(?:-fpm)?\[\d+\][^:]*:\s+.*(?:authentication error|Wrong password|login failed).*user[:\s]+['\"]?(\S+?)['\"]?",
    re.IGNORECASE
)


def parse_line(line):
    """
    Parse one syslog line. Returns a dict with event fields, or None.
    dict type values: 'action' | 'stats' | 'dyndns' | 'system'
    """
    # Extract hostname from syslog prefix for all event types
    host_m = RE_SYSLOG_HOST.match(line)
    pfsense = host_m.group(1) if host_m else ""

    # ── Gateway action: available/unavailable ──
    m = RE_ACTION.search(line)
    if m:
        return {
            "type":    "action",
            "gateway": m.group(1),
            "status":  "online" if m.group(2).lower() == "available" else "offline",
            "action":  m.group(3),
            "group":   m.group(4),
            "pfsense": pfsense,
        }

    # ── Gateway action: has packet loss, omitting (pfSense highloss format) ──
    m = RE_ACTION_OMIT.search(line)
    if m:
        return {
            "type":    "action",
            "gateway": m.group(1),
            "status":  "offline",
            "action":  "omitting from",
            "group":   m.group(2),
            "pfsense": pfsense,
        }

    # ── Stats line (down = offline) — syslog prefix may be absent ──
    m = RE_STATS.search(line)
    if m:
        raw_status = m.group(7).lower()
        return {
            "type":        "stats",
            "gateway_ip":  m.group(1),
            "monitor_ip":  m.group(2),
            "gateway":     m.group(3),
            "rtt_avg":     m.group(4).strip(),
            "rtt_stddev":  m.group(5).strip(),
            "loss_pct":    float(m.group(6)),
            "status":      "offline" if raw_status == "down" else raw_status,
            "substatus":   m.group(8).strip(),
            "pfsense":     pfsense,
        }

    # ── Older dpinger format ──
    m = RE_DOWN_SIMPLE.search(line)
    if m:
        return {"type": "action", "gateway": m.group(1), "status": "offline",
                "action": "removing from", "group": "", "pfsense": pfsense}

    m = RE_UP_SIMPLE.search(line)
    if m:
        return {"type": "action", "gateway": m.group(1), "status": "online",
                "action": "adding to", "group": "", "pfsense": pfsense}

    # ── DynDNS IP update ──
    m = RE_DYNDNS.search(line)
    if m:
        return {
            "type":      "dyndns",
            "hostname":  m.group(1),
            "isp":       m.group(2),
            "iface":     m.group(3),
            "new_ip":    m.group(4),
            "pfsense":   pfsense,
        }

    # ── System events ──
    if RE_BOOTUP.search(line):
        return {"type": "system", "event": "bootup", "pfsense": pfsense}

    if RE_SHUTDOWN.search(line):
        return {"type": "system", "event": "shutdown", "pfsense": pfsense}

    # ── PPP / PPPoE WAN ──────────────────────────────────────────────────────
    m = RE_PPP_CONNECT.search(line)
    if m:
        return {"type": "ppp", "event": "connect",
                "interface": m.group(1), "pfsense": pfsense}

    m = RE_PPP_REMOTE_IP.search(line)
    if m:
        return {"type": "ppp", "event": "remote_ip",
                "remote_ip": m.group(1), "pfsense": pfsense}

    m = RE_PPP_DISCONNECT.search(line)
    if m:
        return {"type": "ppp", "event": "disconnect",
                "reason": m.group(1), "pfsense": pfsense}

    m = RE_PPP_AUTH_FAIL.search(line)
    if m:
        return {"type": "ppp", "event": "auth_fail",
                "reason": m.group(1), "pfsense": pfsense}

    # ── Auth / Security ──────────────────────────────────────────────────────
    m = RE_AUTH_FAIL_SSH.search(line)
    if m:
        return {"type": "auth", "event": "fail",
                "user": m.group(1), "src_ip": m.group(2), "pfsense": pfsense}

    m = RE_AUTH_INVALID_SSH.search(line)
    if m:
        return {"type": "auth", "event": "invalid",
                "user": m.group(1), "src_ip": m.group(2), "pfsense": pfsense}

    m = RE_AUTH_OK_SSH.search(line)
    if m:
        return {"type": "auth", "event": "ok",
                "user": m.group(1), "src_ip": m.group(2), "pfsense": pfsense}

    m = RE_AUTH_FAIL_GUI.search(line)
    if m:
        return {"type": "auth", "event": "fail_gui",
                "user": m.group(1), "src_ip": "", "pfsense": pfsense}

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Pending event buffer — merges action + stats for same gateway within window
# ─────────────────────────────────────────────────────────────────────────────

class PendingBuffer:
    """Holds gateway events for `delay_seconds` before dispatching."""

    def __init__(self, delay):
        self.delay = delay
        self._buf = {}        # gateway -> merged event dict
        self._ts  = {}        # gateway -> first-seen timestamp

    def add(self, event):
        gw = event.get("gateway")
        if not gw:
            return
        if gw not in self._buf:
            self._buf[gw] = dict(event)
            self._ts[gw]  = time.time()
        else:
            # Merge: newer fields win, but don't overwrite with empty
            for k, v in event.items():
                if v not in (None, "", 0, 0.0):
                    self._buf[gw][k] = v

    def flush_ready(self):
        """Return list of events whose delay has elapsed; remove them."""
        now = time.time()
        ready = []
        for gw in list(self._ts):
            if now - self._ts[gw] >= self.delay:
                ready.append(self._buf.pop(gw))
                del self._ts[gw]
        return ready


# ─────────────────────────────────────────────────────────────────────────────
# Core processing logic
# ─────────────────────────────────────────────────────────────────────────────

def process_event(event, state, cfg):
    """Apply anti-spam, format, and send a single merged event."""
    gw     = event.get("gateway", "")
    status = event.get("status", "")

    if not gw or not status:
        return

    if not should_send(state, gw, status, cfg["spam_cooldown"]):
        _log("[%s] ⏭️  chống spam - bỏ qua (%s)" % (gw, status))
        return

    # Treat as offline if critically high loss despite "online" status
    loss = float(event.get("loss_pct", 0))
    effective_status = status
    if status == "online" and loss >= cfg["critical_loss_threshold"]:
        effective_status = "offline"
        _log("[%s] 📉 mất gói nghiêm trọng %.0f%% — leo thang cảnh báo MẤT KẾT NỐI" % (gw, loss))

    msg = format_message(
        gateway    = gw,
        status     = effective_status,
        monitor_ip = event.get("monitor_ip", ""),
        gateway_ip = event.get("gateway_ip", ""),
        rtt_avg    = event.get("rtt_avg", ""),
        rtt_stddev = event.get("rtt_stddev", ""),
        loss_pct   = loss,
        substatus  = event.get("substatus", ""),
        group      = event.get("group", ""),
        action     = event.get("action", ""),
        pfsense    = event.get("pfsense", ""),
    )

    ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg)
    if ok:
        state.setdefault(gw, {})
        state[gw]["status"]    = status
        state[gw]["last_sent"] = time.time()
        save_state(cfg["state_file"], state)
        _log("[%s] ✅ đã gửi %s (mất gói=%.0f%%)" % (gw, status, loss))
    else:
        _log("[%s] ❌ gửi thất bại" % gw)


# ─────────────────────────────────────────────────────────────────────────────
# Watch mode — multi-file log tailer using threads
# ─────────────────────────────────────────────────────────────────────────────

# Keywords covering ALL event types across all log files
_WATCH_KEYS = (
    "MONITOR:", "|online|", "|offline|", "|down|",
    "DynDNS updated", "Bootup complete", "pfSense will shutdown",
    "pppd[", "Connect:", "Connection terminated", "LCP terminated",
    "PAP authentication failed", "CHAP authentication failed",
    "Failed password", "Invalid user ", "Accepted password",
    "Accepted publickey", "authentication error",
)


def _tail_worker(log_path, out_queue):
    """Background thread: tail a single log file, put parsed events into queue."""
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
                fh = open(log_path, "r", encoding="utf-8", errors="replace")
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
    """Daemon: tail multiple log files (one thread each) and dispatch events."""
    log_files = cfg.get("log_files", [cfg.get("log_file", "/var/log/gateways.log")])
    state     = load_state(cfg["state_file"])
    buf       = PendingBuffer(cfg["delay_seconds"])
    ev_queue  = queue.Queue()

    # Brute-force tracker: src_ip -> list of timestamps
    brute_tracker = {}

    _log("📡 Telegram chat: %s" % cfg["telegram_chat_id"])
    _log("⏳ Trì hoãn cảnh báo: %ds | 🔕 Chặn spam gateway: %ds" % (
        cfg["delay_seconds"], cfg["spam_cooldown"]))
    _log("📂 Theo dõi %d file log:" % len(log_files))
    for lf in log_files:
        _log("   • %s" % lf)

    # Start one tailer thread per log file
    for lf in log_files:
        t = threading.Thread(target=_tail_worker, args=(lf, ev_queue), daemon=True)
        t.start()

    try:
        while True:
            # Drain the queue
            while not ev_queue.empty():
                try:
                    event = ev_queue.get_nowait()
                except queue.Empty:
                    break

                etype = event.get("type")
                ps    = event.get("pfsense", "")

                # ── Gateway events → pending buffer ──────────────────────────
                if etype in ("action", "stats"):
                    _log("[GW] %s → %s" % (event.get("gateway"), event.get("status")))
                    buf.add(event)

                # ── DynDNS ───────────────────────────────────────────────────
                elif etype == "dyndns":
                    msg = format_dyndns_message(
                        hostname=event["hostname"], isp=event["isp"],
                        iface=event["iface"], new_ip=event["new_ip"], pfsense=ps)
                    ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg)
                    _log("[DynDNS] %s %s → %s" % ("✅" if ok else "❌",
                                                    event["hostname"], event["new_ip"]))

                # ── System ───────────────────────────────────────────────────
                elif etype == "system":
                    msg = format_system_message(event["event"], ps)
                    if msg:
                        ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg)
                        label = "🟢 Khởi động" if event["event"] == "bootup" else "🔴 Tắt máy"
                        _log("[HỆ THỐNG] %s %s" % (label, "✅" if ok else "❌"))

                # ── PPP / PPPoE ──────────────────────────────────────────────
                elif etype == "ppp":
                    ev = event["event"]
                    _log("[PPP] sự kiện: %s" % ev)
                    # Skip remote_ip if we just sent a connect (minor event)
                    if ev == "remote_ip":
                        continue
                    msg = format_ppp_message(
                        event=ev,
                        interface=event.get("interface", ""),
                        remote_ip=event.get("remote_ip", ""),
                        reason=event.get("reason", ""),
                        pfsense=ps)
                    if msg:
                        ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg)
                        _log("[PPP] %s gửi %s" % ("✅" if ok else "❌", ev))

                # ── Auth / Security ──────────────────────────────────────────
                elif etype == "auth":
                    ev     = event["event"]
                    src_ip = event.get("src_ip", "")
                    user   = event.get("user", "")

                    if ev in ("fail", "invalid"):
                        # Track brute force per source IP
                        now_t = time.time()
                        window = cfg.get("auth_brute_window", 60)
                        brute_tracker.setdefault(src_ip, [])
                        brute_tracker[src_ip] = [
                            t for t in brute_tracker[src_ip] if now_t - t < window
                        ]
                        brute_tracker[src_ip].append(now_t)
                        count = len(brute_tracker[src_ip])
                        threshold = cfg.get("auth_brute_threshold", 5)

                        # Send on first attempt, then only at threshold multiples
                        if count == 1 or count % threshold == 0:
                            _log("[AUTH] ⚠️  %d lần thất bại từ %s" % (count, src_ip))
                            msg = format_auth_message(
                                event=ev, user=user, src_ip=src_ip,
                                count=count, pfsense=ps)
                            if msg:
                                ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg)
                                _log("[AUTH] %s gửi cảnh báo" % ("✅" if ok else "❌"))

                    elif ev in ("ok", "fail_gui"):
                        msg = format_auth_message(
                            event=ev, user=user, src_ip=src_ip, pfsense=ps)
                        if msg:
                            ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg)
                            _log("[AUTH] %s %s từ %s" % ("✅" if ok else "❌", ev, src_ip))

            # Flush ready gateway events
            for event in buf.flush_ready():
                process_event(event, state, cfg)

            time.sleep(0.4)

    except KeyboardInterrupt:
        _log("⏹️  Đã dừng.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        description="pfSense Gateway Telegram Notifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run as daemon watching all configured log files
  python3 pfsense_gw_notify.py watch

  # Override token/chat from CLI
  python3 pfsense_gw_notify.py watch --token BOT_TOKEN --chat-id CHAT_ID

  # Watch specific log files only
  python3 pfsense_gw_notify.py watch --logs /var/log/gateways.log /var/log/ppp.log

  # Direct call (from shell script on gateway event)
  python3 pfsense_gw_notify.py send \\
      --gateway VIETTEL_TAYNINH --status offline \\
      --monitor 10.123.234.2 --group FPT_st1 --loss 100

  # Send a test notification to verify config
  python3 pfsense_gw_notify.py test
        """
    )
    sub = p.add_subparsers(dest="mode", metavar="MODE")
    sub.required = True

    # ── watch ──
    wp = sub.add_parser("watch", help="Tail log files (daemon mode)")
    wp.add_argument("--logs",    default=None, nargs="+", metavar="PATH",
                    help="Log files to watch (default: CONFIG log_files list)")
    wp.add_argument("--token",   default=CONFIG["telegram_token"],  metavar="TOKEN")
    wp.add_argument("--chat-id", default=CONFIG["telegram_chat_id"],metavar="ID", dest="chat_id")
    wp.add_argument("--delay",   type=int, default=CONFIG["delay_seconds"],   metavar="SEC")
    wp.add_argument("--cooldown",type=int, default=CONFIG["spam_cooldown"],   metavar="SEC")

    # ── send ──
    sp = sub.add_parser("send", help="Send single event directly")
    sp.add_argument("--gateway",  required=True, metavar="NAME")
    sp.add_argument("--status",   required=True, choices=["online", "offline"])
    sp.add_argument("--monitor",  default="",    metavar="IP",  help="Monitor IP")
    sp.add_argument("--gw-ip",    default="",    metavar="IP",  dest="gw_ip", help="Gateway IP")
    sp.add_argument("--rtt",      default="",    metavar="VAL", help="RTT avg e.g. 12.5ms")
    sp.add_argument("--loss",     type=float, default=0.0, metavar="PCT")
    sp.add_argument("--substatus",default="",    metavar="VAL")
    sp.add_argument("--group",    default="",    metavar="NAME", help="Routing group")
    sp.add_argument("--token",    default=CONFIG["telegram_token"],  metavar="TOKEN")
    sp.add_argument("--chat-id",  default=CONFIG["telegram_chat_id"],metavar="ID", dest="chat_id")
    sp.add_argument("--no-delay", action="store_true", help="Skip the anti-flap delay")

    # ── test ──
    tp = sub.add_parser("test", help="Send a test notification")
    tp.add_argument("--token",   default=CONFIG["telegram_token"],  metavar="TOKEN")
    tp.add_argument("--chat-id", default=CONFIG["telegram_chat_id"],metavar="ID", dest="chat_id")
    tp.add_argument("--gateway", default="VIETTEL_TAYNINH")
    tp.add_argument("--status",  default="offline", choices=["online", "offline"])

    return p


def main():
    args = build_parser().parse_args()

    cfg = dict(CONFIG)
    if getattr(args, "token",   None): cfg["telegram_token"]   = args.token
    if getattr(args, "chat_id", None): cfg["telegram_chat_id"] = args.chat_id

    # ── watch mode ──
    if args.mode == "watch":
        if args.logs:
            cfg["log_files"] = args.logs
        cfg["delay_seconds"]  = args.delay
        cfg["spam_cooldown"]  = args.cooldown
        watch_log(cfg)

    # ── send mode ──
    elif args.mode == "send":
        state = load_state(cfg["state_file"])
        if not args.no_delay and cfg["delay_seconds"] > 0:
            _log("⏳ Đợi %d giây trước khi gửi…" % cfg["delay_seconds"])
            time.sleep(cfg["delay_seconds"])
        event = {
            "gateway":    args.gateway,
            "status":     args.status,
            "monitor_ip": args.monitor,
            "gateway_ip": args.gw_ip,
            "rtt_avg":    args.rtt,
            "loss_pct":   args.loss,
            "substatus":  args.substatus,
            "group":      args.group,
            "action":     "removing from" if args.status == "offline" else "adding to",
        }
        process_event(event, state, cfg)

    # ── test mode ──
    elif args.mode == "test":
        # OFFLINE test
        offline_msg = format_message(
            gateway="VIETTEL_TAYNINH", status="offline",
            monitor_ip="10.123.234.2", gateway_ip="10.123.234.1",
            rtt_avg="", rtt_stddev="", loss_pct=100.0,
            substatus="loss", group="FPT_st1", action="removing from",
        )
        # ONLINE test
        online_msg = format_message(
            gateway="FPT_TAYNINH", status="online",
            monitor_ip="10.10.88.1", gateway_ip="10.10.88.254",
            rtt_avg="14.5ms", rtt_stddev="1.2ms", loss_pct=5.0,
            substatus="none", group="LB_GR", action="adding to",
        )
        print("=" * 50)
        print("XEM TRƯỚC - MẤT KẾT NỐI:")
        print(offline_msg)
        print("=" * 50)
        print("XEM TRƯỚC - KẾT NỐI TRỞ LẠI:")
        print(online_msg)
        print("=" * 50)

        token   = cfg["telegram_token"]
        chat_id = cfg["telegram_chat_id"]

        if "YOUR_BOT_TOKEN" in token:
            print("\n⚠️  Vui lòng cài đặt token trong CONFIG trước khi test!")
            return

        _log("Đang gửi test MẤT KẾT NỐI…")
        ok1 = send_telegram(token, chat_id, offline_msg)
        time.sleep(2)
        _log("Đang gửi test KẾT NỐI TRỞ LẠI…")
        ok2 = send_telegram(token, chat_id, online_msg)

        if ok1 and ok2:
            print("✅ Đã gửi cả hai tin nhắn test thành công!")
        else:
            print("❌ Một hoặc nhiều tin nhắn thất bại. Kiểm tra lại token/chat_id.")


if __name__ == "__main__":
    main()
