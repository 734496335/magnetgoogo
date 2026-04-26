#!/usr/bin/env python3
"""
Test all magnet-related sites discovered from navigation hubs.
"""
import json, os, sys, time, hashlib, re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

with open('nav_extracted.json', 'r', encoding='utf-8') as f:
    nav_data = json.load(f)

CANDIDATES = []
for domain, info in nav_data['magnet'].items():
    CANDIDATES.append({'name': domain, 'origin': info['url'].rstrip('/')})

EXTRA = [
    {'name': 'bitcq.com', 'origin': 'https://bitcq.com'},
    {'name': 'u3c3.org', 'origin': 'https://u3c3.org'},
    {'name': '1337x.gd', 'origin': 'https://1337x.gd'},
    {'name': 'tokyotosho.info', 'origin': 'https://www.tokyotosho.info'},
    {'name': 'bs5.org', 'origin': 'https://bs5.org'},
    {'name': 'cilimao.im', 'origin': 'https://cilimao.im'},
    {'name': 'clm8.top', 'origin': 'https://clm8.top'},
]
CANDIDATES.extend(EXTRA)

SEARCH_PATTERNS = [
    '/search?q={query}',
    '/search/{query}/',
    '/?q={query}',
    '/?wd={query}',
    '/s/{query}',
    '/search.php?q={query}',
    '/search.php?keywords={query}',
]

TEST_QUERIES = ['Ubuntu', 'Big Buck Bunny', 'One Piece']
hash_re = re.compile(r'[0-9A-Fa-f]{40}')


def test_site(cand):
    origin = cand['origin']
    for pattern in SEARCH_PATTERNS:
        for query in TEST_QUERIES:
            url = origin.rstrip('/') + pattern.replace('{query}', query)
            try:
                resp = requests.get(url, timeout=12, headers=HEADERS, allow_redirects=True)
            except requests.exceptions.Timeout:
                return {'status': 'unreachable', 'error': 'Timeout'}
            except requests.exceptions.ConnectionError:
                return {'status': 'unreachable', 'error': 'DNS/Connection failed'}
            except Exception as e:
                return {'status': 'error', 'error': str(e)[:50]}

            if resp.status_code != 200:
                continue
            if len(resp.text) < 300:
                continue

            soup = BeautifulSoup(resp.text, 'lxml')
            title = soup.title.string[:50] if soup.title and soup.title.string else ''
            if 'just a moment' in title.lower():
                return {'status': 'waf', 'error': 'Cloudflare'}

            magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
            hashes = set()
            for a in soup.find_all('a', href=True):
                m = hash_re.search(a['href'])
                if m:
                    hashes.add(m.group(1))

            if magnets:
                return {
                    'status': 'ok',
                    'magnets': len(magnets),
                    'sample': magnets[0].get('href', '')[:80],
                    'pattern': pattern,
                    'query': query,
                    'title': title,
                }
            if len(hashes) >= 3:
                return {
                    'status': 'ok_hash',
                    'magnets': len(hashes),
                    'pattern': pattern,
                    'query': query,
                    'title': title,
                }
    return {'status': 'no_results', 'error': 'No magnets found with any pattern/query combo'}


with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

existing = set()
for rs in data.get('rulesets', []):
    for r in rs.get('rules', []):
        existing.add(r['site']['origin'])

print("=" * 60)
print(f"  Testing {len(CANDIDATES)} nav-discovered magnet sites")
print("=" * 60)

new_ok = []
for i, cand in enumerate(CANDIDATES):
    if cand['origin'] in existing:
        print(f"[{i+1}/{len(CANDIDATES)}] {cand['name']:35s} SKIP (existing)")
        continue

    print(f"[{i+1}/{len(CANDIDATES)}] {cand['name']:35s}", end='')
    result = test_site(cand)
    st = result['status']

    if st in ('ok', 'ok_hash'):
        new_ok.append((cand, result))
        print(f" OK! {result['magnets']} magnets (pattern={result['pattern']} query={result['query']})")
    elif st == 'waf':
        print(f" WAF")
    elif st == 'unreachable':
        print(f" {result['error'][:20]}")
    else:
        print(f" {st}")
    time.sleep(0.5)

print(f"\n{'='*60}")
print(f"  NEW WORKING SITES: {len(new_ok)}")
for c, r in new_ok:
    print(f"    + {c['name']} ({r['magnets']} magnets, pattern={r['pattern']})")

if new_ok:
    ruleset = data['rulesets'][0]
    for cand, result in new_ok:
        rule = {
            'id': hashlib.md5(cand['origin'].encode()).hexdigest()[:12],
            'site': {'name': cand['name'], 'origin': cand['origin']},
            'capabilities': {'supports_search': True, 'supports_detail': False},
            'search': {
                'request_template': result['pattern'],
                'timeout_ms': 12000,
                'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                'requires_waf_bypass': False,
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
            'quality': {'score': 70, 'tags': ['追新极客']},
            'health': {
                'status': 'green',
                'status_detail': 'ok',
                'last_checked_at': datetime.now(timezone.utc).isoformat(),
                'magnets_found': result['magnets'],
            },
        }
        ruleset['rules'].append(rule)

    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n  Updated sources.json: {data['meta']['total_rules']} total rules")

print("=" * 60)
