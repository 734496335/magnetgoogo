#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo "root required" >&2; exit 1; }
ROLE="${MAGNET_MEDIA_HEALTH_ROLE:-}"
case "$ROLE" in compute|finalizer) ;; *) echo "set MAGNET_MEDIA_HEALTH_ROLE=compute or finalizer" >&2; exit 1 ;; esac
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f /opt/magnet-alerts/magnet-alert.py && -f /opt/magnet-alerts/xtuis_outbox.py ]] || { echo "install shared alerts first" >&2; exit 1; }
/usr/bin/python3 -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$SOURCE_DIR/media-health-check.py"
if [[ -f /etc/magnet-media-health/health.env ]]; then
  CURRENT="$(sed -n 's/^MAGNET_MEDIA_HEALTH_ROLE=//p' /etc/magnet-media-health/health.env)"
  [[ "$CURRENT" == "$ROLE" ]] || { echo "existing media health role differs" >&2; exit 1; }
fi
install -d -m 0700 /etc/magnet-media-health /var/lib/magnet-alerts
install -d -m 0755 /opt/magnet-alerts
install -m 0755 "$SOURCE_DIR/media-health-check.py" /opt/magnet-alerts/media-health-check.py
if [[ ! -f /etc/magnet-media-health/health.env ]]; then
  install -m 0600 "$SOURCE_DIR/media-health.example.env" /etc/magnet-media-health/health.env
  sed -i "s/^MAGNET_MEDIA_HEALTH_ROLE=.*/MAGNET_MEDIA_HEALTH_ROLE=$ROLE/" /etc/magnet-media-health/health.env
fi
chmod 0600 /etc/magnet-media-health/health.env
install -m 0644 "$SOURCE_DIR/magnet-media-health.service" /etc/systemd/system/magnet-media-health.service
install -m 0644 "$SOURCE_DIR/magnet-media-health.timer" /etc/systemd/system/magnet-media-health.timer
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/magnet-media-health.service /etc/systemd/system/magnet-media-health.timer
if [[ "${ENABLE_MEDIA_HEALTH_TIMER:-0}" == "1" ]]; then
  systemctl enable --now magnet-media-health.timer
fi
printf '%s\n' "installed=media-health" "role=$ROLE"
