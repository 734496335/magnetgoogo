#!/usr/bin/env bash
set -euo pipefail

SOAK=/var/lib/magnet-media/status/candidate-soak.json
FINALIZER_STATUS=/var/lib/magnet-media/status/latest-compute-finalizer-publish.json
COMPUTE_AUDIT_STATUS=/var/lib/magnet-media/status/latest-compute-audit.json
LEGACY_STATUS=/var/lib/magnet-media/status/latest-publish.json
[[ -f "$LEGACY_STATUS" ]] || LEGACY_STATUS=/var/lib/magnet-media/status/latest.json

if systemctl is-enabled --quiet magnet-media-compute-finalizer.timer 2>/dev/null || [[ -f "$FINALIZER_STATUS" ]]; then
  STATUS=$FINALIZER_STATUS
  ARCHITECTURE=oracle-compute-finalizer
else
  STATUS=$LEGACY_STATUS
  ARCHITECTURE=legacy-aliyun-daily
fi

if [[ ! -f "$STATUS" ]]; then
  echo "architecture=$ARCHITECTURE"
  echo "status=never_run"
  exit 1
fi

python3 - "$STATUS" "$SOAK" "$COMPUTE_AUDIT_STATUS" "$ARCHITECTURE" <<'PY'
import json, sys
from pathlib import Path

status_path = Path(sys.argv[1])
soak_path = Path(sys.argv[2])
audit_path = Path(sys.argv[3])
architecture = sys.argv[4]
status = json.loads(status_path.read_text(encoding="utf-8"))
print(f"architecture={architecture}")
print(f"status_file={status_path}")

if status.get("schema_version") == "media-compute-finalizer-status/1":
    print(f"status={status.get('status')}")
    print(f"mode={status.get('mode')}")
    print(f"started_at={status.get('started_at')}")
    print(f"finished_at={status.get('finished_at')}")
    print(f"package={status.get('package')}")
    result = status.get("result") or {}
    for key in (
        "compute_run_id", "current_revision", "candidate_revision", "release_id",
        "published", "no_change", "already_finalized",
    ):
        if key in result:
            print(f"{key}={result[key]}")
    error = status.get("error")
    if isinstance(error, dict):
        print(f"error_code={error.get('error_code')}")
        print(f"error={error.get('message')}")
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        print(f"compute_audit_status={audit.get('status')}")
        print(f"compute_audit_finished_at={audit.get('finished_at')}")
        audit_error = audit.get("error")
        if isinstance(audit_error, dict):
            print(f"compute_audit_error_code={audit_error.get('error_code')}")
            print(f"compute_audit_error={audit_error.get('message')}")
else:
    for key in (
        "mode", "status", "started_at", "finished_at", "published", "publish_candidate",
        "candidate_verified", "public_verified", "no_change", "movie_count", "series_count", "resource_count",
        "previous_revision", "candidate_revision", "current_revision", "release_id",
    ):
        if key in status:
            print(f"{key}={status[key]}")
    maintenance = (status.get("stages") or {}).get("maintenance") or {}
    disk = maintenance.get("disk") or {}
    for key in ("used_percent", "free_bytes", "max_used_percent", "min_free_bytes"):
        if key in disk:
            print(f"disk_{key}={disk[key]}")
    lock = maintenance.get("lock") or {}
    if lock.get("stale_lock_recovered"):
        print(f"stale_lock_recovered={lock.get('stale_lock_reason')}")
    error = status.get("error")
    if isinstance(error, dict):
        print(f"error_code={error.get('error_code')}")
        print(f"error={error.get('message')}")

if architecture == "legacy-aliyun-daily" and soak_path.is_file():
    soak = json.loads(soak_path.read_text(encoding="utf-8"))
    for key in ("last_status", "last_run_date", "consecutive_days", "ready_for_promotion"):
        if key in soak:
            print(f"soak_{key}={soak[key]}")
PY

if [[ "$ARCHITECTURE" == "oracle-compute-finalizer" ]]; then
  systemctl --no-pager --full status magnet-media-compute-finalizer.timer 2>/dev/null | sed -n '1,12p' || true
  systemctl --no-pager --full status magnet-media-compute-audit.timer 2>/dev/null | sed -n '1,12p' || true
else
  systemctl --no-pager --full status magnet-media-daily.timer 2>/dev/null | sed -n '1,12p' || true
  systemctl --no-pager --full status magnet-media-audit.timer 2>/dev/null | sed -n '1,12p' || true
fi
