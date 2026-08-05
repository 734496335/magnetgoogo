#!/usr/bin/env bash
set -euo pipefail

MODE="${1:?mode is required}"
CID_FILE="/run/magnet-media-${MODE}.cid"

if [[ ! -f "$CID_FILE" ]]; then
  exit 0
fi

CID="$(tr -d '[:space:]' < "$CID_FILE")"
if [[ "$CID" =~ ^[0-9a-f]{12,64}$ ]]; then
  /usr/bin/docker rm -f "$CID" >/dev/null 2>&1 || true
fi
rm -f "$CID_FILE"
