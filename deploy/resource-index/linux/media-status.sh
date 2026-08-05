#!/usr/bin/env bash
set -euo pipefail

STATUS=/var/lib/magnet-media/status/latest-publish.json
SOAK=/var/lib/magnet-media/status/candidate-soak.json
if [[ ! -f "$STATUS" ]]; then
  STATUS=/var/lib/magnet-media/status/latest.json
fi
if [[ ! -f "$STATUS" ]]; then
  echo "status=never_run"
  exit 1
fi
python3 - "$STATUS" "$SOAK" <<'PY'
import json, sys
from pathlib import Path
status = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
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
soak_path = Path(sys.argv[2])
if soak_path.is_file():
    soak = json.loads(soak_path.read_text(encoding="utf-8"))
    for key in (
        "last_status", "last_run_date", "consecutive_days", "ready_for_promotion",
    ):
        if key in soak:
            print(f"soak_{key}={soak[key]}")
PY
systemctl --no-pager --full status magnet-media-daily.timer 2>/dev/null | sed -n '1,12p' || true
systemctl --no-pager --full status magnet-media-audit.timer 2>/dev/null | sed -n '1,12p' || true
