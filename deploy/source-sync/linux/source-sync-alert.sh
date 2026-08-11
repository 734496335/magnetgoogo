#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-success}"
ALERT_BIN="${MAGNET_ALERT_BIN:-/opt/magnet-alerts/magnet-alert.py}"
PYTHON_BIN="${MAGNET_SOURCE_PYTHON_BIN:-/usr/bin/python3}"
VERIFIER="${MAGNET_SOURCE_VERIFIER:-/opt/magnet-source-sync/verify-source-packs.py}"
TARGET="${MAGNET_SOURCE_TARGET_ROOT:-/var/www/magnetgoogo-site}/sources.enc.json"

[[ -x "$ALERT_BIN" ]] || exit 0

remaining="unknown"
sha="unknown"
if [[ -f "$TARGET" ]]; then
  sha="$(sha256sum "$TARGET" | awk '{print $1}')"
  report="$($PYTHON_BIN "$VERIFIER" --full "$TARGET" --min-remaining-hours 0 2>/dev/null || true)"
  if [[ -n "$report" ]]; then
    remaining="$(printf '%s' "$report" | $PYTHON_BIN -c 'import json,sys; d=json.load(sys.stdin); print(d.get("full",{}).get("remaining_hours","unknown"))' 2>/dev/null || echo unknown)"
  fi
fi

near_expiry=0
if [[ "$remaining" != "unknown" ]]; then
  if "$PYTHON_BIN" - "$remaining" <<'PY'
import sys
try:
    value=float(sys.argv[1])
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if value < 24 else 1)
PY
  then
    near_expiry=1
  fi
fi

if [[ "$MODE" == "failure" ]]; then
  "$ALERT_BIN" failure \
    --key source-sync \
    --threshold 3 \
    --repeat-hours 24 \
    --severity P1 \
    --title "普通版源包连续同步失败" \
    --message "阿里云普通版 sources.enc.json 同步失败。连续3次失败才触发本告警；旧文件保持不变。\nsha=$sha\nremaining_hours=$remaining" || true
else
  "$ALERT_BIN" success \
    --key source-sync \
    --severity P1 \
    --title "普通版源包同步已恢复" \
    --message "阿里云普通版 sources.enc.json 同步当前执行成功。\nsha=$sha\nremaining_hours=$remaining" || true
fi

if (( near_expiry == 1 )); then
  "$ALERT_BIN" failure \
    --key source-expiry \
    --threshold 1 \
    --repeat-hours 12 \
    --severity P0 \
    --title "普通版源包即将过期" \
    --message "当前阿里云 sources.enc.json 剩余有效期不足24小时，需要检查 GitHub 自动续期及分发链。\nsha=$sha\nremaining_hours=$remaining" || true
else
  "$ALERT_BIN" success \
    --key source-expiry \
    --severity P0 \
    --title "普通版源包有效期已恢复" \
    --message "当前阿里云 sources.enc.json 剩余有效期已恢复到安全范围。\nsha=$sha\nremaining_hours=$remaining" || true
fi
