#!/usr/bin/env python3
"""
Batch verify + auto-heal script for magnet sources.
Reads sources.json -> tests each source -> auto-heals -> updates health status -> writes back.
No sources are deleted; only health/status fields are updated.
"""

import json
import sys
import os
import time
from datetime import datetime, timezone

# v0.3.12: bait corpus now contains user-supplied Unicode (CJK, Latin-extended,
# Cyrillic, …). Windows default GBK console can't encode all of them. Force
# UTF-8 on stdout so prints don't crash. Safe no-op on systems already UTF-8.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# v0.3.5: switched to v2 stack so production batch verification benefits from
# the Scrapling Fetcher (TLS impersonation), StealthyFetcher (anti-WAF), AND
# the new detail_follow_v2 capability (zero-config two-hop magnet harvesting).
from crawler.extractor import MagnetExtractor
from crawler_v2.extractor import MagnetExtractorV2
from crawler_v2.healer import HealerV2 as Healer
import telemetry as _telemetry

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')
REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'verify_report.json')

# v0.3.12: populated by _init_telemetry() at startup. None = no telemetry cache
# available → all guards degrade to no-op (static baits, no host_active pin).
_TELEMETRY = None

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

BRAINT_BAITS = {
    'ANIME': ['One Piece', 'Naruto', 'Bleach'],
    # v0.3.11: CHINESE bucket previously held English baits (Inception / Big Buck
    # Bunny) which return 0 results on Chinese sites — caused 5+ false-yellow
    # demotions of high-traffic sources (磁力魔/种子吧/美剧迷). Real-user
    # telemetry shows these sites work fine with Chinese queries; align baits
    # to actual usage. Mix in English fallback for hybrid sites.
    'CHINESE': ['复仇者联盟', '速度与激情', '蜘蛛侠', '三体', 'Avengers', 'Inception'],
    'ADULT': ['SSIS', 'MIDV', 'STARS', 'JUL'],
    'TECH': ['Inception', 'Python', 'Windows 11'],
    'GENERAL': ['Inception', 'Avengers', 'Interstellar', 'Big Buck Bunny'],
}


def classify_site(url):
    url_lower = url.lower()
    if any(kw in url_lower for kw in ['anime', 'tosho', 'nyaa', 'bangumi', 'anidex']):
        return 'ANIME'
    if any(kw in url_lower for kw in ['fitgirl', 'skidrow', 'repack']):
        return 'TECH'
    # v0.3.11: ADULT before CHINESE — javbus/rrjav use code-style queries (SSIS-xxx)
    if any(kw in url_lower for kw in ['javbus', 'rrjav', 'jav', 'sukebei']):
        return 'ADULT'
    # v0.3.11: extended Chinese-site detection — many .top/.cyou/.club/.work
    # zhongziba/cilimao/zzb/kd... bt-mirror domains needed Chinese baits
    if any(kw in url_lower for kw in [
        'bt', 'cili', 'btdb', 'btso', 'btsow', 'verycd',
        'btcake', 'btfans', 'btbtt', 'limetorrent', 'kickass',
        'extratorrent', 'bitport', 'zhongzi', 'zzb', 'kd7',
        'mag', 'meiju', '6v', 'sofan',
    ]):
        return 'CHINESE'
    if url_lower.endswith(('.cn', '.top', '.cyou', '.club', '.work', '.biz', '.de')):
        return 'CHINESE'
    return 'GENERAL'


def quick_probe(url, timeout=15, proxy=None):
    try:
        import requests
        resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True,
                            proxies={"http": proxy, "https": proxy} if proxy else None)
        return resp.status_code, resp.text
    except Exception:
        return None, None


def verify_rule(rule, proxy=None):
    tier_override = rule.get('tier_override')
    if tier_override and tier_override.get('tier'):
        url = rule['site']['origin']
        category = classify_site(url)
        baits = BRAINT_BAITS.get(category, BRAINT_BAITS['GENERAL'])
        for bait in baits:
            try:
                from magnet.crawler_v3.orchestrator import search as v3_search
                results = v3_search(rule, bait, limit=5)
                if results:
                    sample = {"title": results[0].title, "magnet": results[0].magnet}
                    return 'ok', len(results), sample, bait
            except Exception as e:
                pass
        return 'no_magnets', 0, None, None

    url = rule['site']['origin']
    extractor = MagnetExtractorV2(rule, proxy=proxy)
    category = classify_site(url)
    baits = BRAINT_BAITS.get(category, BRAINT_BAITS['GENERAL'])

    for bait in baits:
        try:
            magnets = extractor.search(bait, limit=5, fast=True)
            if magnets:
                return 'ok', len(magnets), magnets[0], bait
        except Exception:
            pass

    return 'no_magnets', 0, None, None


def _trigger_brand_rediscovery(rules, summary, dead_threshold=0.5):
    """When ≥ 50% of a brand_family's rules are gray after verify, fire DDG
    rediscovery and print candidates. Pure side-effect: prints + returns dict.
    Does NOT auto-patch sources.json (operator decides which candidate to use).
    """
    try:
        from discovery.brand_rediscovery import (
            DEFAULT_FAMILIES, find_brand_domains,
        )
    except ImportError:
        return {}

    # Gray names from this run: union of unreachable/404/expired
    gray_names = set()
    for cat in ('unreachable', '404', 'expired'):
        for s in summary.get(cat, []):
            gray_names.add(s['name'])

    # Group rules by brand_family
    family_stats = {}  # fid → [total, dead]
    family_rules = {}  # fid → [rule]
    for r in rules:
        fid = (r.get('capabilities') or {}).get('brand_family')
        if not fid:
            continue
        family_stats.setdefault(fid, [0, 0])
        family_rules.setdefault(fid, []).append(r)
        family_stats[fid][0] += 1
        if r['site']['name'] in gray_names:
            family_stats[fid][1] += 1

    print()
    print("=" * 60)
    print("  Brand-family rediscovery scan")
    print("=" * 60)

    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    fid_to_default = {f.id: f for f in DEFAULT_FAMILIES}
    triggered = {}
    for fid, (total, dead) in family_stats.items():
        ratio = dead / total if total else 0.0
        marker = "TRIGGER" if ratio >= dead_threshold else "ok"
        print(f"  [{fid:6s}] {dead}/{total} dead ({ratio:.0%}) — {marker}")
        if ratio < dead_threshold:
            continue
        family = fid_to_default.get(fid)
        if not family:
            print(f"    (no DEFAULT_FAMILIES entry for {fid!r}, skipping rediscovery)")
            continue
        print(f"    → calling discovery.brand_rediscovery.find_brand_domains({fid!r})")
        try:
            cands = find_brand_domains(family, proxy=proxy,
                                       sources_json_path=SOURCES_FILE)
        except Exception as e:
            print(f"    rediscovery failed: {e}")
            continue
        winners = [c for c in cands if c.magnets_on_home > 0 or c.brand_hit]
        triggered[fid] = [c.host for c in winners[:5]]
        if not winners:
            print(f"    no usable candidates found")
            continue
        print(f"    candidates ({len(winners)}):")
        for c in winners[:5]:
            tag = "🟢 magnet" if c.magnets_on_home else "🔵 brand"
            print(f"      {tag}  {c.host:<28} title={c.title[:50]!r}")
    return triggered


def _init_telemetry():
    """Load user analytics cache (if present) and override the CHINESE +
    GENERAL bait buckets with high-frequency, high-hit-rate real-user queries.

    This is Karpathy-style ground-truth alignment: whatever real users
    successfully searched for is, by definition, the bait most likely to
    return results on a live source. Falls back silently when no cache exists.
    """
    global _TELEMETRY
    _TELEMETRY = _telemetry.load_telemetry()
    if not _TELEMETRY:
        print("[telemetry] no cache at admin-server/cache/batches.json — "
              "using static BRAINT_BAITS only")
        return
    meta = _TELEMETRY['meta']
    print(f"[telemetry] loaded {meta['events']:,} events from "
          f"{meta['batches']} batches "
          f"({len(_TELEMETRY['host_stats'])} hosts, "
          f"{len(_TELEMETRY['query_stats'])} unique queries)")
    tq = _telemetry.top_queries_by_lang(_TELEMETRY)
    if tq.get('zh'):
        # Front-load real-user queries, keep 2 static fallbacks at the tail.
        BRAINT_BAITS['CHINESE'] = tq['zh'] + ['Avengers', 'Inception']
        print(f"[telemetry] CHINESE bait override: {BRAINT_BAITS['CHINESE']}")
    if tq.get('en'):
        BRAINT_BAITS['GENERAL'] = tq['en'] + ['Inception', 'Big Buck Bunny']
        print(f"[telemetry] GENERAL bait override: {BRAINT_BAITS['GENERAL']}")
    active = sum(1 for h in _TELEMETRY['host_stats']
                 if _telemetry.host_active(_TELEMETRY, h))
    print(f"[telemetry] {active} hosts have ≥10 successful user fetches "
          f"in the last 30 days → protected from gray downgrade")


def update_health(rule, status, detail, magnets_found=0, sample=None):
    if 'health' not in rule:
        rule['health'] = {}

    if status == 'ok' or status == 'healed':
        new_status = 'green'
    elif status in ('waf', 'parsing_failed'):
        new_status = 'yellow'
    else:
        new_status = 'gray'

    # v0.3.12: User-active guard. If verify wants to downgrade to gray but the
    # last 30 days of real user telemetry show the host has ≥10 successful
    # magnet fetches, refuse to demote past yellow. The verifier is a
    # synthetic experiment; user telemetry is the physical experiment.
    # The latter always trumps the former.
    site = rule.get('site') or {}
    origin = site.get('origin', '')
    name = site.get('name', '')
    # Frontend reports `src` as either hostname or site.name — match both.
    user_active = bool(_TELEMETRY) and _telemetry.host_active(
        _TELEMETRY, origin, name=name)
    if user_active and new_status == 'gray':
        ok_count = _telemetry.host_ok_count(_TELEMETRY, origin, name=name)
        print(f"  🚨 [user_active] {name} verify→gray but {ok_count} real-user "
              f"successes in 30d — pinning to yellow")
        new_status = 'yellow'
        detail = 'parsing_failed'  # nearest schema-legal enum
        rule['health']['user_active'] = True
        rule['health']['user_ok_30d'] = ok_count
    elif user_active:
        # Still record the signal for the dashboard, but don't override status.
        rule['health']['user_active'] = True
        rule['health']['user_ok_30d'] = _telemetry.host_ok_count(
            _TELEMETRY, origin, name=name)
    else:
        # Clear stale guard flag if telemetry no longer supports it.
        rule['health'].pop('user_active', None)
        rule['health'].pop('user_ok_30d', None)

    rule['health']['status'] = new_status
    rule['health']['status_detail'] = detail
    rule['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()
    rule['health']['magnets_found'] = magnets_found
    if sample:
        rule['health']['sample_title'] = sample.get('title', '')[:80]


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Magnet Source Batch Verify + Auto-Heal")
    ap.add_argument("--names", default=None,
                    help="Comma-separated list of site names to verify (default: all)")
    ap.add_argument("--max-count", type=int, default=None,
                    help="Verify at most N rules (default: all)")
    ap.add_argument("--filter-status", default=None,
                    help="Only verify rules whose health.status matches (green|yellow|gray)")
    ap.add_argument("--no-write", action="store_true",
                    help="Do not write back to sources.json (for dry runs)")
    ap.add_argument("--concurrent", type=int, default=1,
                    help="Max parallel workers (default: 1 = sequential). Each worker "
                         "owns its own HealerV2 instance — cache is not shared.")
    ap.add_argument("--proxy", default=None,
                    help="HTTP proxy URL (e.g. http://127.0.0.1:33210) for all fetches")
    args = ap.parse_args()

    print("=" * 60)
    print("  Magnet Source Batch Verify + Auto-Heal")
    print("=" * 60)

    # v0.3.12: pull baits + active-host guard from real user analytics.
    _init_telemetry()

    if not os.path.exists(SOURCES_FILE):
        print(f"ERROR: {SOURCES_FILE} not found")
        sys.exit(1)

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rules = []
    for ruleset in data.get('rulesets', []):
        rules.extend(ruleset.get('rules', []))

    # Apply CLI filters
    if args.names:
        wanted = set(s.strip() for s in args.names.split(',') if s.strip())
        rules = [r for r in rules if (r.get('site') or {}).get('name') in wanted]
    if args.filter_status:
        rules = [r for r in rules
                 if (r.get('health') or {}).get('status') == args.filter_status]
    if args.max_count:
        rules = rules[:args.max_count]

    total = len(rules)
    print(f"\nTotal sources to verify: {total}\n")
    if total == 0:
        print("No rules match filters; nothing to do.")
        return

    healer = Healer(proxy=args.proxy)

    summary = {
        'ok': [],
        'healed': [],
        'waf': [],
        'parsing_failed': [],
        'expired': [],
        '404': [],
        'unreachable': [],
    }

    # Per-rule worker — used both in sequential and concurrent modes. Each
    # worker owns its own HealerV2 (no shared mutable state across workers).
    # Summary updates go through `summary_lock` so dict mutations stay safe.
    import threading
    summary_lock = threading.Lock()

    def _process_rule(idx, rule):
        url = rule['site']['origin']
        name = rule['site'].get('name', '')
        # Buffer output so concurrent prints don't interleave per-source.
        log = [f"[{idx + 1}/{total}] {name} ({url})"]

        status, count, sample, bait = verify_rule(rule, proxy=args.proxy)

        if status == 'ok':
            update_health(rule, 'ok', 'ok', count, sample)
            with summary_lock:
                summary['ok'].append({'url': url, 'name': name, 'magnets': count, 'bait': bait})
            log.append(f"  OK - {count} magnets (bait: {bait})")
            if sample:
                log.append(f"       sample: {sample.get('title', '')[:60]}")
            print('\n'.join(log), flush=True)
            return

        log.append(f"  No magnets from quick search, probing site accessibility...")
        status_code, html = quick_probe(url, proxy=args.proxy)
        if status_code is None:
            update_health(rule, 'unreachable', 'unreachable')
            with summary_lock:
                summary['unreachable'].append({'url': url, 'name': name})
            log.append(f"  UNREACHABLE - DNS/connection failed")
            print('\n'.join(log), flush=True)
            return

        if status_code == 404:
            update_health(rule, '404', '404')
            with summary_lock:
                summary['404'].append({'url': url, 'name': name})
            log.append(f"  404 - Page not found")
            print('\n'.join(log), flush=True)
            return

        log.append(f"  Site is up (HTTP {status_code}), starting auto-heal...")
        # Local healer per call: HealerV2 caches are per-instance.
        local_healer = Healer(proxy=args.proxy)
        heal_result = local_healer.heal_and_retry(rule)
        heal_status = heal_result.get('status')
        magnets_found = heal_result.get('magnets_found', 0)
        heal_sample = heal_result.get('sample')

        if heal_status == 'ok':
            update_health(rule, 'ok', 'ok', magnets_found, heal_sample)
            with summary_lock:
                summary['ok'].append({
                    'url': url, 'name': name, 'magnets': magnets_found,
                    'bait': heal_result.get('bait_used', ''),
                    'method': heal_result.get('method', 'heal')
                })
            log.append(f"  HEAL-OK - {magnets_found} magnets (method: {heal_result.get('method', '')})")
        elif heal_status == 'healed':
            new_sels = heal_result.get('healed_selectors', {})
            if new_sels:
                rule['search']['parse_metadata']['selectors'] = new_sels
                log.append(f"  Selectors updated: {new_sels}")
            # v0.3.13: save healed search path (from search_path_probe on 404)
            new_template = heal_result.get('healed_request_template')
            if new_template:
                rule['search']['request_template'] = new_template
                log.append(f"  Search path updated: {new_template}")
            update_health(rule, 'healed', 'healed', magnets_found, heal_sample)
            with summary_lock:
                summary['healed'].append({
                    'url': url, 'name': name, 'magnets': magnets_found,
                    'method': heal_result.get('method', ''),
                    'new_selectors': new_sels
                })
            log.append(f"  HEALED - {magnets_found} magnets (method: {heal_result.get('method', '')})")
        elif heal_status in ('expired', '404', 'unreachable'):
            update_health(rule, heal_status, heal_status)
            with summary_lock:
                summary.setdefault(heal_status, []).append({
                    'url': url, 'name': name, 'error': heal_result.get('error', '')
                })
            log.append(f"  {heal_status.upper()} - {heal_result.get('error', '')}")
        elif heal_status == 'waf':
            update_health(rule, 'waf', 'waf')
            with summary_lock:
                summary['waf'].append({'url': url, 'name': name})
            log.append(f"  WAF - Blocked by WAF")
        else:
            update_health(rule, 'parsing_failed', 'parsing_failed')
            with summary_lock:
                summary['parsing_failed'].append({
                    'url': url, 'name': name, 'error': heal_result.get('error', '')
                })
            log.append(f"  PARSE-FAIL - {heal_result.get('error', '')}")
        print('\n'.join(log), flush=True)

    # Dispatch sequentially or concurrently based on --concurrent
    if args.concurrent <= 1:
        for i, rule in enumerate(rules):
            _process_rule(i, rule)
            time.sleep(1)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        print(f"\n[concurrent] Running {total} rules with {args.concurrent} workers")
        with ThreadPoolExecutor(max_workers=args.concurrent) as ex:
            futures = [ex.submit(_process_rule, i, r) for i, r in enumerate(rules)]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    print(f"[worker error] {e}", flush=True)

    if args.no_write:
        print(f"\n[--no-write] skipping sources.json update (dry run)")
    else:
        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\nSources updated and saved to {SOURCES_FILE}")

    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'total': total,
        'summary': {k: len(v) for k, v in summary.items()},
        'details': summary
    }
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("  VERIFICATION REPORT")
    print("=" * 60)
    print(f"  Total sources: {total}")
    print()
    print(f"  GREEN (ok):        {len(summary['ok'])}")
    for s in summary['ok']:
        print(f"    + {s['name']} ({s['magnets']} magnets)")
    print()
    print(f"  GREEN (healed):    {len(summary['healed'])}")
    for s in summary['healed']:
        print(f"    ~ {s['name']} ({s['magnets']} magnets, {s.get('method', '')})")
    print()
    print(f"  YELLOW (waf):      {len(summary['waf'])}")
    for s in summary['waf']:
        print(f"    ! {s['name']}")
    print()
    print(f"  YELLOW (parse):    {len(summary['parsing_failed'])}")
    for s in summary['parsing_failed']:
        print(f"    ! {s['name']}")
    print()
    dead = len(summary.get('expired', [])) + len(summary.get('404', [])) + len(summary.get('unreachable', []))
    print(f"  GRAY (dead):       {dead}")
    for cat in ('expired', '404', 'unreachable'):
        for s in summary.get(cat, []):
            print(f"    x {s['name']} [{cat}]")
    print()
    print(f"  Report saved to {REPORT_FILE}")
    print("=" * 60)

    # v0.3.5: Brand-family rediscovery hook — when ≥ 50% of a family's
    # rules went gray this run, automatically run DDG search to suggest
    # replacement domains. Output goes to console + report file.
    triggered = _trigger_brand_rediscovery(rules, summary)
    if triggered:
        try:
            with open(REPORT_FILE, 'r', encoding='utf-8') as f:
                rep = json.load(f)
            rep['rediscovery_suggestions'] = triggered
            with open(REPORT_FILE, 'w', encoding='utf-8') as f:
                json.dump(rep, f, indent=2, ensure_ascii=False)
        except (OSError, json.JSONDecodeError):
            pass


if __name__ == '__main__':
    main()
