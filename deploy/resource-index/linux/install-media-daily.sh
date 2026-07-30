#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

APP_ROOT=${APP_ROOT:-/opt/magnet-media/app}
CONFIG_ROOT=${CONFIG_ROOT:-/etc/magnet-media}
STATE_ROOT=${STATE_ROOT:-/var/lib/magnet-media}
ENABLE_TIMERS=${ENABLE_TIMERS:-0}

install -d -m 0755 /opt/magnet-media "$APP_ROOT" "$STATE_ROOT" "$STATE_ROOT/public"
install -d -m 0700 "$CONFIG_ROOT"
install -d -m 0755 "$STATE_ROOT/status" "$STATE_ROOT/runs" "$STATE_ROOT/sources" "$STATE_ROOT/bundles" "$STATE_ROOT/releases" "$STATE_ROOT/receipts"

if [[ ! -f "$CONFIG_ROOT/media-daily.json" ]]; then
  install -m 0600 "$APP_ROOT/deploy/resource-index/linux/media-daily.example.json" "$CONFIG_ROOT/media-daily.json"
fi
if [[ ! -f "$CONFIG_ROOT/media.env" ]]; then
  printf '%s\n' '# R2_UPLOAD_WORKER_TOKEN is installed separately; never commit it.' > "$CONFIG_ROOT/media.env"
  chmod 0600 "$CONFIG_ROOT/media.env"
fi

chmod 0755 \
  "$APP_ROOT/deploy/resource-index/linux/run-media-daily.sh" \
  "$APP_ROOT/deploy/resource-index/linux/media-status.sh"

docker build \
  --pull \
  -f "$APP_ROOT/deploy/resource-index/linux/Dockerfile" \
  -t magnet-media-daily:latest \
  "$APP_ROOT"

install -m 0644 "$APP_ROOT/deploy/resource-index/linux/magnet-media-daily.service" /etc/systemd/system/magnet-media-daily.service
install -m 0644 "$APP_ROOT/deploy/resource-index/linux/magnet-media-daily.timer" /etc/systemd/system/magnet-media-daily.timer
install -m 0644 "$APP_ROOT/deploy/resource-index/linux/magnet-media-audit.service" /etc/systemd/system/magnet-media-audit.service
install -m 0644 "$APP_ROOT/deploy/resource-index/linux/magnet-media-audit.timer" /etc/systemd/system/magnet-media-audit.timer

python3 "$APP_ROOT/deploy/resource-index/install-nginx-media-include.py" \
  --config /etc/nginx/conf.d/magnetgoogo.conf \
  --snippet-source "$APP_ROOT/deploy/resource-index/linux/nginx-media-alias.conf" \
  --snippet-target /etc/nginx/snippets/magnetgoogo-media.conf
nginx -t
systemctl reload nginx
systemctl daemon-reload

if [[ "$ENABLE_TIMERS" == "1" ]]; then
  systemctl enable --now magnet-media-daily.timer magnet-media-audit.timer
fi

echo "MEDIA_DAILY_INSTALL_READY"
echo "config=$CONFIG_ROOT/media-daily.json"
echo "environment=$CONFIG_ROOT/media.env"
echo "status=$APP_ROOT/deploy/resource-index/linux/media-status.sh"
