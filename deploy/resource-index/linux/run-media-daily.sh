#!/usr/bin/env bash
set -euo pipefail

IMAGE="${MAGNET_MEDIA_IMAGE:-magnet-media-daily:latest}"
CONFIG="${MAGNET_MEDIA_CONFIG:-/etc/magnet-media/media-daily.json}"
ENV_FILE="${MAGNET_MEDIA_ENV:-/etc/magnet-media/media.env}"
MODE="${1:-${MAGNET_MEDIA_MODE:-candidate}}"
MEMORY="${MAGNET_MEDIA_MEMORY:-768m}"
MEMORY_RESERVATION="${MAGNET_MEDIA_MEMORY_RESERVATION:-512m}"
MEMORY_SWAP="${MAGNET_MEDIA_MEMORY_SWAP:-1280m}"
CPUS="${MAGNET_MEDIA_CPUS:-1.0}"
PIDS_LIMIT="${MAGNET_MEDIA_PIDS_LIMIT:-256}"

args=(media-daily --config "$CONFIG")
case "$MODE" in
  publish) ;;
  candidate) args+=(--no-publish) ;;
  audit) args+=(--skip-crawl --skip-ratings --no-publish) ;;
  force) args+=(--force-publish) ;;
  *) echo "unsupported mode: $MODE" >&2; exit 2 ;;
esac

exec /usr/bin/docker run --rm \
  --name "magnet-media-${MODE}" \
  --network host \
  --memory "$MEMORY" \
  --memory-reservation "$MEMORY_RESERVATION" \
  --memory-swap "$MEMORY_SWAP" \
  --cpus "$CPUS" \
  --pids-limit "$PIDS_LIMIT" \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --stop-timeout 30 \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --env-file "$ENV_FILE" \
  -e TZ=Asia/Shanghai \
  -v /var/lib/magnet-media:/var/lib/magnet-media \
  -v /etc/magnet-media:/etc/magnet-media:ro \
  "$IMAGE" "${args[@]}"
