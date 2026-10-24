#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo "root required" >&2; exit 1; }
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f /opt/magnet-alerts/magnet-alert.py && -f /opt/magnet-alerts/xtuis_outbox.py ]] || { echo "install shared alerts first" >&2; exit 1; }
[[ -d /opt/apps/travel-fare-monitor/state ]] || { echo "Travel state directory missing" >&2; exit 1; }
/usr/bin/python3 -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$SOURCE_DIR/travel-wechat-relay.py"
install -d -o 1001 -g 1001 -m 0700 /opt/apps/travel-fare-monitor/state/wechat-outbox
install -m 0755 "$SOURCE_DIR/travel-wechat-relay.py" /opt/magnet-alerts/travel-wechat-relay.py
install -m 0644 "$SOURCE_DIR/magnet-travel-wechat-relay.service" /etc/systemd/system/magnet-travel-wechat-relay.service
install -m 0644 "$SOURCE_DIR/magnet-travel-wechat-relay.timer" /etc/systemd/system/magnet-travel-wechat-relay.timer
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/magnet-travel-wechat-relay.service /etc/systemd/system/magnet-travel-wechat-relay.timer
if [[ "${ENABLE_TRAVEL_WECHAT_RELAY:-0}" == "1" ]]; then
  systemctl enable --now magnet-travel-wechat-relay.timer
fi
