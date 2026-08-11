#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-success}"
ALERT_BIN="${MAGNET_ALERT_BIN:-/opt/magnet-alerts/magnet-alert.py}"
STATUS="${MAGNET_MEDIA_STATUS_FILE:-/var/lib/magnet-media/status/latest-publish.json}"
PYTHON_BIN="${MAGNET_MEDIA_ALERT_PYTHON:-/usr/bin/python3}"

[[ -x "$ALERT_BIN" ]] || exit 0

DETAIL="$($PYTHON_BIN - "$STATUS" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    value = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    value = {}
error = value.get("error") if isinstance(value.get("error"), dict) else {}
parts = [
    "run_id=%s" % (value.get("run_id") or "unknown"),
    "revision=%s" % (value.get("current_revision") or value.get("previous_revision") or "unknown"),
    "release=%s" % (value.get("release_id") or "unknown"),
    "movies=%s" % (value.get("movie_count") if value.get("movie_count") is not None else "unknown"),
    "series=%s" % (value.get("series_count") if value.get("series_count") is not None else "unknown"),
    "resources=%s" % (value.get("resource_count") if value.get("resource_count") is not None else "unknown"),
]
if error:
    parts.append("error_code=%s" % (error.get("error_code") or "unknown"))
    parts.append("error=%s" % str(error.get("message") or error.get("type") or "unknown")[:500])
print("\n".join(parts))
PY
)"

case "$MODE" in
  failure)
    "$ALERT_BIN" failure \
      --key media-publish \
      --threshold 1 \
      --repeat-hours 24 \
      --severity P0 \
      --title "影视自动发布二次失败" \
      --message "每日影视发布首次失败后已自动重试，重试仍失败。生产 current 保持旧 revision，未强行晋级。\n$DETAIL" || true
    ;;
  success)
    "$ALERT_BIN" success \
      --key media-publish \
      --severity P0 \
      --title "影视自动发布已恢复" \
      --message "影视自动发布当前执行成功，R2/Aliyun 正常路径已恢复。\n$DETAIL" || true
    ;;
  *)
    echo "unsupported media alert mode: $MODE" >&2
    exit 2
    ;;
esac
