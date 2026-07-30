#!/usr/bin/env bash
set -euo pipefail

STATUS=/var/lib/magnet-media/status/latest.json
if [[ ! -f "$STATUS" ]]; then
  echo "status=never_run"
  exit 1
fi
python3 - "$STATUS" <<'PY'
import json, sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key in (
    "status", "started_at", "finished_at", "published", "no_change",
    "movie_count", "series_count", "resource_count", "current_revision", "release_id",
):
    if key in value:
        print(f"{key}={value[key]}")
error = value.get("error")
if isinstance(error, dict):
    print(f"error_code={error.get('error_code')}")
    print(f"error={error.get('message')}")
PY
systemctl --no-pager --full status magnet-media-daily.timer | sed -n '1,12p'
