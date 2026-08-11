#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -d -m 0755 /opt/magnet-alerts /etc/magnet-alerts /var/lib/magnet-alerts
install -m 0755 "$SOURCE_DIR/magnet-alert.py" /opt/magnet-alerts/magnet-alert.py
if [[ ! -f /etc/magnet-alerts/alert.env ]]; then
  install -m 0600 "$SOURCE_DIR/alert.example.env" /etc/magnet-alerts/alert.env
else
  chmod 0600 /etc/magnet-alerts/alert.env
fi
chmod 0700 /var/lib/magnet-alerts
printf '%s\n' "installed=/opt/magnet-alerts/magnet-alert.py" "config=/etc/magnet-alerts/alert.env" "state=/var/lib/magnet-alerts/state.json"
