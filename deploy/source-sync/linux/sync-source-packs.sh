#!/usr/bin/env bash
set -euo pipefail

AUTHORITY_BASE="${MAGNET_SOURCE_AUTHORITY_BASE:-https://magnetgoogo.com}"
GITHUB_API_CONTENTS_BASE="${MAGNET_SOURCE_GITHUB_API_CONTENTS_BASE:-https://api.github.com/repos/734496335/mg-data/contents}"
CDN_BASE="${MAGNET_SOURCE_CDN_BASE:-https://cdn.jsdelivr.net/gh/734496335/mg-data@main}"
TARGET_ROOT="${MAGNET_SOURCE_TARGET_ROOT:-/var/www/magnetgoogo-site}"
CURL_BIN="${MAGNET_SOURCE_CURL_BIN:-/usr/bin/curl}"
PYTHON_BIN="${MAGNET_SOURCE_PYTHON_BIN:-/usr/bin/python3}"
VERIFIER="${MAGNET_SOURCE_VERIFIER:-/opt/magnet-source-sync/verify-source-packs.py}"
MIN_REMAINING_HOURS="${MAGNET_SOURCE_MIN_REMAINING_HOURS:-12}"
TMP_ROOT="$(mktemp -d /var/tmp/magnet-source-sync.XXXXXX)"
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  echo "source-sync: $*" >&2
  exit 1
}

decode_github_content() {
  "$PYTHON_BIN" -c 'import base64,json,sys; src,out,name=sys.argv[1:]; d=json.load(open(src,encoding="utf-8")); assert d.get("type")=="file" and d.get("name")==name and isinstance(d.get("content"),str); encoded="".join(d["content"].split()); raw=base64.b64decode(encoded,validate=True); open(out,"wb").write(raw)' "$1" "$2" "$3"
}

mkdir -p "$TARGET_ROOT"
for file in sources.enc.json sources-green.enc.json; do
  authority="$TMP_ROOT/$file.authority"
  github_api_json="$TMP_ROOT/$file.github-api.json"
  github_api="$TMP_ROOT/$file.github-api"
  headers="$TMP_ROOT/$file.headers"
  if ! "$CURL_BIN" -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 90 -H 'Cache-Control: no-cache' -D "$headers" -o "$authority" "$AUTHORITY_BASE/$file?aliyun_sync=$(date +%s)"; then
    fail "authority fetch failed for $file"
  fi
  if ! grep -Eiq '^x-source-authority:[[:space:]]*github-raw[[:space:]]*$' "$headers"; then
    fail "authority provenance header is missing for $file"
  fi
  if ! "$CURL_BIN" -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 90 -H 'Accept: application/vnd.github+json' -H 'User-Agent: MagnetGoogo-Aliyun-SourceSync/1.0' -o "$github_api_json" "$GITHUB_API_CONTENTS_BASE/$file?ref=main"; then
    fail "GitHub API contents fetch failed for $file"
  fi
  if ! decode_github_content "$github_api_json" "$github_api" "$file"; then
    fail "GitHub API contents decode failed for $file"
  fi
  if ! cmp -s "$authority" "$github_api"; then
    echo "source-sync: authority/GitHub API mismatch for $file authority=$(sha256sum "$authority" | awk '{print $1}') github_api=$(sha256sum "$github_api" | awk '{print $1}')" >&2
    exit 1
  fi
done

if ! "$PYTHON_BIN" "$VERIFIER" \
  --full "$TMP_ROOT/sources.enc.json.authority" \
  --green "$TMP_ROOT/sources-green.enc.json.authority" \
  --min-remaining-hours "$MIN_REMAINING_HOURS"; then
  fail "cryptographic, freshness, or full/green coherence validation failed"
fi

for file in sources.enc.json sources-green.enc.json; do
  cdn="$TMP_ROOT/$file.cdn"
  if "$CURL_BIN" -fsSL --retry 1 --connect-timeout 10 --max-time 30 -H 'Cache-Control: no-cache' -o "$cdn" "$CDN_BASE/$file"; then
    if cmp -s "$TMP_ROOT/$file.authority" "$cdn"; then
      echo "$file optional jsDelivr evidence converged: $(sha256sum "$cdn" | awk '{print $1}')"
    else
      echo "source-sync: warning: jsDelivr is lagging for $file authority=$(sha256sum "$TMP_ROOT/$file.authority" | awk '{print $1}') cdn=$(sha256sum "$cdn" | awk '{print $1}')" >&2
    fi
  else
    echo "source-sync: warning: jsDelivr evidence unavailable for $file" >&2
  fi
done

full_target="$TARGET_ROOT/sources.enc.json"
green_target="$TARGET_ROOT/sources-green.enc.json"
full_pending="$TARGET_ROOT/.sources.enc.json.$$.new"
green_pending="$TARGET_ROOT/.sources-green.enc.json.$$.new"
install -m 0644 "$TMP_ROOT/sources.enc.json.authority" "$full_pending"
install -m 0644 "$TMP_ROOT/sources-green.enc.json.authority" "$green_pending"

full_changed=1
green_changed=1
if [[ -f "$full_target" ]] && cmp -s "$full_pending" "$full_target"; then full_changed=0; fi
if [[ -f "$green_target" ]] && cmp -s "$green_pending" "$green_target"; then green_changed=0; fi
if (( full_changed == 0 && green_changed == 0 )); then
  rm -f "$full_pending" "$green_pending"
  echo "sources.enc.json already current: $(sha256sum "$full_target" | awk '{print $1}')"
  echo "sources-green.enc.json already current: $(sha256sum "$green_target" | awk '{print $1}')"
  exit 0
fi

full_had=0
green_had=0
if [[ -f "$full_target" ]]; then cp -p "$full_target" "$TMP_ROOT/full.backup"; full_had=1; fi
if [[ -f "$green_target" ]]; then cp -p "$green_target" "$TMP_ROOT/green.backup"; green_had=1; fi

restore_targets() {
  if (( full_had == 1 )); then install -m 0644 "$TMP_ROOT/full.backup" "$full_target"; else rm -f "$full_target"; fi
  if (( green_had == 1 )); then install -m 0644 "$TMP_ROOT/green.backup" "$green_target"; else rm -f "$green_target"; fi
}

if (( green_changed == 1 )); then
  if ! mv -f "$green_pending" "$green_target"; then
    rm -f "$full_pending" "$green_pending"
    fail "failed to replace sources-green.enc.json"
  fi
else
  rm -f "$green_pending"
fi
if (( full_changed == 1 )); then
  if ! mv -f "$full_pending" "$full_target"; then
    restore_targets
    rm -f "$full_pending"
    fail "failed to replace sources.enc.json; previous source-pack pair restored"
  fi
else
  rm -f "$full_pending"
fi

if ! cmp -s "$full_target" "$TMP_ROOT/sources.enc.json.authority" || ! cmp -s "$green_target" "$TMP_ROOT/sources-green.enc.json.authority"; then
  restore_targets
  fail "post-install source-pack bytes mismatch; previous pair restored"
fi
if ! "$PYTHON_BIN" "$VERIFIER" --full "$full_target" --green "$green_target" --min-remaining-hours "$MIN_REMAINING_HOURS" >/dev/null; then
  restore_targets
  fail "post-install source-pack validation failed; previous pair restored"
fi

echo "sources.enc.json updated: $(sha256sum "$full_target" | awk '{print $1}')"
echo "sources-green.enc.json updated: $(sha256sum "$green_target" | awk '{print $1}')"
