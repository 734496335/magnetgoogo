"""Single-source ad-hoc verification using HealerV2.

Usage:
  python -m scripts.verify_one --name yts.rs
  python -m scripts.verify_one --name knaben.org

Useful for validating new healer capabilities (e.g. detail_follow_v2) on
one specific source without re-running the full 240-source verify_and_heal.
"""

import os
import sys
import json
import argparse
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAGNET_ROOT = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(MAGNET_ROOT)
if MAGNET_ROOT not in sys.path:
    sys.path.insert(0, MAGNET_ROOT)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from crawler_v2.healer import HealerV2

SOURCES_JSON = os.path.join(PROJECT_ROOT, "sources.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="Exact site.name to verify")
    ap.add_argument("--query", default=None, help="Override bait query (default: auto)")
    ap.add_argument("--proxy", default=None, help="HTTP proxy URL (e.g. http://127.0.0.1:33210)")
    args = ap.parse_args()

    with open(SOURCES_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    rule = None
    for rs in data.get("rulesets") or []:
        for r in rs.get("rules") or []:
            if (r.get("site") or {}).get("name") == args.name:
                rule = r
                break
        if rule:
            break

    if not rule:
        print(f"ERROR: source {args.name!r} not found in sources.json")
        sys.exit(2)

    print(f"\n[verify_one] {args.name}")
    print(f"  origin    : {rule['site'].get('origin')}")
    print(f"  template  : {(rule.get('search') or {}).get('request_template')}")
    print(f"  selectors : {(rule.get('search') or {}).get('parse_metadata', {}).get('selectors')}")
    print(f"  caps      : {rule.get('capabilities')}")
    print()

    healer = HealerV2(proxy=args.proxy)
    t0 = time.time()
    result = healer.heal_and_retry(rule, query=args.query)
    elapsed = int(time.time() - t0)

    print(f"\n[result] elapsed={elapsed}s")
    print(json.dumps({
        "status": result.get("status"),
        "method": result.get("method"),
        "magnets_found": result.get("magnets_found"),
        "sample": result.get("sample"),
        "error": result.get("error"),
        "bait_used": result.get("bait_used"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
