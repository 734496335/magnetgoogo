#!/usr/bin/env bash
set -euo pipefail

MODE="${1:?mode is required}"
CID_FILE="/run/magnet-media-${MODE}.cid"

if [[ ! -f "$CID_FILE" ]]; then
  exit 0
fi

CID="$(tr -d '[:space:]' < "$CID_FILE")"
LOCK=/var/lib/magnet-media/locks/media-daily.lock
if [[ "$CID" =~ ^[0-9a-f]{12,64}$ ]]; then
  OWNER=""
  if [[ -f "$LOCK" ]]; then
    OWNER="$(awk -F= '$1 == "hostname" {print $2; exit}' "$LOCK")"
  fi
  /usr/bin/docker rm -f "$CID" >/dev/null 2>&1 || true
  SHORT_CID="${CID:0:12}"
  if [[ -n "$OWNER" && ( "$OWNER" == "$SHORT_CID" || "$SHORT_CID" == "$OWNER" ) ]]; then
    rm -f "$LOCK"
  fi
fi
rm -f "$CID_FILE"
