#!/bin/sh
# /usr/local/etc/rc.d/pf_notify.sh -- pfSense Gateway Telegram Notifier service
# Usage: pf_notify.sh {start|stop|restart|reload|status}

PIDFILE="/var/run/pf_notify.pid"
PYTHON="/usr/local/bin/python3.11"
SCRIPT="/usr/local/sbin/pf_notify.py"
LOGFILE="/var/log/pf_notify.log"
CONFIG="/usr/local/etc/pf_notify/config.json"

_get_pid() {
    [ -f "$PIDFILE" ] && cat "$PIDFILE" 2>/dev/null
}

_is_running() {
    PID=$(_get_pid)
    [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null
}

case "$1" in
start)
    if _is_running; then
        echo "pf_notify dang chay (PID: $(_get_pid)) -- khong khoi dong lai"
        exit 0
    fi
    rm -f "$PIDFILE"
    mkdir -p /var/db/pf_notify
    /usr/sbin/daemon -f -o "$LOGFILE" -p "$PIDFILE" \
        "$PYTHON" "$SCRIPT" watch --config "$CONFIG"
    sleep 1
    if _is_running; then
        echo "pf_notify started (PID: $(_get_pid))"
    else
        echo "pf_notify: khoi dong that bai -- xem $LOGFILE"
        exit 1
    fi
    ;;
stop)
    PID=$(_get_pid)
    if [ -z "$PID" ]; then
        echo "pf_notify not running"
        rm -f "$PIDFILE"
        exit 0
    fi
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        sleep 2
        kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
        echo "pf_notify stopped (PID: $PID)"
    else
        echo "pf_notify: PID $PID khong ton tai (stale)"
    fi
    rm -f "$PIDFILE"
    ;;
restart)
    $0 stop
    sleep 1
    $0 start
    ;;
reload)
    PID=$(_get_pid)
    if [ -z "$PID" ]; then
        echo "pf_notify not running"
        exit 1
    fi
    if kill -0 "$PID" 2>/dev/null; then
        kill -HUP "$PID"
        echo "pf_notify: da gui SIGHUP (reload config) -> PID $PID"
    else
        echo "pf_notify: PID $PID stale -- khoi dong lai"
        rm -f "$PIDFILE"
        $0 start
    fi
    ;;
status)
    PID=$(_get_pid)
    if [ -z "$PID" ]; then
        echo "pf_notify not running"
        exit 1
    fi
    if kill -0 "$PID" 2>/dev/null; then
        echo "pf_notify running (PID: $PID)"
    else
        echo "pf_notify: PID file ton tai ($PID) nhung process da chet -- stale PID"
        exit 2
    fi
    ;;
*)
    echo "Usage: $0 {start|stop|restart|reload|status}"
    exit 1
    ;;
esac
