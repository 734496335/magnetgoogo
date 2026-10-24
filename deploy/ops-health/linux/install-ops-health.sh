#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
/usr/bin/python3 -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$SOURCE_DIR/ops-health-check.py"
install -d -m 0755 /opt/magnet-ops-health
install -d -m 0700 /etc/magnet-alerts /var/lib/magnet-alerts
install -m 0755 "$SOURCE_DIR/ops-health-check.py" /opt/magnet-ops-health/ops-health-check.py
install -m 0644 "$SOURCE_DIR/magnet-ops-health.service" /etc/systemd/system/magnet-ops-health.service
install -m 0644 "$SOURCE_DIR/magnet-ops-health.timer" /etc/systemd/system/magnet-ops-health.timer
systemctl daemon-reload
if [[ -f /etc/magnet-alerts/ops-health.json ]]; then
  systemctl enable --now magnet-ops-health.timer
  printf '%s\n' 'ops_health_timer=enabled'
else
  printf '%s\n' 'ops_health_config=missing; timer not enabled'
fi
