#!/usr/bin/env python3
"""
Resume batch test from where we left off. Skips already-tested domains.
"""
import sys, os, time, json, re, hashlib, logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding='utf-8', mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}
hash_re = re.compile(r'[0-9A-Fa-f]{40}')

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')
with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

existing = set()
for rs in data.get('rulesets', []):
    for r in rs.get('rules', []):
        existing.add(r['site']['origin'].lower().rstrip('/'))

with open('all_candidates.json', 'r', encoding='utf-8') as f:
    ALL = json.load(f)

tested_domains = set()
START_INDEX = 548  # skip first 548 domains (already tested in previous run)
sorted_domains = sorted(ALL.keys())[START_INDEX:]

log.info(f"=== RESUME from index {START_INDEX}: {len(sorted_domains)} remaining ===")

SEARCH_PATTERNS = [
    '/search?q=Inception', '/search?q=test', '/?q=Inception', '/?wd=Inception',
    '/search/Inception/', '/s/Inception', '/search.php?q=Inception',
    '/search.php?keywords=Inception', '/?s=Inception', '/so/Inception.html',
]

working = []
tested = 0
reachable = 0
skipped = 0
total = len(ALL)
start_time = time.time()

sorted_domains = sorted(ALL.keys())

for domain in sorted_domains:
    info = ALL[domain]
    url = info['url'].rstrip('/')

    if url.lower() in existing:
        skipped += 1
        continue

    tested += 1

    site_ok = False
    ok_html = None
    ok_pattern = ''

    for pattern in SEARCH_PATTERNS[:4]:
        test_url = url + pattern
        try:
            resp = requests.get(test_url, timeout=6, headers=HEADERS, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 300:
                title = ''
                try:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    t = soup.title
                    title = t.string[:40] if t and t.string else ''
                except Exception:
                    pass
                if 'just a moment' in title.lower():
                    continue
                site_ok = True
                ok_html = resp.text
                ok_pattern = pattern
                break
        except Exception:
            continue

    if not site_ok:
        log.info(f"[{tested}] {domain:35s} FAIL")
        continue

    reachable += 1
    soup = BeautifulSoup(ok_html, 'lxml')
    magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
    hashes = set()
    for a in soup.find_all('a', href=True):
        m = hash_re.search(a['href'])
        if m:
            hashes.add(m.group(0))

    if magnets or len(hashes) >= 2:
        count = max(len(magnets), len(hashes))
        sample = magnets[0].get('href', '')[:60] if magnets else ''
        title = soup.title.string[:40] if soup.title and soup.title.string else ''
        working.append({
            'domain': domain, 'url': url, 'pattern': ok_pattern,
            'count': count, 'sample': sample, 'title': title,
        })
        log.info(f"[{tested}] {domain:35s} FOUND #{len(working)}: {count} magnets | {title}")
    else:
        log.info(f"[{tested}] {domain:35s} REACHABLE but no magnets | {ok_pattern}")

elapsed = time.time() - start_time
log.info(f"")
log.info(f"{'='*60}")
log.info(f"RESUME RESULTS: tested={tested} skipped={skipped} reachable={reachable} WORKING={len(working)} time={elapsed:.0f}s")

for w in working:
    log.info(f"  + {w['domain']:30s} | {w['count']} magnets | {w['pattern']}")

if working:
    ruleset = data['rulesets'][0]
    for w in working:
        rule = {
            'id': hashlib.md5(w['url'].encode()).hexdigest()[:12],
            'site': {'name': w['domain'], 'origin': w['url']},
            'capabilities': {'supports_search': True, 'supports_detail': False},
            'search': {
                'request_template': w['pattern'].replace('Inception', '{query}').replace('test', '{query}'),
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
                'magnets_found': w['count'],
            },
        }
        ruleset['rules'].append(rule)
    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"  Updated sources.json: {data['meta']['total_rules']} total rules")

with open('nuclear_results.json', 'w', encoding='utf-8') as f:
    json.dump({'working': working, 'tested': tested, 'reachable': reachable, 'total_candidates': total}, f, indent=2, ensure_ascii=False)

log.info("=" * 60)
