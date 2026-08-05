#!/usr/bin/env bash
set -euo pipefail

DELAY="${MAGNET_MEDIA_RETRY_DELAY:-30m}"
STATUS=/var/lib/magnet-media/status/latest-publish.json
FAILED_AT="$(/usr/bin/systemctl show magnet-media-daily.service -p ExecMainExitTimestamp --value)"
FAILED_EPOCH="$(date -d "$FAILED_AT" +%s 2>/dev/null || date +%s)"

sleep "$DELAY"

if [[ -f "$STATUS" ]]; then
  readarray -t VALUES < <(python3 - "$STATUS" <<'PY'
import json, sys
from pathlib import Path
try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    value = {}
print(value.get("status") or "")
print(value.get("finished_at") or "")
PY
)
  if [[ "${VALUES[0]:-}" == "success" && -n "${VALUES[1]:-}" ]]; then
    SUCCESS_EPOCH="$(date -d "${VALUES[1]}" +%s 2>/dev/null || echo 0)"
    if (( SUCCESS_EPOCH >= FAILED_EPOCH )); then
      echo "media publish already recovered after the recorded failure"
      exit 0
    fi
  fi
fi

exec /usr/bin/systemctl start magnet-media-daily.service
