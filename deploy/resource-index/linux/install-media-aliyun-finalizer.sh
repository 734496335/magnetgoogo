#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "run as root on the Aliyun media host" >&2
  exit 1
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
APP_RELEASE=${APP_RELEASE:-$(cd -- "$SCRIPT_DIR/../../.." && pwd)}
release_name=$(basename "$APP_RELEASE")
APP_ROOT=${APP_ROOT:-/opt/magnet-media-finalizer}
APP_LINK=$APP_ROOT/app
CONFIG_ROOT=${CONFIG_ROOT:-/etc/magnet-media}
IMAGE=${MAGNET_MEDIA_FINALIZER_IMAGE:-magnet-media-finalizer:$release_name}
ENABLE_FINALIZER_TIMER=${ENABLE_FINALIZER_TIMER:-0}
FINALIZER_MODE=${FINALIZER_MODE:-candidate}

[[ -d "$APP_RELEASE" && "$release_name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid APP_RELEASE" >&2; exit 2; }
[[ "$FINALIZER_MODE" == "candidate" || "$FINALIZER_MODE" == "publish" ]] || { echo "FINALIZER_MODE must be candidate or publish" >&2; exit 2; }
for path in \
  "$APP_RELEASE/deploy/resource-index/linux/magnet-media-oracle-outbox-tunnel.service" \
  "$APP_RELEASE/deploy/resource-index/linux/magnet-media-compute-finalizer.service" \
  "$APP_RELEASE/deploy/resource-index/linux/magnet-media-compute-finalizer.timer" \
  "$APP_RELEASE/deploy/resource-index/linux/run-media-compute-finalizer.sh" \
  "$APP_RELEASE/deploy/resource-index/fetch-media-compute-handoff.py" \
  "$APP_RELEASE/deploy/resource-index/finalize-media-compute.py"; do
  [[ -f "$path" ]] || { echo "missing required finalizer file: $path" >&2; exit 2; }
done
for path in \
  "$CONFIG_ROOT/media-daily.json" \
  "$CONFIG_ROOT/media.env" \
  "$CONFIG_ROOT/media-ed25519-private.pem" \
  "$CONFIG_ROOT/media-ed25519-public.pem"; do
  [[ -f "$path" ]] || { echo "required production material is missing: $path" >&2; exit 2; }
done
if ! grep -Eq '^R2_UPLOAD_WORKER_TOKEN=.{32,}$' "$CONFIG_ROOT/media.env"; then
  echo "production R2 token is missing on Aliyun finalizer host" >&2
  exit 2
fi
if ! systemctl is-enabled --quiet magnet-media-daily.timer; then
  echo "old Aliyun crawler timer must remain enabled during finalizer installation" >&2
  exit 2
fi
[[ -f /home/admin/.ssh/travel-oracle-tunnel ]] || { echo "existing Oracle tunnel identity is missing" >&2; exit 2; }
[[ -f /home/admin/.ssh/known_hosts ]] || { echo "Oracle known_hosts is missing" >&2; exit 2; }
/usr/bin/docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "finalizer image is missing; run build-media-aliyun-finalizer-image.sh first" >&2; exit 2; }
[[ "$(/usr/bin/docker image inspect "$IMAGE" --format '{{.Os}}/{{.Architecture}}')" == "linux/amd64" ]] || { echo "finalizer image is not linux/amd64" >&2; exit 2; }

install -d -m 0755 "$APP_ROOT" "$APP_ROOT/releases" /var/lib/magnet-media/compute-inbox
release_link="$APP_ROOT/releases/$release_name"
if [[ "$APP_RELEASE" == "$release_link" ]]; then
  [[ -d "$release_link" && ! -L "$release_link" ]] || { echo "in-place finalizer release must be a real directory" >&2; exit 2; }
else
  if [[ -e "$release_link" && ! -L "$release_link" ]]; then
    echo "finalizer release target exists and is not a symlink" >&2
    exit 2
  fi
  ln -sfn "$APP_RELEASE" "$release_link"
fi
ln -sfn "$release_link" "$APP_LINK"
chmod 0755 "$APP_LINK/deploy/resource-index/linux/run-media-compute-finalizer.sh"

printf 'MAGNET_MEDIA_FINALIZER_IMAGE=%s\nMAGNET_MEDIA_FINALIZER_MODE=%s\nMAGNET_MEDIA_COMPUTE_BASE=http://127.0.0.1:18766\nMAGNET_MEDIA_COMPUTE_INBOX=/var/lib/magnet-media/compute-inbox\n' "$IMAGE" "$FINALIZER_MODE" > "$CONFIG_ROOT/finalizer.env"
chmod 0600 "$CONFIG_ROOT/finalizer.env"

install -m 0644 "$APP_LINK/deploy/resource-index/linux/magnet-media-oracle-outbox-tunnel.service" /etc/systemd/system/magnet-media-oracle-outbox-tunnel.service
install -m 0644 "$APP_LINK/deploy/resource-index/linux/magnet-media-compute-finalizer.service" /etc/systemd/system/magnet-media-compute-finalizer.service
install -m 0644 "$APP_LINK/deploy/resource-index/linux/magnet-media-compute-finalizer.timer" /etc/systemd/system/magnet-media-compute-finalizer.timer
systemctl daemon-reload
systemd-analyze verify \
  /etc/systemd/system/magnet-media-oracle-outbox-tunnel.service \
  /etc/systemd/system/magnet-media-compute-finalizer.service \
  /etc/systemd/system/magnet-media-compute-finalizer.timer
systemctl enable --now magnet-media-oracle-outbox-tunnel.service
if [[ "$ENABLE_FINALIZER_TIMER" == "1" ]]; then
  [[ "$FINALIZER_MODE" == "publish" ]] || { echo "finalizer timer may only be enabled in publish mode" >&2; exit 2; }
  systemctl enable --now magnet-media-compute-finalizer.timer
else
  systemctl disable --now magnet-media-compute-finalizer.timer >/dev/null 2>&1 || true
fi
systemctl is-enabled --quiet magnet-media-daily.timer || { echo "old crawler timer changed unexpectedly" >&2; exit 2; }

printf '%s\n' \
  "MEDIA_ALIYUN_FINALIZER_READY" \
  "image=$IMAGE" \
  "mode=$FINALIZER_MODE" \
  "tunnel=enabled" \
  "finalizer_timer_enabled=$ENABLE_FINALIZER_TIMER" \
  "old_crawler_timer=still_enabled" \
  "production_secrets=remain_on_aliyun"
