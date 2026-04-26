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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler.extractor import MagnetExtractor
from crawler.healer import Healer

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')
REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'verify_report.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

BRAINT_BAITS = {
    'ANIME': ['One Piece', 'Naruto', 'Bleach'],
    'CHINESE': ['Inception', 'Inception', 'Big Buck Bunny'],
    'TECH': ['Inception', 'Python', 'Windows 11'],
    'GENERAL': ['Inception', 'Inception', 'Big Buck Bunny', 'Interstellar'],
}


def classify_site(url):
    url_lower = url.lower()
    if any(kw in url_lower for kw in ['anime', 'tosho', 'nyaa', 'bangumi', 'anidex']):
        return 'ANIME'
    if any(kw in url_lower for kw in ['fitgirl', 'skidrow', 'repack']):
        return 'TECH'
    if any(kw in url_lower for kw in [
        'bt', 'cili', 'btdb', 'btso', 'btsow', 'verycd',
        'btcake', 'btfans', 'btbtt', 'limetorrent', 'kickass',
        'extratorrent', 'bitport'
    ]):
        return 'CHINESE'
    return 'GENERAL'


def quick_probe(url, timeout=15):
    try:
        import requests
        resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        return resp.status_code, resp.text
    except Exception:
        return None, None


def verify_rule(rule):
    url = rule['site']['origin']
    extractor = MagnetExtractor(rule)
    category = classify_site(url)
    baits = BRAINT_BAITS.get(category, BRAINT_BAITS['GENERAL'])

    for bait in baits:
        try:
            magnets = extractor.search(bait, limit=5)
            if magnets:
                return 'ok', len(magnets), magnets[0], bait
        except Exception:
            pass

    return 'no_magnets', 0, None, None


def update_health(rule, status, detail, magnets_found=0, sample=None):
    if 'health' not in rule:
        rule['health'] = {}
    if status == 'ok' or status == 'healed':
        rule['health']['status'] = 'green'
    elif status in ('waf', 'parsing_failed'):
        rule['health']['status'] = 'yellow'
    else:
        rule['health']['status'] = 'gray'
    rule['health']['status_detail'] = detail
    rule['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()
    rule['health']['magnets_found'] = magnets_found
    if sample:
        rule['health']['sample_title'] = sample.get('title', '')[:80]


def main():
    print("=" * 60)
    print("  Magnet Source Batch Verify + Auto-Heal")
    print("=" * 60)

    if not os.path.exists(SOURCES_FILE):
        print(f"ERROR: {SOURCES_FILE} not found")
        sys.exit(1)

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rules = []
    for ruleset in data.get('rulesets', []):
        rules.extend(ruleset.get('rules', []))

    total = len(rules)
    print(f"\nTotal sources to verify: {total}\n")

    healer = Healer()

    summary = {
        'ok': [],
        'healed': [],
        'waf': [],
        'parsing_failed': [],
        'expired': [],
        '404': [],
        'unreachable': [],
    }

    for i, rule in enumerate(rules):
        url = rule['site']['origin']
        name = rule['site'].get('name', '')
        print(f"[{i + 1}/{total}] {name} ({url})")

        status, count, sample, bait = verify_rule(rule)

        if status == 'ok':
            update_health(rule, 'ok', 'ok', count, sample)
            summary['ok'].append({'url': url, 'name': name, 'magnets': count, 'bait': bait})
            print(f"  OK - {count} magnets (bait: {bait})")
            if sample:
                print(f"       sample: {sample.get('title', '')[:60]}")
            continue

        print(f"  No magnets from quick search, probing site accessibility...")

        status_code, html = quick_probe(url)
        if status_code is None:
            update_health(rule, 'unreachable', 'unreachable')
            summary['unreachable'].append({'url': url, 'name': name})
            print(f"  UNREACHABLE - DNS/connection failed")
            continue

        if status_code == 404:
            update_health(rule, '404', '404')
            summary['404'].append({'url': url, 'name': name})
            print(f"  404 - Page not found")
            continue

        print(f"  Site is up (HTTP {status_code}), starting auto-heal...")

        heal_result = healer.heal_and_retry(rule)
        heal_status = heal_result.get('status')
        magnets_found = heal_result.get('magnets_found', 0)
        heal_sample = heal_result.get('sample')

        if heal_status == 'ok':
            update_health(rule, 'ok', 'ok', magnets_found, heal_sample)
            summary['ok'].append({
                'url': url, 'name': name,
                'magnets': magnets_found,
                'bait': heal_result.get('bait_used', ''),
                'method': heal_result.get('method', 'heal')
            })
            print(f"  HEAL-OK - {magnets_found} magnets (method: {heal_result.get('method', '')})")

        elif heal_status == 'healed':
            new_sels = heal_result.get('healed_selectors', {})
            if new_sels:
                rule['search']['parse_metadata']['selectors'] = new_sels
                print(f"  Selectors updated: {new_sels}")
            update_health(rule, 'healed', 'healed', magnets_found, heal_sample)
            summary['healed'].append({
                'url': url, 'name': name,
                'magnets': magnets_found,
                'method': heal_result.get('method', ''),
                'new_selectors': new_sels
            })
            print(f"  HEALED - {magnets_found} magnets (method: {heal_result.get('method', '')})")

        elif heal_status in ('expired', '404', 'unreachable'):
            update_health(rule, heal_status, heal_status)
            summary.setdefault(heal_status, []).append({
                'url': url, 'name': name,
                'error': heal_result.get('error', '')
            })
            print(f"  {heal_status.upper()} - {heal_result.get('error', '')}")

        elif heal_status == 'waf':
            update_health(rule, 'waf', 'waf')
            summary['waf'].append({'url': url, 'name': name})
            print(f"  WAF - Blocked by WAF")

        else:
            update_health(rule, 'parsing_failed', 'parsing_failed')
            summary['parsing_failed'].append({
                'url': url, 'name': name,
                'error': heal_result.get('error', '')
            })
            print(f"  PARSE-FAIL - {heal_result.get('error', '')}")

        time.sleep(1)

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


if __name__ == '__main__':
    main()
