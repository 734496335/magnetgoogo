#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

APP_ROOT=${APP_ROOT:-/opt/magnet-media/app}
CONFIG_ROOT=${CONFIG_ROOT:-/etc/magnet-media}
STATE_ROOT=${STATE_ROOT:-/var/lib/magnet-media}
LIVE_MEDIA_ROOT=${LIVE_MEDIA_ROOT:-/var/www/magnetgoogo-site/media}
NGINX_CONFIG=${NGINX_CONFIG:-/etc/nginx/conf.d/magnetgoogo.conf}
NGINX_SNIPPET=${NGINX_SNIPPET:-/etc/nginx/snippets/magnetgoogo-media.conf}
ENABLE_TIMERS=${ENABLE_TIMERS:-0}
MEDIA_SEED_ROOT=${MEDIA_SEED_ROOT:-}
IMAGE=${MAGNET_MEDIA_IMAGE:-magnet-media-daily:latest}

install -d -m 0755 /opt/magnet-media "$APP_ROOT" "$STATE_ROOT"
install -d -m 0700 "$CONFIG_ROOT"
install -d -m 0755 \
  "$STATE_ROOT/status" \
  "$STATE_ROOT/runs" \
  "$STATE_ROOT/sources" \
  "$STATE_ROOT/bundles" \
  "$STATE_ROOT/releases" \
  "$STATE_ROOT/receipts" \
  "$STATE_ROOT/ratings" \
  "$STATE_ROOT/locks"

if [[ ! -f "$CONFIG_ROOT/media-daily.json" ]]; then
  install -m 0600 "$APP_ROOT/deploy/resource-index/linux/media-daily.example.json" "$CONFIG_ROOT/media-daily.json"
fi
if [[ ! -f "$CONFIG_ROOT/media.env" ]]; then
  printf '%s\n' '# Candidate soak needs no R2 upload token.' > "$CONFIG_ROOT/media.env"
  chmod 0600 "$CONFIG_ROOT/media.env"
fi
install -m 0644 \
  "$APP_ROOT/deploy/resource-index/linux/media-production-ed25519-public.pem" \
  "$CONFIG_ROOT/media-production-ed25519-public.pem"

chmod 0755 \
  "$APP_ROOT/deploy/resource-index/linux/run-media-daily.sh" \
  "$APP_ROOT/deploy/resource-index/linux/media-status.sh"

docker build \
  --pull \
  -f "$APP_ROOT/deploy/resource-index/linux/Dockerfile" \
  -t "$IMAGE" \
  "$APP_ROOT"

if [[ ! -f "$CONFIG_ROOT/media-ed25519-private.pem" || ! -f "$CONFIG_ROOT/media-ed25519-public.pem" ]]; then
  docker run --rm \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    -v "$CONFIG_ROOT:/etc/magnet-media" \
    "$IMAGE" \
    init-media-signing-key \
    --private-key /etc/magnet-media/media-ed25519-private.pem \
    --public-key /etc/magnet-media/media-ed25519-public.pem
fi
chmod 0600 "$CONFIG_ROOT/media-ed25519-private.pem"
chmod 0644 "$CONFIG_ROOT/media-ed25519-public.pem"

if [[ -n "$MEDIA_SEED_ROOT" ]]; then
  python3 "$APP_ROOT/deploy/resource-index/install-media-candidate-seed.py" \
    --seed-root "$MEDIA_SEED_ROOT" \
    --state-root "$STATE_ROOT"
fi

python3 "$APP_ROOT/deploy/resource-index/prepare-nginx-media-root.py" \
  --source "$LIVE_MEDIA_ROOT" \
  --target "$STATE_ROOT/public"

install -m 0644 "$APP_ROOT/deploy/resource-index/linux/magnet-media-daily.service" /etc/systemd/system/magnet-media-daily.service
install -m 0644 "$APP_ROOT/deploy/resource-index/linux/magnet-media-daily.timer" /etc/systemd/system/magnet-media-daily.timer
install -m 0644 "$APP_ROOT/deploy/resource-index/linux/magnet-media-audit.service" /etc/systemd/system/magnet-media-audit.service
install -m 0644 "$APP_ROOT/deploy/resource-index/linux/magnet-media-audit.timer" /etc/systemd/system/magnet-media-audit.timer

rollback_root=$(mktemp -d /etc/nginx/.magnet-media-install.XXXXXX)
cp -a "$NGINX_CONFIG" "$rollback_root/nginx.conf"
if [[ -f "$NGINX_SNIPPET" ]]; then
  cp -a "$NGINX_SNIPPET" "$rollback_root/snippet.conf"
  snippet_existed=1
else
  snippet_existed=0
fi
nginx_changed=1
rollback_nginx() {
  trap - ERR
  if [[ "$nginx_changed" == "1" ]]; then
    cp -a "$rollback_root/nginx.conf" "$NGINX_CONFIG"
    if [[ "$snippet_existed" == "1" ]]; then
      cp -a "$rollback_root/snippet.conf" "$NGINX_SNIPPET"
    else
      rm -f "$NGINX_SNIPPET"
    fi
    nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
  fi
  rm -rf "$rollback_root"
}
trap rollback_nginx ERR

python3 "$APP_ROOT/deploy/resource-index/install-nginx-media-include.py" \
  --config "$NGINX_CONFIG" \
  --snippet-source "$APP_ROOT/deploy/resource-index/linux/nginx-media-alias.conf" \
  --snippet-target "$NGINX_SNIPPET"
nginx -t
systemctl reload nginx
nginx_changed=0
trap - ERR
rm -rf "$rollback_root"

systemctl daemon-reload
if [[ "$ENABLE_TIMERS" == "1" ]]; then
  systemctl enable --now magnet-media-daily.timer magnet-media-audit.timer
fi

echo "MEDIA_DAILY_INSTALL_READY"
echo "mode=candidate-only"
echo "config=$CONFIG_ROOT/media-daily.json"
echo "environment=$CONFIG_ROOT/media.env"
echo "status=$APP_ROOT/deploy/resource-index/linux/media-status.sh"
echo "timers_enabled=$ENABLE_TIMERS"
