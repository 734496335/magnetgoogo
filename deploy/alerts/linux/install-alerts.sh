#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${MAGNET_ALERT_PYTHON:-/usr/bin/python3}"
"$PYTHON_BIN" -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$SOURCE_DIR/magnet-alert.py"
install -d -m 0755 /opt/magnet-alerts /etc/magnet-alerts
install -d -m 0700 /var/lib/magnet-alerts
install -m 0755 "$SOURCE_DIR/magnet-alert.py" /opt/magnet-alerts/magnet-alert.py
if [[ ! -f /etc/magnet-alerts/alert.env ]]; then
  install -m 0600 "$SOURCE_DIR/alert.example.env" /etc/magnet-alerts/alert.env
else
  chmod 0600 /etc/magnet-alerts/alert.env
fi
printf '%s\n' "installed=/opt/magnet-alerts/magnet-alert.py" "config=/etc/magnet-alerts/alert.env" "state_dir=/var/lib/magnet-alerts"
