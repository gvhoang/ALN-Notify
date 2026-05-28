#!/bin/sh
# ─────────────────────────────────────────────────────────────────
# pfSense Gateway Monitor — Shell wrapper
# Drop-in replacement for pfsense_log_watch.sh
#
# This script calls the Python notifier instead of raw curl.
# Place at: /root/pfsense_gw_notify_hook.sh
# Make executable: chmod +x /root/pfsense_gw_notify_hook.sh
# ─────────────────────────────────────────────────────────────────

PYTHON="/usr/local/bin/python3"
SCRIPT="/root/pfsense_gw_notify.py"
LOG="/var/log/system.log"

# ── Daemon mode (watch log) ──────────────────────────────────────
# Usage: ./pfsense_gw_notify_hook.sh watch
if [ "$1" = "watch" ]; then
    exec "$PYTHON" "$SCRIPT" watch --log "$LOG"
fi

# ── Direct call mode (from dpinger callback / manual trigger) ───
# Usage: ./pfsense_gw_notify_hook.sh send GATEWAY_NAME online|offline [GROUP]
if [ "$1" = "send" ]; then
    GW="$2"
    STATUS="$3"
    GROUP="${4:-}"
    MONITOR="${5:-}"
    LOSS="${6:-0}"

    exec "$PYTHON" "$SCRIPT" send \
        --gateway "$GW" \
        --status  "$STATUS" \
        --group   "$GROUP" \
        --monitor "$MONITOR" \
        --loss    "$LOSS"
fi

# ── Test ────────────────────────────────────────────────────────
if [ "$1" = "test" ]; then
    exec "$PYTHON" "$SCRIPT" test
fi

echo "Usage: $0 watch | send GW_NAME online|offline [GROUP] | test"
exit 1
