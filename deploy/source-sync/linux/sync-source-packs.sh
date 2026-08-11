#!/usr/bin/env bash
set -euo pipefail

AUTHORITY_BASE="${MAGNET_SOURCE_AUTHORITY_BASE:-https://magnetgoogo.com}"
CDN_BASE="${MAGNET_SOURCE_CDN_BASE:-https://cdn.jsdelivr.net/gh/734496335/mg-data@main}"
TARGET_ROOT="${MAGNET_SOURCE_TARGET_ROOT:-/var/www/magnetgoogo-site}"
CURL_BIN="${MAGNET_SOURCE_CURL_BIN:-/usr/bin/curl}"
PYTHON_BIN="${MAGNET_SOURCE_PYTHON_BIN:-/usr/bin/python3}"
TMP_ROOT="$(mktemp -d /var/tmp/magnet-source-sync.XXXXXX)"
trap 'rm -rf "$TMP_ROOT"' EXIT

validate_pack() {
  "$PYTHON_BIN" -c 'import json,re,sys; p=sys.argv[1]; d=json.load(open(p,encoding="utf-8")); ok=isinstance(d,dict) and isinstance(d.get("iv"),str) and re.fullmatch(r"[0-9a-fA-F]{32}",d["iv"]) and isinstance(d.get("ct"),str) and len(d["ct"])>1024 and isinstance(d.get("sig"),str) and re.fullmatch(r"[0-9a-fA-F]{64}",d["sig"]) and isinstance(d.get("gz"),bool); sys.exit(0 if ok else 3)' "$1"
}

for file in sources.enc.json sources-green.enc.json; do
  authority="$TMP_ROOT/$file.authority"
  cdn="$TMP_ROOT/$file.cdn"
  headers="$TMP_ROOT/$file.headers"
  "$CURL_BIN" -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 90 -H 'Cache-Control: no-cache' -D "$headers" -o "$authority" "$AUTHORITY_BASE/$file?aliyun_sync=$(date +%s)"
  grep -Eiq '^x-source-authority:[[:space:]]*github-raw[[:space:]]*$' "$headers"
  "$CURL_BIN" -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 90 -H 'Cache-Control: no-cache' -o "$cdn" "$CDN_BASE/$file"
  validate_pack "$authority"
  validate_pack "$cdn"
  cmp -s "$authority" "$cdn"
done

mkdir -p "$TARGET_ROOT"
for file in sources.enc.json sources-green.enc.json; do
  authority="$TMP_ROOT/$file.authority"
  target="$TARGET_ROOT/$file"
  if [[ -f "$target" ]] && cmp -s "$authority" "$target"; then
    echo "$file already current: $(sha256sum "$target" | awk '{print $1}')"
    continue
  fi
  pending="$TARGET_ROOT/.$file.$$.new"
  install -m 0644 "$authority" "$pending"
  mv -f "$pending" "$target"
  echo "$file updated: $(sha256sum "$target" | awk '{print $1}')"
done
