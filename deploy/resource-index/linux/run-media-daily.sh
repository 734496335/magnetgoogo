#!/usr/bin/env bash
set -euo pipefail

IMAGE="${MAGNET_MEDIA_IMAGE:-magnet-media-daily:latest}"
CONFIG="${MAGNET_MEDIA_CONFIG:-/etc/magnet-media/media-daily.json}"
ENV_FILE="${MAGNET_MEDIA_ENV:-/etc/magnet-media/media.env}"
MODE="${1:-publish}"

args=(media-daily --config "$CONFIG")
case "$MODE" in
  publish) ;;
  candidate) args+=(--no-publish) ;;
  audit) args+=(--skip-crawl --no-publish) ;;
  force) args+=(--force-publish) ;;
  *) echo "unsupported mode: $MODE" >&2; exit 2 ;;
esac

exec /usr/bin/docker run --rm \
  --name magnet-media-daily \
  --network host \
  --memory 1500m \
  --cpus 1.75 \
  --env-file "$ENV_FILE" \
  -e TZ=Asia/Shanghai \
  -v /var/lib/magnet-media:/var/lib/magnet-media \
  -v /etc/magnet-media:/etc/magnet-media:ro \
  "$IMAGE" "${args[@]}"
