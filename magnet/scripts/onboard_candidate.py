"""Onboard a new candidate host as a sources.json rule.

End-to-end pipeline:
  1. discovery.search_form_probe.probe_search_url(host) → SearchPattern
  2. crawler_v2.healer.HealerV2.heal_and_retry(draft_rule) → live magnets
  3. Emit a JSON rule fragment to stdout. Operator copies into sources.json
     after manual review (we do NOT auto-write — onboarding is a curated act).

Usage:
  python -m scripts.onboard_candidate --host clb.im --family clb
  python -m scripts.onboard_candidate --host yts.rs   # no family
  python -m scripts.onboard_candidate --host new.site --bait 复仇者联盟

This is the canonical follow-up to `brand_rediscover` — when that finds
candidate hosts, run them through here one by one to get rule drafts.
"""

import os
import sys
import json
import argparse
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAGNET_ROOT = os.path.dirname(HERE)
if MAGNET_ROOT not in sys.path:
    sys.path.insert(0, MAGNET_ROOT)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from discovery.search_form_probe import probe_search_url, derive_detail_selector
from crawler_v2.healer import HealerV2


def build_draft_rule(host: str, pattern, family: str = None) -> dict:
    """Convert a SearchPattern + host into a sources.json-shaped rule."""
    selectors = {
        "list_item": "",
        "title": "",
        "magnet": "",
        "size": "",
        "date": "",
    }
    if pattern.parse_strategy == "detail_follow":
        # Use the actual detail link samples observed during probe to derive
        # a precise selector (most-common path segment, e.g. /movie/).
        if pattern.detail_link_samples:
            selectors["detail_link"] = derive_detail_selector(pattern.detail_link_samples)
        else:
            selectors["detail_link"] = 'a[href*="/detail/"]'

    capabilities = {"parse_strategy": pattern.parse_strategy}
    if family:
        capabilities["brand_family"] = family

    rule = {
        "site": {"name": host, "origin": f"https://{host}"},
        "search": {
            "request_template": pattern.request_template,
            "parse_metadata": {"selectors": selectors},
        },
        "capabilities": capabilities,
        "health": {
            "status": "yellow",  # operator promotes to green after review
            "status_detail": "ok",
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        },
        "_onboarded": {
            "version": os.environ.get("ONBOARD_VERSION", "v0.3.7"),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "probe_method": pattern.method,
            "sample_url": pattern.sample_url,
            "bait_used": pattern.bait_used,
            "magnets_seen": pattern.magnets_seen,
            "detail_links_seen": pattern.detail_links_seen,
        },
    }
    return rule


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="Candidate host (no scheme): e.g. clb.im")
    ap.add_argument("--family", default=None, help="brand_family id if applicable (clb/clm/sobt/52bt)")
    ap.add_argument("--bait", action="append", default=None,
                    help="Override bait keyword(s). Repeat for multiple. Default: Avengers/复仇者联盟/...")
    ap.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))
    ap.add_argument("--skip-verify", action="store_true", help="Just probe, don't run HealerV2 verify")
    ap.add_argument("--use-llm", action="store_true",
                    help="When probe fails, fall back to crawler_v2.ai.synthesize_selectors_for_url "
                         "(Crawl4AI + reasoning LLM). Costs API tokens; only sensible for "
                         "JS-rendered sites where the heuristic probe can't see structure.")
    ap.add_argument("--search-url", default=None,
                    help="Manual search URL template for --use-llm path (e.g. https://host/search?q={query}). "
                         "Required because LLM path can't auto-discover the URL.")
    args = ap.parse_args()

    print(f"\n[1/2] Probing search URL pattern for {args.host}...", file=sys.stderr)
    baits = args.bait or ["Avengers", "复仇者联盟", "one piece", "1080p"]
    pattern = probe_search_url(args.host, baits=baits, proxy=args.proxy)
    if not pattern:
        if not args.use_llm:
            print(f"ERROR: no search pattern found for {args.host}. "
                  f"Site may use SPA/JS rendering — retry with --use-llm "
                  f"--search-url 'https://{args.host}/search?q={{query}}'",
                  file=sys.stderr)
            sys.exit(2)
        # ── LLM fallback path ─────────────────────────────────────────
        if not args.search_url:
            print("ERROR: --use-llm requires --search-url '<template-with-{query}>'",
                  file=sys.stderr)
            sys.exit(2)
        print(f"\n[1b/2] Probe failed; falling back to LLM selector synthesis...",
              file=sys.stderr)
        try:
            from crawler_v2.ai import synthesize_selectors_for_url, render_rule_draft
        except ImportError as e:
            print(f"ERROR: crawler_v2.ai unavailable: {e}", file=sys.stderr)
            sys.exit(3)
        try:
            llm_result = synthesize_selectors_for_url(
                args.search_url, query=baits[0], proxy=args.proxy,
            )
        except Exception as e:
            print(f"ERROR: LLM synthesis failed: {e}", file=sys.stderr)
            sys.exit(4)
        if not llm_result or not llm_result.get('selectors'):
            print(f"ERROR: LLM returned empty selectors", file=sys.stderr)
            sys.exit(5)
        # Render LLM-driven rule directly (skip pattern-based draft + verify
        # since the LLM has already been observed to work on the page).
        from urllib.parse import urlparse
        parsed = urlparse(args.search_url)
        rel_template = (parsed.path or '/') + (
            '?' + parsed.query if parsed.query else '')
        rule = {
            "site": {"name": args.host, "origin": f"https://{args.host}"},
            "search": {
                "request_template": rel_template,
                "parse_metadata": {"selectors": llm_result['selectors']},
            },
            "capabilities": {
                "parse_strategy": "list_page",
                **({"brand_family": args.family} if args.family else {}),
            },
            "health": {"status": "yellow", "status_detail": "ok"},
            "_onboarded": {
                "version": os.environ.get("ONBOARD_VERSION", "v0.3.10"),
                "at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "probe_method": "llm_selector_synth",
                "llm_provider": llm_result.get('llm_provider', '?'),
                "magnets_validated": llm_result.get('regex_magnets', 0),
                "list_items": llm_result.get('list_items', 0),
                "sample_url": args.search_url.replace('{query}', baits[0]),
            },
        }
        print(f"  → selectors: {llm_result['selectors']}", file=sys.stderr)
        print(f"  → magnets validated: {llm_result.get('regex_magnets', 0)}",
              file=sys.stderr)
        print()
        print(json.dumps(rule, ensure_ascii=False, indent=2))
        print()
        print(f"[next] Review above JSON, then append to sources.json. "
              f"LLM-generated rules need extra scrutiny.", file=sys.stderr)
        return
    print(f"  → {pattern.method}: {pattern.request_template} "
          f"({pattern.parse_strategy}, magnets={pattern.magnets_seen}, "
          f"detail_links={pattern.detail_links_seen})", file=sys.stderr)

    rule = build_draft_rule(args.host, pattern, family=args.family)

    if not args.skip_verify:
        print(f"\n[2/2] Verifying with HealerV2 (bait={pattern.bait_used!r})...", file=sys.stderr)
        healer = HealerV2()
        t0 = time.time()
        result = healer.heal_and_retry(rule, query=pattern.bait_used)
        elapsed = int(time.time() - t0)
        magnets = result.get("magnets_found", 0)
        method = result.get("method", "")
        print(f"  → status={result.get('status')} method={method} "
              f"magnets={magnets} elapsed={elapsed}s", file=sys.stderr)
        rule["_onboarded"]["verify_result"] = {
            "status": result.get("status"),
            "method": method,
            "magnets_found": magnets,
            "elapsed_s": elapsed,
        }
        if magnets > 0:
            rule["health"]["status"] = "green"
            rule["health"]["magnets_found"] = magnets

    # Emit the rule to stdout for operator review
    print()
    print(json.dumps(rule, ensure_ascii=False, indent=2))
    print()
    print(f"[next] Review above JSON, then append to sources.json under the "
          f"appropriate ruleset.", file=sys.stderr)


if __name__ == "__main__":
    main()
