#!/bin/sh
case "$1" in
start)
    pkill -f pfsense_gw_notify.py 2>/dev/null
    sleep 1
    nohup /usr/local/bin/python3.11 /root/pfsense_gw_notify.py watch >> /var/log/pf_notify.log 2>&1 &
    echo $! > /var/run/pf_notify.pid
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
            echo "pf_notify: PID file ton tai nhung process da chet"
        fi
    else
        echo "pf_notify not running"
    fi
    ;;
*)
    echo "Usage: $0 {start|stop|status}"
    ;;
esac