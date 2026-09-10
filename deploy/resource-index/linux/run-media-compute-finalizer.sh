#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=${APP_ROOT:-/opt/magnet-media-finalizer/app}
CONFIG=${MAGNET_MEDIA_CONFIG:-/etc/magnet-media/media-daily.json}
ENV_FILE=${MAGNET_MEDIA_ENV:-/etc/magnet-media/media.env}
INBOX=${MAGNET_MEDIA_COMPUTE_INBOX:-/var/lib/magnet-media/compute-inbox}
BASE=${MAGNET_MEDIA_COMPUTE_BASE:-http://127.0.0.1:18766}
IMAGE=${MAGNET_MEDIA_FINALIZER_IMAGE:-magnet-media-finalizer:latest}
MODE=${MAGNET_MEDIA_FINALIZER_MODE:-candidate}

case "$MODE" in
  candidate|publish|force) ;;
  *) echo "unsupported finalizer mode: $MODE" >&2; exit 2 ;;
esac
[[ -f "$CONFIG" ]] || { echo "missing media config: $CONFIG" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "missing media env: $ENV_FILE" >&2; exit 2; }
[[ -f "$APP_ROOT/deploy/resource-index/fetch-media-compute-handoff.py" ]] || { echo "missing compute fetcher" >&2; exit 2; }
[[ -f "$APP_ROOT/deploy/resource-index/finalize-media-compute.py" ]] || { echo "missing compute finalizer" >&2; exit 2; }
mkdir -p "$INBOX"

/usr/bin/python3.11 "$APP_ROOT/deploy/resource-index/fetch-media-compute-handoff.py" \
  --base "$BASE" \
  --output-dir "$INBOX"
package_name=$(/usr/bin/python3.11 -c 'import json,sys; from pathlib import Path; p=json.loads((Path(sys.argv[1])/"current.json").read_text()); print(Path(p["package"]).name)' "$INBOX")
package="$INBOX/$package_name"
[[ -f "$package" ]] || { echo "downloaded compute handoff is missing: $package" >&2; exit 2; }

args=(--config "$CONFIG" --package "$package")
if [[ "$MODE" == "publish" || "$MODE" == "force" ]]; then
  args+=(--publish)
fi
if [[ "$MODE" == "force" ]]; then
  args+=(--force-publish)
fi

exec /usr/bin/docker run --rm \
  --name magnet-media-compute-finalizer \
  --network host \
  --memory 768m \
  --memory-reservation 384m \
  --memory-swap 1280m \
  --cpus 1.0 \
  --pids-limit 256 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --env-file "$ENV_FILE" \
  -e TZ=Asia/Shanghai \
  -v /var/lib/magnet-media:/var/lib/magnet-media \
  -v /etc/magnet-media:/etc/magnet-media:ro \
  --entrypoint python \
  "$IMAGE" \
  /app/deploy/resource-index/finalize-media-compute.py "${args[@]}"
