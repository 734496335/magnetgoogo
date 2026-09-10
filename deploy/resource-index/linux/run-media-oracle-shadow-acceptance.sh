#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "run as root on the Oracle media host" >&2
  exit 1
fi

APP_LINK=${APP_LINK:-/opt/magnet-media/app}
CONFIG_ROOT=${CONFIG_ROOT:-/etc/magnet-media}
STATE_ROOT=${STATE_ROOT:-/var/lib/magnet-media}
CONFIG=${MAGNET_MEDIA_CONFIG:-$CONFIG_ROOT/media-daily.json}
ENV_FILE=${MAGNET_MEDIA_ENV:-$CONFIG_ROOT/media.env}
R2_BASE=${R2_BASE:-https://media.magnetgoogo.com}
ALIYUN_BASE=${ALIYUN_BASE:-https://cn.magnetgoogo.com/media}
SOURCE_PROBE_LIMIT=${SOURCE_PROBE_LIMIT:-5}

if [[ $(uname -m) != "aarch64" ]]; then
  echo "Oracle shadow acceptance requires native aarch64" >&2
  exit 2
fi
for required in docker python3 findmnt mountpoint cmp stat; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "required command is missing: $required" >&2
    exit 2
  fi
done
if [[ ! -L "$APP_LINK" && ! -d "$APP_LINK" ]]; then
  echo "Oracle media app link is missing" >&2
  exit 2
fi
release_path=$(readlink -f "$APP_LINK")
if [[ -z "$release_path" || ! -d "$release_path" ]]; then
  echo "Oracle media app release cannot be resolved" >&2
  exit 2
fi
release_name=$(basename "$release_path")
IMAGE=${MAGNET_MEDIA_IMAGE:-magnet-media-daily:oracle-shadow-$release_name}
if [[ ! "$IMAGE" =~ ^[A-Za-z0-9._/@:-]+$ ]]; then
  echo "MAGNET_MEDIA_IMAGE contains unsupported characters" >&2
  exit 2
fi
if [[ ! -f "$CONFIG" || ! -f "$ENV_FILE" ]]; then
  echo "Oracle media config or env file is missing" >&2
  exit 2
fi
if grep -Eq '^R2_UPLOAD_WORKER_TOKEN=.+' "$ENV_FILE"; then
  echo "Oracle shadow acceptance refuses a production R2 upload token" >&2
  exit 2
fi
for required in media-ed25519-private.pem media-ed25519-public.pem media-production-ed25519-public.pem aliyun-media-deploy.key aliyun-known-hosts; do
  if [[ ! -f "$CONFIG_ROOT/$required" ]]; then
    echo "Oracle shadow acceptance prerequisite is missing: $CONFIG_ROOT/$required" >&2
    exit 2
  fi
done
if ! mountpoint -q /data || ! mountpoint -q "$STATE_ROOT"; then
  echo "Oracle data and media state mounts must both be active" >&2
  exit 2
fi
data_source=$(findmnt -n -o SOURCE /data)
state_source=$(findmnt -n -o SOURCE "$STATE_ROOT")
if [[ -z "$data_source" || -z "$state_source" || "$state_source" != "$data_source"* && "$state_source" != /data/* ]]; then
  echo "Oracle media state is not backed by the data volume" >&2
  exit 2
fi
for production_unit in magnet-media-daily.service magnet-media-daily.timer magnet-media-audit.service magnet-media-audit.timer magnet-media-retry.service; do
  if systemctl cat "$production_unit" >/dev/null 2>&1; then
    echo "Oracle shadow acceptance refuses installed production unit: $production_unit" >&2
    exit 2
  fi
done
image_arch=$(docker image inspect "$IMAGE" --format '{{.Architecture}}')
image_os=$(docker image inspect "$IMAGE" --format '{{.Os}}')
if [[ "$image_arch" != "arm64" || "$image_os" != "linux" ]]; then
  echo "Oracle media image is not native linux/arm64: $image_os/$image_arch" >&2
  exit 2
fi

docker run --rm --entrypoint python "$IMAGE" -c 'import boto3,bs4,cryptography,curl_cffi,PIL; print("MEDIA_ARM64_IMPORTS_PASS")'
docker run --rm --entrypoint sh "$IMAGE" -c 'command -v ssh >/dev/null && command -v scp >/dev/null && echo MEDIA_SSH_CLIENT_PASS'

run_stamp=$(date -u +%Y%m%dT%H%M%SZ)
evidence="$STATE_ROOT/oracle-acceptance/$run_stamp"
mkdir -p "$evidence"
chmod 0700 "$evidence"
start_epoch=$(date +%s)

fetch_pointer() {
  local base=$1
  local output=$2
  docker run --rm \
    --network host \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    -v "$STATE_ROOT:$STATE_ROOT" \
    --entrypoint python \
    "$IMAGE" \
    /app/deploy/resource-index/fetch-media-public-pointer.py \
    --base "$base" \
    --output "$output"
}

fetch_pointer "$R2_BASE" "$evidence/r2-before.json"
fetch_pointer "$ALIYUN_BASE" "$evidence/aliyun-before.json"
if ! cmp -s "$evidence/r2-before.json" "$evidence/aliyun-before.json"; then
  echo "R2 and Aliyun pointers diverged before Oracle shadow acceptance" >&2
  exit 2
fi

docker run --rm \
  --network host \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  -v "$STATE_ROOT:$STATE_ROOT" \
  -v "$CONFIG_ROOT:$CONFIG_ROOT:ro" \
  --entrypoint python \
  "$IMAGE" \
  /app/deploy/resource-index/probe-aliyun-media-mirror.py \
  --config "$CONFIG" > "$evidence/aliyun-mirror-probe.json"

docker run --rm \
  --network host \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  -v "$STATE_ROOT:$STATE_ROOT" \
  --entrypoint python \
  "$IMAGE" \
  /app/deploy/resource-index/probe-media-source-chain.py \
  --candidate-limit "$SOURCE_PROBE_LIMIT" \
  --output "$evidence/source-chain.json" > "$evidence/source-chain.stdout.json"

set +e
MAGNET_MEDIA_IMAGE="$IMAGE" MAGNET_MEDIA_CONFIG="$CONFIG" MAGNET_MEDIA_ENV="$ENV_FILE" \
  /usr/bin/bash "$APP_LINK/deploy/resource-index/linux/run-media-daily.sh" candidate \
  > "$evidence/candidate.stdout.log" 2>&1
candidate_rc=$?
set -e

fetch_pointer "$R2_BASE" "$evidence/r2-after.json"
fetch_pointer "$ALIYUN_BASE" "$evidence/aliyun-after.json"
if ! cmp -s "$evidence/r2-before.json" "$evidence/r2-after.json"; then
  echo "R2 current pointer changed during Oracle shadow acceptance" >&2
  exit 2
fi
if ! cmp -s "$evidence/aliyun-before.json" "$evidence/aliyun-after.json"; then
  echo "Aliyun current pointer changed during Oracle shadow acceptance" >&2
  exit 2
fi
if ! cmp -s "$evidence/r2-after.json" "$evidence/aliyun-after.json"; then
  echo "R2 and Aliyun pointers diverged after Oracle shadow acceptance" >&2
  exit 2
fi
if [[ $candidate_rc -ne 0 ]]; then
  echo "Oracle media candidate failed with exit code $candidate_rc; public pointers remained unchanged" >&2
  exit "$candidate_rc"
fi

latest_status="$STATE_ROOT/status/latest.json"
if [[ ! -f "$latest_status" ]]; then
  echo "Oracle media candidate did not write latest status" >&2
  exit 2
fi
status_mtime=$(stat -c %Y "$latest_status")
if (( status_mtime < start_epoch )); then
  echo "Oracle media candidate latest status is stale" >&2
  exit 2
fi
cp "$latest_status" "$evidence/candidate-status.json"
chmod 0600 "$evidence/candidate-status.json"

docker run --rm \
  --network host \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  -v "$STATE_ROOT:$STATE_ROOT" \
  -v "$CONFIG_ROOT:$CONFIG_ROOT:ro" \
  --entrypoint python \
  "$IMAGE" \
  /app/deploy/resource-index/verify-media-oracle-candidate.py \
  --status "$evidence/candidate-status.json" \
  --config "$CONFIG" \
  --r2-before "$evidence/r2-before.json" \
  --r2-after "$evidence/r2-after.json" \
  --aliyun-before "$evidence/aliyun-before.json" \
  --aliyun-after "$evidence/aliyun-after.json" \
  --output "$evidence/acceptance.json" > "$evidence/acceptance.stdout.json"

printf '%s\n' \
  "ORACLE_MEDIA_SHADOW_ACCEPTANCE_PASS" \
  "release=$release_name" \
  "image=$IMAGE" \
  "evidence=$evidence" \
  "source_probe=pass" \
  "candidate=pass" \
  "public_pointer_unchanged=pass" \
  "production_units=absent" \
  "r2_token=absent"
