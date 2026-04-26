#!/usr/bin/env python3
"""
P1: Discover + verify new magnet search sources.
Probe a curated list of known-active torrent/magnet search sites,
verify they actually return magnet links, and add working ones to sources.json.

Uses direct HTTP probing (no search engine dependency).
"""

import json
import os
import sys
import time
import hashlib
import copy
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')
REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'discover_report.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

CANDIDATES = [
    {'name': 'nyaa.si', 'origin': 'https://nyaa.si', 'search': '/?f=0&q={query}', 'tags': ['ANIME']},
    {'name': '1337x.to', 'origin': 'https://1337x.to', 'search': '/search/{query}/1/', 'tags': ['GENERAL']},
    {'name': 'thepiratebay.org', 'origin': 'https://thepiratebay.org', 'search': '/search.php?q={query}', 'tags': ['GENERAL']},
    {'name': 'rarbg.to', 'origin': 'https://rarbg.to', 'search': '/torrents.php?search={query}', 'tags': ['GENERAL']},
    {'name': 'torrentgalaxy.to', 'origin': 'https://torrentgalaxy.to', 'search': '/torrents.php?search={query}', 'tags': ['GENERAL']},
    {'name': 'magnetdl.com', 'origin': 'https://magnetdl.com', 'search': '/{query}/', 'tags': ['GENERAL']},
    {'name': 'yts.mx', 'origin': 'https://yts.mx', 'search': '/browse-movies/{query}', 'tags': ['GENERAL']},
    {'name': 'eztv.re', 'origin': 'https://eztv.re', 'search': '/search/{query}', 'tags': ['GENERAL']},
    {'name': 'limetorrents.pro', 'origin': 'https://limetorrents.pro', 'search': '/search/all/{query}/', 'tags': ['GENERAL']},
    {'name': 'glodls.to', 'origin': 'https://glodls.to', 'search': '/search_results.php?search={query}', 'tags': ['GENERAL']},
    {'name': 'torrentz2eu.org', 'origin': 'https://torrentz2eu.org', 'search': '/search?q={query}', 'tags': ['GENERAL']},
    {'name': 'idope.se', 'origin': 'https://idope.se', 'search': '/torrent-list/{query}/', 'tags': ['GENERAL']},
    {'name': 'aiosearch.com', 'origin': 'https://aiosearch.com', 'search': '/search?q={query}', 'tags': ['GENERAL']},
    {'name': 'snowfl.com', 'origin': 'https://snowfl.com', 'search': '/{query}/1', 'tags': ['GENERAL']},
    {'name': 'torrentprojects.se', 'origin': 'https://torrentprojects.se', 'search': '/?q={query}', 'tags': ['GENERAL']},
    {'name': 'solidtorrents.to', 'origin': 'https://solidtorrents.to', 'search': '/search?q={query}', 'tags': ['GENERAL']},
    {'name': 'btscene.org', 'origin': 'https://btscene.org', 'search': '/search/{query}', 'tags': ['GENERAL']},
    {'name': 'yourbittorrent.com', 'origin': 'https://yourbittorrent.com', 'search': '/?q={query}', 'tags': ['GENERAL']},
    {'name': 'sharetorrent.org', 'origin': 'https://sharetorrent.org', 'search': '/search?q={query}', 'tags': ['GENERAL']},
    {'name': 'demonoid.is', 'origin': 'https://demonoid.is', 'search': '/files/?q={query}', 'tags': ['GENERAL']},
    {'name': 'rutor.info', 'origin': 'http://rutor.info', 'search': '/search/{query}', 'tags': ['GENERAL']},
    {'name': 'rutracker.org', 'origin': 'https://rutracker.org', 'search': '/forum/tracker.php?nm={query}', 'tags': ['GENERAL']},
    {'name': 'anidex.info', 'origin': 'https://anidex.info', 'search': '/?q={query}', 'tags': ['ANIME']},
    {'name': 'animetosho.org', 'origin': 'https://animetosho.org', 'search': '/search?q={query}', 'tags': ['ANIME']},
    {'name': 'dmhy.org', 'origin': 'https://share.dmhy.org', 'search': '/topics/list?keyword={query}', 'tags': ['ANIME']},
    {'name': 'acg.rip', 'origin': 'https://acg.rip', 'search': '/search/?q={query}', 'tags': ['ANIME']},
    {'name': 'mteam.cc', 'origin': 'https://kp.mteam.cc', 'search': '/torrents.php?search={query}', 'tags': ['CHINESE']},
    {'name': 'pt.soulvoice.club', 'origin': 'https://pt.soulvoice.club', 'search': '/torrents.php?search={query}', 'tags': ['CHINESE']},
    {'name': 'hdhome.org', 'origin': 'https://hdhome.org', 'search': '/torrents.php?search={query}', 'tags': ['CHINESE']},
    {'name': 'audiences.me', 'origin': 'https://audiences.me', 'search': '/torrents.php?search={query}', 'tags': ['CHINESE']},
]

TEST_QUERIES = {
    'ANIME': ['One Piece', 'Naruto'],
    'CHINESE': ['The Dark Knight', 'Interstellar'],
    'GENERAL': ['Inception', 'Big Buck Bunny'],
}


def make_rule_id(origin):
    return hashlib.md5(origin.encode()).hexdigest()[:12]


def probe_site(candidate, test_queries):
    origin = candidate['origin']
    search_path = candidate['search']

    for query in test_queries:
        url = origin.rstrip('/') + search_path.replace('{query}', query)
        try:
            resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        except requests.exceptions.Timeout:
            return {'status': 'unreachable', 'error': 'Timeout'}
        except requests.exceptions.ConnectionError:
            return {'status': 'unreachable', 'error': 'DNS/Connection failed'}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

        if resp.status_code == 404:
            continue
        if resp.status_code >= 500:
            continue

        html = resp.text
        soup = BeautifulSoup(html, 'lxml')

        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        if magnets:
            magnet_href = magnets[0].get('href', '')
            title = ''
            parent = magnets[0].parent
            for _ in range(3):
                if parent:
                    links = parent.find_all('a', href=True)
                    for a in links:
                        if a.get_text(strip=True) and 'magnet:' not in a.get('href', ''):
                            title = a.get_text(strip=True)
                            break
                    if title:
                        break
                    parent = parent.parent

            return {
                'status': 'ok',
                'magnets_found': len(magnets),
                'sample_magnet': magnet_href[:80],
                'sample_title': title[:80],
                'query': query,
                'html_len': len(html),
            }

        if len(html) < 500:
            if 'cloudflare' in html.lower() or 'fingerprint' in html.lower():
                return {'status': 'waf', 'error': 'JS challenge'}
            continue

    return {'status': 'parsing_failed', 'error': 'No magnet links found in search results'}


def build_rule(candidate, probe_result):
    return {
        'id': make_rule_id(candidate['origin']),
        'site': {
            'name': candidate['name'],
            'origin': candidate['origin'],
        },
        'capabilities': {
            'supports_search': True,
            'supports_detail': False,
        },
        'search': {
            'request_template': candidate['search'],
            'timeout_ms': 10000,
            'retries': {
                'max_attempts': 3,
                'backoff_ms': 1000,
            },
            'requires_waf_bypass': probe_result.get('status') == 'waf',
            'parse_metadata': {
                'selectors': {
                    'list_item': 'div.item',
                    'title': 'a[href^="magnet:"]',
                    'magnet': 'a[href^="magnet:"]',
                    'size': 'span.size',
                    'date': 'span.date',
                }
            }
        },
        'quality': {
            'score': 70,
            'tags': [],
        },
        'health': {
            'status': 'green' if probe_result.get('status') == 'ok' else 'yellow',
            'status_detail': probe_result.get('status', 'unknown'),
            'last_checked_at': datetime.now(timezone.utc).isoformat(),
            'magnets_found': probe_result.get('magnets_found', 0),
            'sample_title': probe_result.get('sample_title', ''),
        },
    }


def main():
    print("=" * 60)
    print("  P1: Discover New Magnet Search Sources")
    print("=" * 60)

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    existing_origins = set()
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            existing_origins.add(r['site']['origin'])

    print(f"\nExisting sources: {len(existing_origins)}")
    print(f"Candidates to probe: {len(CANDIDATES)}\n")

    new_ok = []
    new_waf = []
    new_failed = []
    skipped = 0

    for i, cand in enumerate(CANDIDATES):
        if cand['origin'] in existing_origins:
            skipped += 1
            continue

        name = cand['name']
        origin = cand['origin']
        print(f"[{i+1}/{len(CANDIDATES)}] {name} ({origin})")

        tags = cand.get('tags', ['GENERAL'])
        queries = TEST_QUERIES.get(tags[0], TEST_QUERIES['GENERAL'])

        result = probe_site(cand, queries)
        status = result['status']

        if status == 'ok':
            rule = build_rule(cand, result)
            new_ok.append((cand, rule, result))
            print(f"  OK - {result['magnets_found']} magnets (query: {result['query']})")
            print(f"       sample: {result.get('sample_title', '')}")
        elif status == 'waf':
            new_waf.append((cand, result))
            print(f"  WAF - {result.get('error', '')}")
        elif status in ('unreachable', 'error'):
            new_failed.append((cand, result))
            print(f"  {status.upper()} - {result.get('error', '')}")
        else:
            new_failed.append((cand, result))
            print(f"  {status.upper()} - {result.get('error', '')}")

        time.sleep(0.5)

    ruleset = data['rulesets'][0] if data.get('rulesets') else {'ruleset_id': 'base', 'priority': 1, 'max_sources_per_search': 10, 'rules': []}

    for cand, rule, result in new_ok:
        ruleset['rules'].append(rule)
        print(f"  Added: {cand['name']}")

    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))

    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'candidates_probed': len(CANDIDATES) - skipped,
        'skipped_existing': skipped,
        'new_ok': len(new_ok),
        'new_waf': len(new_waf),
        'new_failed': len(new_failed),
        'details': {
            'ok': [{'name': c['name'], 'origin': c['origin'], 'magnets': r['magnets_found']} for c, _, r in new_ok],
            'waf': [{'name': c['name'], 'origin': c['origin']} for c, _ in new_waf],
            'failed': [{'name': c['name'], 'origin': c['origin'], 'error': r.get('error', '')} for c, r in new_failed],
        }
    }
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("  DISCOVERY REPORT")
    print("=" * 60)
    print(f"  Probed: {len(CANDIDATES) - skipped}  |  Skipped: {skipped}")
    print(f"  NEW OK:   {len(new_ok)}")
    for c, _, r in new_ok:
        print(f"    + {c['name']} ({r['magnets_found']} magnets)")
    print(f"  NEW WAF:  {len(new_waf)}")
    for c, _ in new_waf:
        print(f"    ! {c['name']}")
    print(f"  FAILED:   {len(new_failed)}")
    print(f"\n  Total sources now: {data['meta']['total_rules']}")
    print(f"  Report: {REPORT_FILE}")
    print("=" * 60)


if __name__ == '__main__':
    main()
