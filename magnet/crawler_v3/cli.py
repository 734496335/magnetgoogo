"""crawler_v3 CLI.

Usage:
    python -m magnet.crawler_v3 search "Inception" --origin clb21.top
    python -m magnet.crawler_v3 search "蜘蛛侠" --origin laowangzo.top --debug
    python -m magnet.crawler_v3 classify --origin clttone.top
    python -m magnet.crawler_v3 verify-yellow "test"   # batch-verify yellow sources
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

# Ensure project root on path when run as -m
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SOURCES_FILE = os.path.join(ROOT, "sources.json")


def _load_sources() -> list[dict]:
    """Flatten sources.json into a list of rule dicts.

    Schema: {rulesets: [{rules: [...]}]}  (canonical, current schema_version 0.1)
    Falls back to {sources: [...]} or top-level list for forward compat.
    """
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        if "rulesets" in data:
            out: list[dict] = []
            for rs in data.get("rulesets") or []:
                out.extend(rs.get("rules") or [])
            return out
        if "sources" in data:
            return data["sources"]
    if isinstance(data, list):
        return data
    return []


def _filter_sources(sources: list[dict], origin: str | None, status: str | None) -> list[dict]:
    out = sources
    if origin:
        origin = origin.lower()
        out = [s for s in out if origin in (s.get("site", {}).get("origin", "") or "").lower()]
    if status:
        out = [s for s in out if (s.get("health") or {}).get("status") == status]
    return out


def cmd_search(args: argparse.Namespace) -> int:
    from .orchestrator import search

    sources = _filter_sources(_load_sources(), args.origin, args.status)
    if not sources:
        print(f"No sources matched origin={args.origin!r} status={args.status!r}", file=sys.stderr)
        return 2

    total_results = 0
    for src in sources:
        name = src.get("site", {}).get("name", "?")
        print(f"\n── {name} ({src.get('site', {}).get('origin')}) ──")
        results = search(src, args.query, limit=args.limit)
        total_results += len(results)
        for r in results:
            print(f"  {r.title[:80]}  |  S:{r.seeders or '-'}  size:{r.size or '-'}")
            print(f"    magnet: {(r.magnet or '(detail-follow)')[:96]}")
    print(f"\nTotal: {total_results} results across {len(sources)} source(s)")
    return 0 if total_results > 0 else 1


def cmd_classify(args: argparse.Namespace) -> int:
    from .detector import classify

    sources = _filter_sources(_load_sources(), args.origin, args.status)
    for src in sources:
        plan = classify(src)
        print(f"{src.get('site', {}).get('origin'):40s}  →  {[k.value for k in plan.order]}  ({plan.reason})")
    return 0


def cmd_verify_yellow(args: argparse.Namespace) -> int:
    from .orchestrator import search

    yellows = _filter_sources(_load_sources(), None, "yellow")
    if not yellows:
        print("No yellow sources found")
        return 0

    print(f"Verifying {len(yellows)} yellow source(s) with query={args.query!r}\n")
    passed = 0
    for src in yellows:
        name = src.get("site", {}).get("name", "?")
        origin = src.get("site", {}).get("origin", "?")
        results = search(src, args.query, limit=5)
        ok = bool(results) and any(r.magnet for r in results)
        status = "PASS" if ok else "FAIL"
        print(f"  {status:8s}  {name:30s}  {origin:40s}  n={len(results)}")
        if ok:
            passed += 1
    print(f"\nResult: {passed}/{len(yellows)} sources verified")
    return 0


def cmd_recheck(args: argparse.Namespace) -> int:
    """Recheck yellow sources; upgrade to green if they pass."""
    from .orchestrator import search

    sources = _filter_sources(_load_sources(), None, "yellow")
    if not sources:
        print("No yellow sources found")
        return 0

    print(f"Rechecking {len(sources)} yellow source(s) with query={args.query!r}")
    if not args.commit:
        print("(dry-run — use --commit to write changes)\n")

    upgraded = 0
    changed = False
    for src in sources:
        name = src.get("site", {}).get("name", "?")
        origin = src.get("site", {}).get("origin", "?")
        results = search(src, args.query, limit=5)
        magnets = sum(1 for r in results if r.magnet)
        ok = magnets >= 3
        status = "PASS" if ok else "FAIL"
        print(f"  {status:8s}  {name:30s}  {origin:40s}  magnets={magnets}")
        if ok and args.commit:
            src.setdefault("health", {})["status"] = "green"
            src["health"]["status_detail"] = "ok"
            src["health"]["magnets_found"] = magnets
            if results:
                src["health"]["sample_title"] = results[0].title[:80]
            upgraded += 1
            changed = True

    if changed:
        with open(SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"rulesets": [{"rules": _load_sources()}]},
                f, ensure_ascii=False, indent=2,
            )
            f.write("\n")
        print(f"\nUpgraded {upgraded} source(s) to green (sources.json updated)")
    else:
        print(f"\n{upgraded} source(s) would be upgraded (dry-run)")

    return 0


def cmd_brand_stats(args: argparse.Namespace) -> int:
    """Print brand-level coverage statistics."""
    sources = _load_sources()
    brands: dict[str, dict] = {}  # brand -> {green: N, yellow: N, gray: N}
    no_brand = 0
    for src in sources:
        brand = (src.get("site") or {}).get("brand", "")
        if not brand:
            no_brand += 1
            continue
        status = (src.get("health") or {}).get("status", "unknown")
        if brand not in brands:
            brands[brand] = {"green": 0, "yellow": 0, "gray": 0, "other": 0}
        if status in brands[brand]:
            brands[brand][status] += 1
        else:
            brands[brand]["other"] += 1

    total_brands = len(brands)
    green_brands = sum(1 for b in brands.values() if b["green"] > 0)
    yellow_only = sum(1 for b in brands.values() if b["yellow"] > 0 and b["green"] == 0)
    gray_only = sum(1 for b in brands.values() if b["gray"] > 0 and b["green"] == 0 and b["yellow"] == 0)

    print(f"Total sources: {len(sources)}")
    print(f"Sources without brand: {no_brand}")
    print(f"Total brands: {total_brands}")
    print(f"Green-covered brands: {green_brands}")
    print(f"Yellow-only brands: {yellow_only}")
    print(f"Gray-only brands: {gray_only}")
    coverage = green_brands / (green_brands + yellow_only) * 100 if (green_brands + yellow_only) else 0
    print(f"Brand coverage: {coverage:.1f}%")

    if args.top:
        print(f"\nTop {args.top} brands by source count:")
        for brand, counts in sorted(brands.items(), key=lambda x: sum(x[1].values()), reverse=True)[:args.top]:
            total = sum(counts.values())
            print(f"  {brand:30s}  g={counts['green']:2d} y={counts['yellow']:2d} gray={counts['gray']:2d}  ({total})")

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="magnet.crawler_v3", description="crawler_v3 4-tier search")
    p.add_argument("--debug", action="store_true", help="verbose logging")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="run search on filtered sources")
    p_search.add_argument("query")
    p_search.add_argument("--origin", default=None, help="filter sources by origin substring")
    p_search.add_argument("--status", default=None, help="filter by health.status (green/yellow/gray)")
    p_search.add_argument("--limit", type=int, default=24)
    p_search.set_defaults(fn=cmd_search)

    p_classify = sub.add_parser("classify", help="show Tier plan for sources")
    p_classify.add_argument("--origin", default=None)
    p_classify.add_argument("--status", default=None)
    p_classify.set_defaults(fn=cmd_classify)

    p_verify = sub.add_parser("verify-yellow", help="batch-verify all yellow sources")
    p_verify.add_argument("query")
    p_verify.set_defaults(fn=cmd_verify_yellow)

    p_recheck = sub.add_parser("recheck", help="recheck yellow sources, optionally upgrade to green")
    p_recheck.add_argument("query", help="search query to test")
    p_recheck.add_argument("--commit", action="store_true", help="write upgrades to sources.json")
    p_recheck.set_defaults(fn=cmd_recheck)

    p_brand = sub.add_parser("brand-stats", help="print brand-level coverage statistics")
    p_brand.add_argument("--top", type=int, default=0, help="show top N brands by source count")
    p_brand.set_defaults(fn=cmd_brand_stats)

    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
