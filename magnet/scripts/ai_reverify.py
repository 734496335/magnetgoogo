"""Batch AI selector synthesis for suspect_dead_search sources.

Reads:
  - magnet/_health_report_full.json (latest health_check output)
  - sources.json (to get search URL templates)

For each source flagged `suspect_dead_search`, runs the offline AI selector
synthesis pipeline (StealthyFetcher → Crawl4AI + LLM → validate against HTML).
Writes:
  - magnet/_ai_batch_<timestamp>.json — summary
  - magnet/_ai_draft_<host>.json per source (for human review)

This is OFFLINE-ONLY. It is not invoked by real-time search; it produces
selector PROPOSALS that humans/scripts then promote into sources.json.

Usage:
  python -m magnet.scripts.ai_reverify              # all suspect_dead
  python -m magnet.scripts.ai_reverify --filter clb # only those whose name contains "clb"
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

# Make sibling imports work whether invoked as module (-m) or script
HERE = os.path.dirname(os.path.abspath(__file__))
MAGNET_ROOT = os.path.dirname(HERE)            # magnet/
PROJECT_ROOT = os.path.dirname(MAGNET_ROOT)    # repo root
if MAGNET_ROOT not in sys.path:
    sys.path.insert(0, MAGNET_ROOT)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from crawler_v2.ai import resolve_llm_choice, synthesize_selectors_for_url

HEALTH_REPORT = os.path.join(MAGNET_ROOT, "_health_report_full.json")
SOURCES_JSON = os.path.join(PROJECT_ROOT, "sources.json")
OUT_DIR = MAGNET_ROOT


def _pick_bait(rule) -> str:
    """Select a bait keyword based on the rule's tags."""
    tags = (rule.get("quality") or {}).get("tags") or []
    tag_str = " ".join(str(t) for t in tags).lower()
    if any(k in tag_str for k in ("anime", "动漫", "动画", "番")):
        return "One Piece"
    if any(k in tag_str for k in ("xxx", "av", "jav", "adult", "成人")):
        return "uncensored"
    if any(k in tag_str for k in ("chinese", "cn", "中文", "电影", "movie")):
        return "复仇者联盟"
    return "Avengers"


def _load_suspect_dead_pairs(name_filter: str = ""):
    """Cross-reference health report's suspect_dead_search list with sources.json
    rules — return list of (name, rule)."""
    with open(HEALTH_REPORT, "r", encoding="utf-8") as f:
        health = json.load(f)
    suspect_names = [
        n for n, info in health.items()
        if "suspect_dead_search" in (info.get("error") or "")
    ]
    if name_filter:
        nf = name_filter.lower()
        suspect_names = [n for n in suspect_names if nf in n.lower()]

    with open(SOURCES_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    name_to_rule = {}
    for ruleset in data.get("rulesets") or []:
        for rule in ruleset.get("rules") or []:
            name_to_rule[rule["site"]["name"]] = rule

    pairs, missing = [], []
    for n in suspect_names:
        if n in name_to_rule:
            pairs.append((n, name_to_rule[n]))
        else:
            missing.append(n)
    if missing:
        print(f"[warn] {len(missing)} suspect names not found in sources.json: {missing}")
    return pairs


def _process_one(name: str, rule: dict, llm, proxy: str) -> dict:
    """One AI-bootstrap pass on a single source. Never raises — returns dict."""
    site = rule.get("site") or {}
    origin = site.get("origin", "")
    template = (rule.get("search") or {}).get("request_template", "")
    if not origin or not template:
        return {"name": name, "skipped": True,
                "error": "missing origin or request_template"}

    origin_clean = origin.split("?")[0].rstrip("/")
    url_template = origin_clean + template
    bait = _pick_bait(rule)

    print(f"\n[{name}] template={url_template} bait={bait}")
    t0 = time.time()
    res = synthesize_selectors_for_url(
        url_template=url_template,
        query=bait,
        llm_choice=llm,
        proxy=proxy,
        site_name=name,
        tags=(rule.get("quality") or {}).get("tags") or [],
    )
    elapsed = int(time.time() - t0)

    if "error" in res:
        return {
            "name": name, "bait_used": bait, "elapsed": elapsed,
            "error": res["error"], "fetcher": res.get("fetcher", "?"),
        }

    rule_draft = res["rule_draft"]
    proposal = rule_draft["_ai_proposal"]

    # Persist single-source draft for human review
    from urllib.parse import urlparse
    host = urlparse(rule_draft["site"]["origin"]).netloc.replace(":", "_") or name.replace("/", "_")
    draft_path = os.path.join(OUT_DIR, f"_ai_draft_{host}.json")
    try:
        with open(draft_path, "w", encoding="utf-8") as f:
            json.dump(rule_draft, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"  [warn] could not write draft: {e}")
        draft_path = ""

    v = proposal["validation"]
    print(f"[{name}] confidence={proposal['confidence']:.0%} "
          f"magnets={v['magnets_found']}/{v['list_items']} "
          f"regex={v['regex_magnets_on_page']} elapsed={elapsed}s")

    return {
        "name": name, "bait_used": bait, "elapsed": elapsed,
        "fetcher": res.get("fetcher"),
        "bytes": res.get("bytes"),
        "confidence": proposal["confidence"],
        "selectors": proposal["selectors"],
        "list_items": v["list_items"],
        "magnets_found": v["magnets_found"],
        "regex_magnets_on_page": v["regex_magnets_on_page"],
        "samples": v["samples"],
        "draft_path": draft_path,
    }


def main():
    ap = argparse.ArgumentParser(description="Batch AI selector synthesis for suspect_dead_search sources")
    ap.add_argument("--proxy",
                    default=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"),
                    help="HTTP proxy for both fetch and LLM (default: env HTTPS_PROXY)")
    ap.add_argument("--filter", default="",
                    help="Only process sources whose name contains this substring")
    ap.add_argument("--out", default=None,
                    help="Output summary path (default: _ai_batch_<ts>.json)")
    args = ap.parse_args()

    llm = resolve_llm_choice()
    if not llm:
        print("ERROR: No LLM API key (set MIMO_API_KEY / DEEPSEEK_API_KEY etc.)")
        sys.exit(2)
    print(f"[llm] using {llm.label} ({llm.provider}); proxy={args.proxy or '(none)'}")

    pairs = _load_suspect_dead_pairs(args.filter)
    print(f"[load] {len(pairs)} suspect_dead_search sources to process\n")

    summary = []
    for i, (name, rule) in enumerate(pairs, 1):
        print(f"\n{'=' * 70}\n  [{i}/{len(pairs)}] {name}\n{'=' * 70}")
        try:
            r = _process_one(name, rule, llm, args.proxy)
        except KeyboardInterrupt:
            print("\n[abort] user interrupt; saving partial summary")
            break
        except Exception as e:
            r = {"name": name, "error": f"unhandled: {e}"}
        summary.append(r)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or os.path.join(OUT_DIR, f"_ai_batch_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "llm": llm.label, "results": summary},
                  f, ensure_ascii=False, indent=2)

    # Console summary
    saved = sum(1 for r in summary if (r.get("magnets_found", 0) > 0))
    print(f"\n\n{'=' * 70}\n  BATCH SUMMARY — {len(summary)} processed, {saved} successful\n{'=' * 70}")
    print(f"  {'name':<35} {'conf':>5}  {'mag':>4}/{'rows':<4}  {'pageMag':>7}  notes")
    print("  " + "-" * 76)
    for r in summary:
        if "error" in r:
            print(f"  {r['name'][:33]:<35} {'-':>5}  {'-':>4}/{'-':<4}  {'-':>7}  ERR: {r['error'][:30]}")
        else:
            conf = r.get("confidence", 0)
            print(f"  {r['name'][:33]:<35} {conf:>4.0%}  "
                  f"{r['magnets_found']:>4}/{r['list_items']:<4}  "
                  f"{r['regex_magnets_on_page']:>7}  bait={r.get('bait_used', '')}")
    print(f"\n  Full report: {out_path}")


if __name__ == "__main__":
    main()
