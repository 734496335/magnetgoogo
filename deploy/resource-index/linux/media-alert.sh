#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-success}"
ALERT_BIN="${MAGNET_ALERT_BIN:-/opt/magnet-alerts/magnet-alert.py}"
STATUS="${MAGNET_MEDIA_STATUS_FILE:-/var/lib/magnet-media/status/latest-publish.json}"
PYTHON_BIN="${MAGNET_MEDIA_ALERT_PYTHON:-/usr/bin/python3}"
STATE_FILE="${MAGNET_MEDIA_ALERT_STATE:-/var/lib/magnet-alerts/media-publish.json}"
FRESHNESS_STATE_FILE="${MAGNET_MEDIA_FRESHNESS_ALERT_STATE:-/var/lib/magnet-alerts/media-source-freshness.json}"
REDUNDANCY_STATE_FILE="${MAGNET_MEDIA_REDUNDANCY_ALERT_STATE:-/var/lib/magnet-alerts/media-source-redundancy.json}"

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
    "quality_status=%s" % (value.get("quality_status") or "unknown"),
    "degraded_sources=%s" % ",".join(value.get("degraded_sources") or []),
    "required_degraded_sources=%s" % ",".join(value.get("required_degraded_sources") or []),
    "failed_freshness_groups=%s" % ",".join(value.get("failed_freshness_groups") or []),
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

DEGRADED_SOURCES="$($PYTHON_BIN - "$STATUS" <<'PY'
import json, sys
from pathlib import Path
try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    value = {}
items = value.get("degraded_sources")
if isinstance(items, list):
    print(",".join(str(item) for item in items if str(item)))
PY
)"

FRESHNESS_BLOCKED="$($PYTHON_BIN - "$STATUS" <<'PY'
import json, sys
from pathlib import Path
try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    value = {}
required = value.get("required_degraded_sources") if isinstance(value.get("required_degraded_sources"), list) else []
groups = value.get("failed_freshness_groups") if isinstance(value.get("failed_freshness_groups"), list) else []
items = [str(item) for item in required + groups if str(item)]
print(",".join(items))
PY
)"

case "$MODE" in
  failure)
    "$ALERT_BIN" failure \
      --key media-publish \
      --state-file "$STATE_FILE" \
      --threshold 1 \
      --repeat-hours 24 \
      --severity P0 \
      --title "影视自动发布二次失败" \
      --message "每日影视发布首次失败后已自动重试，重试仍失败。生产 current 保持旧 revision，未强行晋级。\n$DETAIL" || true
    ;;
  success)
    if [[ -n "$FRESHNESS_BLOCKED" ]]; then
      "$ALERT_BIN" success \
        --key media-source-redundancy \
        --state-file "$REDUNDANCY_STATE_FILE" \
        --severity P2 \
        --title "影视资源冗余告警已升级" \
        --message "影视源降级已升级为 freshness 发布门禁失败。\n$DETAIL" || true
      "$ALERT_BIN" failure \
        --key media-source-freshness \
        --state-file "$FRESHNESS_STATE_FILE" \
        --threshold 1 \
        --repeat-hours 24 \
        --severity P1 \
        --title "影视 freshness 门禁持续降级" \
        --message "影视 freshness 门禁未满足：必需单源或冗余组新鲜源数量不足。生产 current 保持上一稳定 revision，未强行晋级。\n$DETAIL" || true
    elif [[ -n "$DEGRADED_SOURCES" ]]; then
      "$ALERT_BIN" success \
        --key media-source-freshness \
        --state-file "$FRESHNESS_STATE_FILE" \
        --severity P1 \
        --title "影视 freshness 门禁已恢复" \
        --message "影视 freshness 发布门禁当前满足。\n$DETAIL" || true
      "$ALERT_BIN" failure \
        --key media-source-redundancy \
        --state-file "$REDUNDANCY_STATE_FILE" \
        --threshold 1 \
        --repeat-hours 24 \
        --severity P2 \
        --title "影视资源冗余降级" \
        --message "至少一个影视源仍处于 degraded，但 freshness quorum 仍满足，发布继续。请修复降级源以恢复冗余余量。\n$DETAIL" || true
    else
      "$ALERT_BIN" success \
        --key media-source-freshness \
        --state-file "$FRESHNESS_STATE_FILE" \
        --severity P1 \
        --title "影视 freshness 门禁已恢复" \
        --message "影视必需单源与 freshness 冗余组当前均满足发布门禁。\n$DETAIL" || true
      "$ALERT_BIN" success \
        --key media-source-redundancy \
        --state-file "$REDUNDANCY_STATE_FILE" \
        --severity P2 \
        --title "影视资源冗余已恢复" \
        --message "影视源当前均未处于 degraded，冗余余量已恢复。\n$DETAIL" || true
    fi
    "$ALERT_BIN" success \
      --key media-publish \
      --state-file "$STATE_FILE" \
      --severity P0 \
      --title "影视自动发布已恢复" \
      --message "影视自动发布当前执行成功，R2/Aliyun 正常路径已恢复。\n$DETAIL" || true
    ;;
  *)
    echo "unsupported media alert mode: $MODE" >&2
    exit 2
    ;;
esac
