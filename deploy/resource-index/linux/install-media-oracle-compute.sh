#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
APP_RELEASE=${APP_RELEASE:-$(cd -- "$SCRIPT_DIR/../../.." && pwd)}
DATA_ROOT=${DATA_ROOT:-/data/magnet-media}
STATE_SOURCE=${STATE_SOURCE:-$DATA_ROOT/state}
APP_LINK=${APP_LINK:-/opt/magnet-media/app}
CONFIG_ROOT=${CONFIG_ROOT:-/etc/magnet-media}
release_name=$(basename "$APP_RELEASE")
IMAGE=${MAGNET_MEDIA_IMAGE:-magnet-media-daily:oracle-compute-$release_name}
ENABLE_COMPUTE_TIMER=${ENABLE_COMPUTE_TIMER:-0}

if [[ ! "$release_name" =~ ^[A-Za-z0-9._-]+$ || ! -d "$APP_RELEASE" ]]; then
  echo "invalid APP_RELEASE" >&2
  exit 2
fi
for path in \
  "$APP_RELEASE/deploy/resource-index/linux/media-daily.oracle-compute.example.json" \
  "$APP_RELEASE/deploy/resource-index/linux/media-production-ed25519-public.pem" \
  "$APP_RELEASE/deploy/resource-index/linux/magnet-media-oracle-compute.service" \
  "$APP_RELEASE/deploy/resource-index/linux/magnet-media-oracle-compute.timer" \
  "$APP_RELEASE/deploy/resource-index/linux/magnet-media-oracle-outbox.service" \
  "$APP_RELEASE/deploy/resource-index/linux/run-media-daily.sh"; do
  [[ -f "$path" ]] || { echo "missing required release file: $path" >&2; exit 2; }
done
mountpoint -q /data || { echo "/data is not mounted" >&2; exit 2; }
root_source=$(findmnt -n -o SOURCE /)
data_source=$(findmnt -n -o SOURCE /data)
[[ -n "$data_source" && "$data_source" != "$root_source" ]] || { echo "/data must be a separate volume" >&2; exit 2; }
case "$(realpath -m "$STATE_SOURCE")" in /data/*) ;; *) echo "STATE_SOURCE must remain under /data" >&2; exit 2;; esac
if [[ -d /var/lib/magnet-media ]] && ! mountpoint -q /var/lib/magnet-media && find /var/lib/magnet-media -mindepth 1 -print -quit | grep -q .; then
  echo "refusing to hide existing /var/lib/magnet-media data" >&2
  exit 2
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  fallback="magnet-media-daily:oracle-shadow-$release_name"
  docker image inspect "$fallback" >/dev/null 2>&1 || { echo "Oracle ARM64 media image is missing" >&2; exit 2; }
  docker tag "$fallback" "$IMAGE"
fi
[[ "$(docker image inspect "$IMAGE" --format '{{.Os}}/{{.Architecture}}')" == "linux/arm64" ]] || { echo "media image is not linux/arm64" >&2; exit 2; }
docker run --rm --entrypoint python "$IMAGE" -c 'import boto3,bs4,cryptography,curl_cffi,PIL; print("MEDIA_ARM64_IMPORTS_PASS")'
for unit in magnet-media-daily.service magnet-media-daily.timer magnet-media-audit.service magnet-media-audit.timer magnet-media-retry.service; do
  if systemctl cat "$unit" >/dev/null 2>&1; then
    echo "Oracle compute install refuses production Aliyun-style unit: $unit" >&2
    exit 2
  fi
done

install -d -m 0755 "$DATA_ROOT" "$STATE_SOURCE" /var/lib/magnet-media /opt/magnet-media /opt/magnet-media/releases
chown -R root:root "$STATE_SOURCE"
ln -sfn "$APP_RELEASE" "/opt/magnet-media/releases/$release_name"
ln -sfn "/opt/magnet-media/releases/$release_name" "$APP_LINK"
install -d -m 0700 "$CONFIG_ROOT"
install -m 0600 "$APP_RELEASE/deploy/resource-index/linux/media-daily.oracle-compute.example.json" "$CONFIG_ROOT/media-daily.json"
install -m 0644 "$APP_RELEASE/deploy/resource-index/linux/media-production-ed25519-public.pem" "$CONFIG_ROOT/media-production-ed25519-public.pem"
printf '%s\n' '# Oracle compute has no R2 production token.' > "$CONFIG_ROOT/media.env"
printf 'MAGNET_MEDIA_IMAGE=%s\n' "$IMAGE" > "$CONFIG_ROOT/runtime.env"
chmod 0600 "$CONFIG_ROOT/media-daily.json" "$CONFIG_ROOT/media.env" "$CONFIG_ROOT/runtime.env"
if grep -Eq '^R2_UPLOAD_WORKER_TOKEN=.+' "$CONFIG_ROOT/media.env"; then
  echo "Oracle compute must not contain an R2 production token" >&2
  exit 2
fi

mount_unit=$(systemd-escape -p --suffix=mount /var/lib/magnet-media)
mount_unit_path="/etc/systemd/system/$mount_unit"
cat > "$mount_unit_path" <<EOF
[Unit]
Description=MagnetGoogo media state bind mount on Oracle data volume
RequiresMountsFor=/data
Before=magnet-media-oracle-compute.service magnet-media-oracle-outbox.service

[Mount]
What=$STATE_SOURCE
Where=/var/lib/magnet-media
Type=none
Options=bind

[Install]
WantedBy=multi-user.target
EOF
install -m 0644 "$APP_LINK/deploy/resource-index/linux/magnet-media-oracle-compute.service" /etc/systemd/system/magnet-media-oracle-compute.service
install -m 0644 "$APP_LINK/deploy/resource-index/linux/magnet-media-oracle-compute.timer" /etc/systemd/system/magnet-media-oracle-compute.timer
install -m 0644 "$APP_LINK/deploy/resource-index/linux/magnet-media-oracle-outbox.service" /etc/systemd/system/magnet-media-oracle-outbox.service
systemctl daemon-reload
systemd-analyze verify "$mount_unit_path" /etc/systemd/system/magnet-media-oracle-compute.service /etc/systemd/system/magnet-media-oracle-compute.timer /etc/systemd/system/magnet-media-oracle-outbox.service
systemctl enable --now "$mount_unit"
systemctl enable --now magnet-media-oracle-outbox.service
if [[ "$ENABLE_COMPUTE_TIMER" == "1" ]]; then
  systemctl enable --now magnet-media-oracle-compute.timer
else
  systemctl disable --now magnet-media-oracle-compute.timer >/dev/null 2>&1 || true
fi
[[ "$(findmnt -n -o SOURCE /var/lib/magnet-media)" == "$data_source"* || "$(findmnt -n -o SOURCE /var/lib/magnet-media)" == "$STATE_SOURCE" ]] || { echo "media state is not backed by /data" >&2; exit 2; }
printf '%s\n' "MEDIA_ORACLE_COMPUTE_READY" "image=$IMAGE" "state_backing=$STATE_SOURCE" "outbox=127.0.0.1:18766" "compute_timer_enabled=$ENABLE_COMPUTE_TIMER" "production_secrets=none"
