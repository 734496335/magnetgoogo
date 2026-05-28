"""Run brand-family domain rediscovery as a batch script.

Calls `discovery.brand_rediscovery.find_brand_domains` for each known
collapsed family (or a user-specified subset) and prints a ranked candidate
table per family. Saves a JSON report to `magnet/_brand_domains_<ts>.json`.

Promoting a candidate into sources.json is NOT done here — that's a separate
human/script step (the candidate may need its search URL pattern probed
first, etc.).

Usage:
  python -m magnet.scripts.brand_rediscover                     # all DEFAULT_FAMILIES
  python -m magnet.scripts.brand_rediscover --family clb        # only clb family
"""

import os
import sys
import json
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
MAGNET_ROOT = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(MAGNET_ROOT)
if MAGNET_ROOT not in sys.path:
    sys.path.insert(0, MAGNET_ROOT)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from discovery.brand_rediscovery import (
    DEFAULT_FAMILIES, find_brand_domains, BrandFamily, BrandCandidate,
    tag_existing_sources,
)

SOURCES_JSON = os.path.join(PROJECT_ROOT, "sources.json")
OUT_DIR = MAGNET_ROOT


def main():
    ap = argparse.ArgumentParser(description="Rediscover replacement domains for collapsed brand families")
    ap.add_argument("--proxy",
                    default=os.environ.get("HTTPS_PROXY") or "http://127.0.0.1:33210",
                    help="HTTP proxy (default: 127.0.0.1:33210)")
    ap.add_argument("--family", default=None,
                    help="Only run this family id (clb/clm/sobt/52bt). Default: all.")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tag-sources", choices=["preview", "write"], default=None,
                    help="Tag sources.json rules with capabilities.brand_family "
                         "based on dead_hosts + name patterns. 'preview' lists "
                         "matches without writing; 'write' applies them. Skips DDG.")
    args = ap.parse_args()

    # Tag-only mode: don't run DDG search, just attribute existing sources
    if args.tag_sources:
        dry = (args.tag_sources == "preview")
        tagged = tag_existing_sources(SOURCES_JSON, dry_run=dry)
        mode = "DRY-RUN (preview)" if dry else "WRITTEN to sources.json"
        print(f"\nBrand family attribution — {mode}\n" + "=" * 60)
        total = 0
        for fid, names in tagged.items():
            print(f"\n[{fid}] {len(names)} rules:")
            for n in names:
                print(f"  + {n}")
            total += len(names)
        print(f"\nTotal: {total} rules attributed to a brand family.")
        if dry:
            print("  Re-run with --tag-sources write to persist.")
        return

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print(f"[proxy] {args.proxy}")
    families = [f for f in DEFAULT_FAMILIES if (args.family is None or f.id == args.family)]
    if not families:
        print(f"ERROR: --family {args.family!r} not in {[f.id for f in DEFAULT_FAMILIES]}")
        sys.exit(2)

    all_results = []
    for f in families:
        print(f"\n{'=' * 72}\n  {f.label}  (dead: {len(f.dead_hosts)} hosts)\n{'=' * 72}")
        cands: list[BrandCandidate] = find_brand_domains(
            f, proxy=args.proxy, sources_json_path=SOURCES_JSON,
        )
        print(f"  → {len(cands)} candidates after filtering")
        for c in cands[:8]:
            flag = ("🟢 magnet" if c.magnets_on_home else
                    "🔵 brand " if c.brand_hit else
                    "⚪ reach " if c.reachable else "🔴 dead  ")
            print(f"    {flag}  {c.host:<28} status={c.status} title={c.title[:50]!r}")
        all_results.append({
            "family_id": f.id, "label": f.label,
            "candidates": [c.__dict__ for c in cands],
        })

    # ── Action summary ──
    print(f"\n\n{'=' * 72}\n  ACTION SUMMARY\n{'=' * 72}")
    saved = 0
    for r in all_results:
        cands = [BrandCandidate(**{k: v for k, v in c.items() if k != "rank_key"})
                 for c in r["candidates"]]
        top = next((c for c in cands if c.magnets_on_home > 0), None) or \
              next((c for c in cands if c.brand_hit), None)
        if top:
            saved += 1
            note = f"{top.magnets_on_home} magnets" if top.magnets_on_home else "brand-hit only — verify search"
            print(f"  ✓ {r['label']}: USE \"{top.host}\" ({note})")
        else:
            print(f"  ✗ {r['label']}: no strong candidate; manual research needed")
    print(f"\n  {saved} / {len(all_results)} families have at least 1 strong candidate")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or os.path.join(OUT_DIR, f"_brand_domains_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "proxy": args.proxy, "families": all_results},
                  f, ensure_ascii=False, indent=2)
    print(f"\n[save] {out_path}")


if __name__ == "__main__":
    main()
