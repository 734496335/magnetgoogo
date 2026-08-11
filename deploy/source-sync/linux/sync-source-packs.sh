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
FILE="sources.enc.json"
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
authority="$TMP_ROOT/$FILE.authority"
github_api_json="$TMP_ROOT/$FILE.github-api.json"
github_api="$TMP_ROOT/$FILE.github-api"
headers="$TMP_ROOT/$FILE.headers"

if ! "$CURL_BIN" -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 90 -H 'Cache-Control: no-cache' -D "$headers" -o "$authority" "$AUTHORITY_BASE/$FILE?aliyun_sync=$(date +%s)"; then
  fail "authority fetch failed for $FILE"
fi
if ! grep -Eiq '^x-source-authority:[[:space:]]*github-raw[[:space:]]*$' "$headers"; then
  fail "authority provenance header is missing for $FILE"
fi
if ! "$CURL_BIN" -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 90 -H 'Accept: application/vnd.github+json' -H 'User-Agent: MagnetGoogo-Aliyun-SourceSync/1.0' -o "$github_api_json" "$GITHUB_API_CONTENTS_BASE/$FILE?ref=main"; then
  fail "GitHub API contents fetch failed for $FILE"
fi
if ! decode_github_content "$github_api_json" "$github_api" "$FILE"; then
  fail "GitHub API contents decode failed for $FILE"
fi
if ! cmp -s "$authority" "$github_api"; then
  fail "authority/GitHub API mismatch for $FILE authority=$(sha256sum "$authority" | awk '{print $1}') github_api=$(sha256sum "$github_api" | awk '{print $1}')"
fi

if ! "$PYTHON_BIN" "$VERIFIER" --full "$authority" --min-remaining-hours "$MIN_REMAINING_HOURS"; then
  fail "cryptographic or freshness validation failed"
fi

cdn="$TMP_ROOT/$FILE.cdn"
if "$CURL_BIN" -fsSL --retry 1 --connect-timeout 10 --max-time 30 -H 'Cache-Control: no-cache' -o "$cdn" "$CDN_BASE/$FILE"; then
  if cmp -s "$authority" "$cdn"; then
    echo "$FILE optional jsDelivr evidence converged: $(sha256sum "$cdn" | awk '{print $1}')"
  else
    echo "source-sync: warning: jsDelivr is lagging for $FILE authority=$(sha256sum "$authority" | awk '{print $1}') cdn=$(sha256sum "$cdn" | awk '{print $1}')" >&2
  fi
else
  echo "source-sync: warning: jsDelivr evidence unavailable for $FILE" >&2
fi

target="$TARGET_ROOT/$FILE"
if [[ -f "$target" ]] && cmp -s "$authority" "$target"; then
  echo "$FILE already current: $(sha256sum "$target" | awk '{print $1}')"
  exit 0
fi

pending="$TARGET_ROOT/.$FILE.$$.new"
install -m 0644 "$authority" "$pending"
if ! "$PYTHON_BIN" "$VERIFIER" --full "$pending" --min-remaining-hours "$MIN_REMAINING_HOURS" >/dev/null; then
  rm -f "$pending"
  fail "pending source pack validation failed"
fi
mv -f "$pending" "$target"
if ! cmp -s "$target" "$authority"; then
  fail "post-install source-pack bytes mismatch"
fi

echo "$FILE updated: $(sha256sum "$target" | awk '{print $1}')"
