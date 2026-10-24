#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${MAGNET_ALERT_PYTHON:-/usr/bin/python3}"
for script in magnet-alert.py xtuis_outbox.py; do
  "$PYTHON_BIN" -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$SOURCE_DIR/$script"
done
install -d -m 0755 /opt/magnet-alerts /etc/magnet-alerts
install -d -m 0700 /var/lib/magnet-alerts
install -m 0755 "$SOURCE_DIR/magnet-alert.py" /opt/magnet-alerts/magnet-alert.py
install -m 0644 "$SOURCE_DIR/xtuis_outbox.py" /opt/magnet-alerts/xtuis_outbox.py
if [[ ! -f /etc/magnet-alerts/alert.env ]]; then
  install -m 0600 "$SOURCE_DIR/alert.example.env" /etc/magnet-alerts/alert.env
else
  chmod 0600 /etc/magnet-alerts/alert.env
fi
install -m 0644 "$SOURCE_DIR/magnet-alert-outbox.service" /etc/systemd/system/magnet-alert-outbox.service
install -m 0644 "$SOURCE_DIR/magnet-alert-outbox.timer" /etc/systemd/system/magnet-alert-outbox.timer
systemctl daemon-reload
if [[ "${MAGNET_ALERT_ENABLE_OUTBOX:-0}" == "1" ]]; then
  systemctl enable --now magnet-alert-outbox.timer
fi
printf '%s\n' "installed=/opt/magnet-alerts/magnet-alert.py" "config=/etc/magnet-alerts/alert.env" "state_dir=/var/lib/magnet-alerts"
