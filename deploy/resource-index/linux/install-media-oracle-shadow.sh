#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DEFAULT_APP_RELEASE=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
APP_RELEASE=${APP_RELEASE:-$DEFAULT_APP_RELEASE}
DATA_ROOT=${DATA_ROOT:-/data/magnet-media}
STATE_SOURCE=${STATE_SOURCE:-$DATA_ROOT/state}
APP_LINK=${APP_LINK:-/opt/magnet-media/app}
CONFIG_ROOT=${CONFIG_ROOT:-/etc/magnet-media}
ALLOW_R2_TOKEN=${ALLOW_R2_TOKEN:-0}
ALIYUN_IDENTITY_SOURCE=${ALIYUN_IDENTITY_SOURCE:-/home/ubuntu/.ssh/aliyun-media-deploy}
ALIYUN_KNOWN_HOSTS_SOURCE=${ALIYUN_KNOWN_HOSTS_SOURCE:-/home/ubuntu/.ssh/aliyun-known-hosts}

if [[ ! -d "$APP_RELEASE" ]]; then
  echo "APP_RELEASE must point to an existing immutable media release" >&2
  exit 2
fi
release_name=$(basename "$APP_RELEASE")
if [[ ! "$release_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "release directory name is unsafe: $release_name" >&2
  exit 2
fi
IMAGE=${MAGNET_MEDIA_IMAGE:-magnet-media-daily:oracle-shadow-$release_name}
if [[ ! "$IMAGE" =~ ^[A-Za-z0-9._/@:-]+$ ]]; then
  echo "MAGNET_MEDIA_IMAGE contains unsupported characters" >&2
  exit 2
fi
for required_path in \
  "$APP_RELEASE/deploy/resource-index/linux/Dockerfile" \
  "$APP_RELEASE/deploy/resource-index/linux/media-daily.oracle.example.json" \
  "$APP_RELEASE/deploy/resource-index/linux/magnet-media-oracle-shadow.service" \
  "$APP_RELEASE/deploy/resource-index/linux/run-media-daily.sh" \
  "$APP_RELEASE/deploy/resource-index/linux/cleanup-media-container.sh"; do
  if [[ ! -f "$required_path" ]]; then
    echo "required release file is missing: $required_path" >&2
    exit 2
  fi
done

if ! mountpoint -q /data; then
  echo "/data must already be a mounted data volume" >&2
  exit 2
fi
root_source=$(findmnt -n -o SOURCE /)
data_source=$(findmnt -n -o SOURCE /data)
if [[ -z "$data_source" || "$data_source" == "$root_source" ]]; then
  echo "/data must be backed by a separate mounted volume" >&2
  exit 2
fi
state_canonical=$(realpath -m "$STATE_SOURCE")
case "$state_canonical" in
  /data/*) ;;
  *)
    echo "STATE_SOURCE must remain under /data: $state_canonical" >&2
    exit 2
    ;;
esac
if [[ -d /var/lib/magnet-media ]] && ! mountpoint -q /var/lib/magnet-media; then
  if find /var/lib/magnet-media -mindepth 1 -print -quit | grep -q .; then
    echo "/var/lib/magnet-media is non-empty and not a mountpoint; refusing to hide existing data" >&2
    exit 2
  fi
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "required Oracle shadow image is missing; run build-media-oracle-image.sh first: $IMAGE" >&2
  exit 2
fi
image_arch=$(docker image inspect "$IMAGE" --format '{{.Architecture}}')
image_os=$(docker image inspect "$IMAGE" --format '{{.Os}}')
if [[ "$image_arch" != "arm64" || "$image_os" != "linux" ]]; then
  echo "Oracle media image is not native linux/arm64: $image_os/$image_arch" >&2
  exit 2
fi
docker run --rm --entrypoint python "$IMAGE" -c 'import boto3,bs4,cryptography,curl_cffi,PIL; print("MEDIA_ARM64_IMPORTS_PASS")'
docker run --rm --entrypoint sh "$IMAGE" -c 'command -v ssh >/dev/null && command -v scp >/dev/null && echo MEDIA_SSH_CLIENT_PASS'

for production_unit in \
  magnet-media-daily.service \
  magnet-media-daily.timer \
  magnet-media-audit.service \
  magnet-media-audit.timer \
  magnet-media-retry.service; do
  if systemctl cat "$production_unit" >/dev/null 2>&1; then
    echo "shadow install refuses an existing production media unit: $production_unit" >&2
    exit 2
  fi
done
if systemctl is-active --quiet magnet-media-oracle-shadow.service; then
  echo "Oracle shadow service is already active; refusing installation mutation" >&2
  exit 2
fi

for secret_path in \
  "$CONFIG_ROOT/media-ed25519-private.pem" \
  "$CONFIG_ROOT/media-ed25519-public.pem" \
  "$CONFIG_ROOT/media-production-ed25519-public.pem" \
  "$ALIYUN_IDENTITY_SOURCE" \
  "$ALIYUN_KNOWN_HOSTS_SOURCE"; do
  if [[ ! -f "$secret_path" ]]; then
    echo "required staged credential/material is missing: $secret_path" >&2
    exit 2
  fi
done
if [[ "$ALLOW_R2_TOKEN" != "1" && -f "$CONFIG_ROOT/media.env" ]] && grep -Eq '^R2_UPLOAD_WORKER_TOKEN=.+' "$CONFIG_ROOT/media.env"; then
  echo "shadow install refuses a production R2 upload token; set ALLOW_R2_TOKEN=1 only at final cutover" >&2
  exit 2
fi

install -d -m 0755 "$DATA_ROOT" "$STATE_SOURCE" /var/lib/magnet-media /opt/magnet-media /opt/magnet-media/releases
release_link="/opt/magnet-media/releases/$release_name"
if [[ -e "$release_link" && ! -L "$release_link" ]]; then
  echo "release link target already exists and is not a symlink: $release_link" >&2
  exit 2
fi
ln -sfn "$APP_RELEASE" "$release_link"
ln -sfn "$release_link" "$APP_LINK"
chmod 0755 \
  "$APP_LINK/deploy/resource-index/linux/run-media-daily.sh" \
  "$APP_LINK/deploy/resource-index/linux/cleanup-media-container.sh" \
  "$APP_LINK/deploy/resource-index/linux/retry-media-daily.sh" \
  "$APP_LINK/deploy/resource-index/linux/media-alert.sh" \
  "$APP_LINK/deploy/resource-index/linux/media-status.sh"

install -d -m 0700 "$CONFIG_ROOT"
if [[ ! -f "$CONFIG_ROOT/media-daily.json" ]]; then
  install -m 0600 "$APP_RELEASE/deploy/resource-index/linux/media-daily.oracle.example.json" "$CONFIG_ROOT/media-daily.json"
fi
if [[ ! -f "$CONFIG_ROOT/media.env" ]]; then
  printf '%s\n' '# Shadow mode intentionally has no production R2 upload token.' > "$CONFIG_ROOT/media.env"
fi
install -m 0600 "$ALIYUN_IDENTITY_SOURCE" "$CONFIG_ROOT/aliyun-media-deploy.key"
install -m 0600 "$ALIYUN_KNOWN_HOSTS_SOURCE" "$CONFIG_ROOT/aliyun-known-hosts"
printf 'MAGNET_MEDIA_IMAGE=%s\n' "$IMAGE" > "$CONFIG_ROOT/runtime.env"
chmod 0600 \
  "$CONFIG_ROOT/media-daily.json" \
  "$CONFIG_ROOT/media.env" \
  "$CONFIG_ROOT/runtime.env" \
  "$CONFIG_ROOT/media-ed25519-private.pem" \
  "$CONFIG_ROOT/aliyun-media-deploy.key" \
  "$CONFIG_ROOT/aliyun-known-hosts"
chmod 0644 "$CONFIG_ROOT/media-ed25519-public.pem" "$CONFIG_ROOT/media-production-ed25519-public.pem"
if [[ "$ALLOW_R2_TOKEN" != "1" ]] && grep -Eq '^R2_UPLOAD_WORKER_TOKEN=.+' "$CONFIG_ROOT/media.env"; then
  echo "shadow install refuses a production R2 upload token after config staging" >&2
  exit 2
fi

mount_unit=$(systemd-escape -p --suffix=mount /var/lib/magnet-media)
mount_unit_path="/etc/systemd/system/$mount_unit"
service_path=/etc/systemd/system/magnet-media-oracle-shadow.service
cat > "$mount_unit_path" <<EOF
[Unit]
Description=MagnetGoogo media state bind mount on Oracle data volume
RequiresMountsFor=/data
Before=magnet-media-oracle-shadow.service magnet-media-daily.service magnet-media-audit.service

[Mount]
What=$STATE_SOURCE
Where=/var/lib/magnet-media
Type=none
Options=bind

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "$mount_unit_path"
install -m 0644 "$APP_LINK/deploy/resource-index/linux/magnet-media-oracle-shadow.service" "$service_path"
systemctl daemon-reload
if ! systemd-analyze verify "$mount_unit_path" "$service_path"; then
  rm -f "$mount_unit_path" "$service_path"
  systemctl daemon-reload
  echo "Oracle media systemd unit verification failed" >&2
  exit 2
fi
systemctl enable --now "$mount_unit"
mounted_source=$(findmnt -n -o SOURCE /var/lib/magnet-media)
if [[ "$mounted_source" != "$data_source"* && "$mounted_source" != "$STATE_SOURCE" ]]; then
  echo "/var/lib/magnet-media is not backed by the Oracle data volume" >&2
  exit 2
fi
systemctl disable magnet-media-oracle-shadow.service >/dev/null 2>&1 || true
if systemctl is-active --quiet magnet-media-oracle-shadow.service; then
  echo "Oracle shadow service must remain inactive until explicitly started for validation" >&2
  exit 2
fi

printf '%s\n' \
  "MEDIA_ORACLE_SHADOW_READY" \
  "app=$APP_LINK" \
  "state=/var/lib/magnet-media" \
  "state_backing=$STATE_SOURCE" \
  "image=$IMAGE" \
  "image_arch=$image_arch" \
  "image_os=$image_os" \
  "shadow_service=installed_inactive" \
  "production_units=not_installed" \
  "nginx=untouched" \
  "r2_token_allowed=$ALLOW_R2_TOKEN"
