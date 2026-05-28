#!/usr/bin/env python3
"""
Encrypt green (compliance) sources → sources-green.enc.json

Extracts only the whitelisted source IDs from sources.json,
encrypts with the same key as the full version, and deploys
to the same multi-path CDN endpoints.

Usage:
  python encrypt_sources_green.py                # encrypt → mg-data/sources-green.enc.json
  python encrypt_sources_green.py --deploy       # encrypt + git push
"""

import json
import sys
from pathlib import Path
from encrypt_sources import encrypt_sources as _encrypt_full, verify_roundtrip, DIST_DIR

SCRIPT_DIR = Path(__file__).parent
SOURCES_JSON = SCRIPT_DIR / "sources.json"
GREEN_JSON = SCRIPT_DIR / "sources-green.json"       # temp intermediate
DIST_FILE = DIST_DIR / "sources-green.enc.json"

# ── Whitelisted source IDs (must match complianceConfig.ts) ──
COMPLIANT_IDS = {
    "6d6496b2ce94",  # animetosho.org
    "52fbe59cf95c",  # animetime.cc
    "uindex_001",    # UIndex
    "zhihu_cilimo",  # CiliMo/磁力魔
    "zhihu_kd705",   # 磁力口袋/CLKD
}


def extract_green_sources():
    """Extract only whitelisted sources from sources.json."""
    raw = json.loads(SOURCES_JSON.read_bytes())

    all_rules = []
    if isinstance(raw, dict) and raw.get("rulesets"):
        for rs in raw["rulesets"]:
            if rs.get("rules"):
                all_rules.extend(rs["rules"])
    elif isinstance(raw, list):
        all_rules = raw

    green_rules = [r for r in all_rules if r.get("id") in COMPLIANT_IDS]

    found_ids = {r["id"] for r in green_rules}
    missing = COMPLIANT_IDS - found_ids
    if missing:
        print(f"⚠  Missing source IDs: {missing}")

    # Preserve the same schema structure
    green_json = {
        "schema_version": raw.get("schema_version", "0.1"),
        "generated_at": raw.get("generated_at", ""),
        "rulesets": [{
            "ruleset_id": "green",
            "priority": 1,
            "max_sources_per_search": 5,
            "rules": green_rules,
        }],
    }

    GREEN_JSON.write_text(
        json.dumps(green_json, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"✓ Extracted {len(green_rules)} green sources → {GREEN_JSON}")
    for r in green_rules:
        status = r.get("health", {}).get("status", "?")
        print(f"  [{status}] {r['id']} — {r.get('site', {}).get('name', '?')}")

    return green_json


def main():
    if not SOURCES_JSON.exists():
        print(f"✗ {SOURCES_JSON} not found")
        sys.exit(1)

    print("=== Green Sources Encryption ===\n")

    # Step 1: Extract
    extract_green_sources()

    # Step 2: Encrypt (reuse the same encrypt logic from encrypt_sources.py)
    config_path = DIST_DIR / "config.json"
    print(f"\nEncrypting {GREEN_JSON} ...")
    payload = _encrypt_full(GREEN_JSON, config_path)

    # Step 3: Write
    DIST_DIR.mkdir(exist_ok=True)
    enc_json = json.dumps(payload)
    DIST_FILE.write_text(enc_json, encoding="utf-8")
    print(f"✓ Written {DIST_FILE} ({len(enc_json):,} bytes)")

    # Step 4: Verify
    print("\nVerifying roundtrip ...")
    if not verify_roundtrip(payload):
        sys.exit(1)

    # Cleanup temp file
    GREEN_JSON.unlink(missing_ok=True)

    if "--deploy" in sys.argv:
        from encrypt_sources import deploy_to_github
        deploy_to_github()


if __name__ == "__main__":
    main()
