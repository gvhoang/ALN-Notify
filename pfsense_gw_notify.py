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
    "telegram_token":   "8506670215:AAHOR-zBY-4TbaSTCLztxumUH2y5PdfcDlg",     # e.g. 8506670215:AAHOR-zBY...
    "telegram_chat_id": "1015285796",        # e.g. 1015285796

    # pfSense log file path (FreeBSD)
    "log_file": "/var/log/system.log",

    # State file to persist gateway statuses across restarts
    "state_file": "/tmp/pf_gw_states.json",

    # Delay (seconds) before sending alert — absorbs brief flapping
    "delay_seconds": 5,

    # How long (seconds) to suppress duplicate same-status notifications
    "spam_cooldown": 300,

    # Packet loss % thresholds
    "high_loss_threshold":     20,   # ⚠️  warn even if "online"
    "critical_loss_threshold": 80,   # 🔴  treat as offline
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
    "loss":      "📉 Loss threshold exceeded",
    "delay":     "⏳ Delay threshold exceeded",
    "highdelay": "⏳ High delay detected",
    "highloss":  "📉 High loss detected",
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
    return {"icon": "🌐", "label": "Unknown"}


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
        _err("Cannot save state: %s" % e)


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
        _err("Telegram send failed: %s" % e)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Message formatter
# ─────────────────────────────────────────────────────────────────────────────

def format_message(gateway, status, monitor_ip="", gateway_ip="",
                   rtt_avg="", rtt_stddev="", loss_pct=0.0,
                   substatus="", group="", action=""):
    """Build a beautiful Telegram HTML notification string."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    isp = detect_isp(gateway)

    # ── Header ──
    if status == "offline":
        header = "🔴 <b>GATEWAY OFFLINE</b>"
    elif status == "online":
        header = "🟢 <b>GATEWAY ONLINE</b>"
    else:
        header = "⚠️ <b>GATEWAY ALERT</b>"

    lines = [header, ""]

    # ── WAN identity ──
    lines.append("🌐 WAN: <code>%s</code>" % gateway)
    if monitor_ip:
        lines.append("📡 Monitor: <code>%s</code>" % monitor_ip)
    if gateway_ip:
        lines.append("🔗 Gateway IP: <code>%s</code>" % gateway_ip)

    lines.append("")

    # ── Loss & RTT ──
    if loss_pct >= 100:
        lines.append("⚠️ Packet loss: <b>100%</b>")
        lines.append("⚠️ RTT timeout")
    else:
        if loss_pct > 0:
            icon = "⚠️" if loss_pct >= CONFIG["high_loss_threshold"] else "📊"
            lines.append("%s Packet loss: <b>%.0f%%</b>" % (icon, loss_pct))
        if rtt_avg and rtt_avg not in ("~", "0.000ms", "0ms", ""):
            lines.append("⏱️ RTT: %s" % rtt_avg)
            if rtt_stddev and rtt_stddev not in ("~", "0.000ms", ""):
                lines[-1] += " ± %s" % rtt_stddev
        elif status == "offline":
            lines.append("⚠️ RTT timeout")

    # ── Substatus detail ──
    sub_label = SUBSTATUS_LABELS.get(substatus.lower() if substatus else "", "")
    if not sub_label and substatus and substatus.lower() not in ("none", ""):
        sub_label = "ℹ️ %s" % substatus
    if sub_label:
        lines.append(sub_label)

    lines.append("")

    # ── Routing group ──
    if group:
        if status == "offline" or "remov" in action.lower():
            lines.append("🛣️ Removed from:")
        else:
            lines.append("🛣️ Added to:")
        lines.append("<code>%s</code>" % group)
        lines.append("")

    # ── Timestamp ──
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

# "10.0.0.1|10.0.0.2|GW_NAME|12.5ms|0.3ms|5%|online|none"
RE_STATS = re.compile(
    r"(\d{1,3}(?:\.\d{1,3}){3})"    # gateway_ip
    r"\|(\d{1,3}(?:\.\d{1,3}){3})"  # monitor_ip
    r"\|(\S+?)"                       # gateway name
    r"\|([^|]*)"                      # rtt_avg
    r"\|([^|]*)"                      # rtt_stddev
    r"\|(\d+\.?\d*)%"                 # loss %
    r"\|(online|offline)"             # status
    r"\|([^|\s]*)"                    # substatus
)

# Older dpinger format: "MONITOR: GW is down"
RE_DOWN_SIMPLE = re.compile(r"MONITOR:\s+(\S+)\s+is\s+down", re.IGNORECASE)
RE_UP_SIMPLE   = re.compile(r"MONITOR:\s+(\S+)\s+is\s+up",   re.IGNORECASE)


def parse_line(line):
    """
    Parse one syslog line. Returns a dict with event fields, or None.
    Dict always has: 'gateway', 'status', and optionally other fields.
    """
    m = RE_ACTION.search(line)
    if m:
        return {
            "type":    "action",
            "gateway": m.group(1),
            "status":  "online" if m.group(2).lower() == "available" else "offline",
            "action":  m.group(3),
            "group":   m.group(4),
        }

    m = RE_STATS.search(line)
    if m:
        return {
            "type":        "stats",
            "gateway_ip":  m.group(1),
            "monitor_ip":  m.group(2),
            "gateway":     m.group(3),
            "rtt_avg":     m.group(4).strip(),
            "rtt_stddev":  m.group(5).strip(),
            "loss_pct":    float(m.group(6)),
            "status":      m.group(7),
            "substatus":   m.group(8).strip(),
        }

    m = RE_DOWN_SIMPLE.search(line)
    if m:
        return {"type": "action", "gateway": m.group(1), "status": "offline",
                "action": "removing from", "group": ""}

    m = RE_UP_SIMPLE.search(line)
    if m:
        return {"type": "action", "gateway": m.group(1), "status": "online",
                "action": "adding to", "group": ""}

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
        _log("[%s] ⏭️  anti-spam skip (%s)" % (gw, status))
        return

    # Treat as offline if critically high loss despite "online" status
    loss = float(event.get("loss_pct", 0))
    effective_status = status
    if status == "online" and loss >= cfg["critical_loss_threshold"]:
        effective_status = "offline"
        _log("[%s] 📉 critical loss %.0f%% — escalating to OFFLINE alert" % (gw, loss))

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
    )

    ok = send_telegram(cfg["telegram_token"], cfg["telegram_chat_id"], msg)
    if ok:
        state.setdefault(gw, {})
        state[gw]["status"]    = status
        state[gw]["last_sent"] = time.time()
        save_state(cfg["state_file"], state)
        _log("[%s] ✅ sent %s (loss=%.0f%%)" % (gw, status, loss))
    else:
        _log("[%s] ❌ send failed" % gw)


# ─────────────────────────────────────────────────────────────────────────────
# Watch mode — pure Python log tailer (no subprocess)
# ─────────────────────────────────────────────────────────────────────────────

def watch_log(cfg):
    """Daemon: tail log_file and process gateway events."""
    log_path = cfg["log_file"]
    state    = load_state(cfg["state_file"])
    buf      = PendingBuffer(cfg["delay_seconds"])

    _log("👀 Watching: %s" % log_path)
    _log("📡 Telegram chat: %s" % cfg["telegram_chat_id"])
    _log("⏳ Alert delay: %ds | 🔕 Cooldown: %ds" % (
        cfg["delay_seconds"], cfg["spam_cooldown"]))

    # Open file and seek to end
    try:
        fh = open(log_path, "r", encoding="utf-8", errors="replace")
    except OSError as e:
        _err("Cannot open log: %s" % e)
        sys.exit(1)

    fh.seek(0, 2)  # Seek to end
    inode = os.fstat(fh.fileno()).st_ino

    try:
        while True:
            # Detect log rotation
            try:
                cur_inode = os.stat(log_path).st_ino
            except OSError:
                cur_inode = inode

            if cur_inode != inode:
                _log("🔄 Log rotated — reopening")
                fh.close()
                fh = open(log_path, "r", encoding="utf-8", errors="replace")
                inode = os.fstat(fh.fileno()).st_ino

            # Read new lines
            for line in fh:
                line = line.rstrip("\n\r")
                if not any(k in line for k in ("MONITOR:", "|online|", "|offline|")):
                    continue
                event = parse_line(line)
                if event:
                    _log("[PARSE] %s → %s" % (event.get("gateway"), event.get("status")))
                    buf.add(event)

            # Dispatch ready events
            for event in buf.flush_ready():
                process_event(event, state, cfg)

            time.sleep(0.5)

    except KeyboardInterrupt:
        _log("⏹️  Stopped.")
    finally:
        fh.close()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        description="pfSense Gateway Telegram Notifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run as daemon watching /var/log/system.log
  python3 pfsense_gw_notify.py watch

  # Override token/chat from CLI
  python3 pfsense_gw_notify.py watch --token BOT_TOKEN --chat-id CHAT_ID

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
    wp = sub.add_parser("watch", help="Tail log file (daemon mode)")
    wp.add_argument("--log",     default=CONFIG["log_file"],        metavar="PATH")
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
        cfg["log_file"]       = args.log
        cfg["delay_seconds"]  = args.delay
        cfg["spam_cooldown"]  = args.cooldown
        watch_log(cfg)

    # ── send mode ──
    elif args.mode == "send":
        state = load_state(cfg["state_file"])
        if not args.no_delay and cfg["delay_seconds"] > 0:
            _log("⏳ Waiting %ds before sending…" % cfg["delay_seconds"])
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
        print("OFFLINE preview:")
        print(offline_msg)
        print("=" * 50)
        print("ONLINE preview:")
        print(online_msg)
        print("=" * 50)

        token   = cfg["telegram_token"]
        chat_id = cfg["telegram_chat_id"]

        if "YOUR_BOT_TOKEN" in token:
            print("\n⚠️  Set your token in CONFIG before testing!")
            return

        _log("Sending OFFLINE test…")
        ok1 = send_telegram(token, chat_id, offline_msg)
        time.sleep(2)
        _log("Sending ONLINE test…")
        ok2 = send_telegram(token, chat_id, online_msg)

        if ok1 and ok2:
            print("✅ Both test messages sent!")
        else:
            print("❌ One or more messages failed. Check token/chat_id.")


if __name__ == "__main__":
    main()
