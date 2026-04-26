#!/usr/bin/env python3
"""
Nuclear option: discover magnet sources by every means available.
1. Parse cilihezi.com 711KB page for ALL embedded links
2. GitHub open-source projects (magnetW etc.)
3. Baidu multi-keyword search
4. Brute-force domain variants of known brands
5. Batch test everything
"""
import sys, os, time, json, re, hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}
hash_re = re.compile(r'[0-9A-Fa-f]{40}')

ALL_CANDIDATES = {}

def add_candidate(url, source, label=''):
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if not domain or '.' not in domain:
        return
    if domain.startswith('www.'):
        domain = domain[4:]
    if domain not in ALL_CANDIDATES:
        ALL_CANDIDATES[domain] = {
            'url': f'{parsed.scheme}://{parsed.netloc}',
            'domain': domain,
            'sources': [f'{source}:{label}'],
        }
    else:
        ALL_CANDIDATES[domain]['sources'].append(f'{source}:{label}')

# ============================================================
# STRATEGY 1: Deep-parse cilihezi.com (711KB page)
# ============================================================
print("=" * 60)
print("STRATEGY 1: Deep parse cilihezi.com 711KB page")
print("=" * 60)

try:
    resp = requests.get('https://cilihezi.com/', timeout=20, headers=HEADERS)
    soup = BeautifulSoup(resp.text, 'lxml')
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue
        text = a.get_text(strip=True)
        if href.startswith('/'):
            continue
        parsed = urlparse(href)
        domain = parsed.netloc.lower()
        if domain and '.' in domain and domain != 'cilihezi.com' and domain != 'www.cilihezi.com':
            add_candidate(href, 'cilihezi', text[:30])

    for link in soup.find_all(['a', 'area'], href=True):
        href = link['href'].strip()
        if href.startswith('http'):
            add_candidate(href, 'cilihezi-full', '')

    print(f"  cilihezi.com yielded {len([d for d in ALL_CANDIDATES if 'cilihezi' in str(ALL_CANDIDATES[d]['sources'])])} domains")
except Exception as e:
    print(f"  ERROR: {e}")

# ============================================================
# STRATEGY 2: Parse other nav hubs
# ============================================================
print("\nSTRATEGY 2: Parse navigation hub sites")
nav_sites = [
    'https://www.cilihezi.top',
    'https://cilimao.biz',
    'https://cilitiantang.vip',
    'https://ezhentang.com',
    'https://cilsousuoyinqng.com.cn',
    'https://cilihezi.com/link.html',
]
for url in nav_sites:
    try:
        resp = requests.get(url, timeout=12, headers=HEADERS, allow_redirects=True)
        soup = BeautifulSoup(resp.text, 'lxml')
        domain_count = 0
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if href.startswith('http') and not href.startswith('javascript'):
                text = a.get_text(strip=True)[:30]
                add_candidate(href, f'nav-{urlparse(url).netloc}', text)
                domain_count += 1
        print(f"  {url}: {domain_count} links")
    except Exception as e:
        print(f"  {url}: {e}")

# ============================================================
# STRATEGY 3: Known brand domain brute-force
# ============================================================
print("\nSTRATEGY 3: Brute-force domain variants")
brands = ['cilimao', 'cili', 'btsow', 'btdb', 'btso', 'cilijun', 'ciliss',
          'zhongzi', 'sousuo', 'btdigg', 'torrentkitty', 'mag', 'cilibili',
          'btfans', 'btcake', 'btbtt', 'limetorrent', 'kickass', 'nyaa',
          'dmhy', 'acg', 'mikan', 'torrent', 'bitsearch', 'magnet']
tlds = ['.com', '.cc', '.top', '.fun', '.one', '.vip', '.xyz', '.me', '.net',
        '.org', '.info', '.io', '.app', '.pro', '.work', '.site', '.online',
        '.club', '.live', '.pw', '.la', '.tv', '.moe']
prefixes = ['', 'www.']

for brand in brands:
    for tld in tlds:
        for prefix in prefixes:
            domain = f'{prefix}{brand}{tld}'
            url = f'https://{domain}'
            add_candidate(url, 'brute', brand)

print(f"  Brute-force added {len([d for d in ALL_CANDIDATES if 'brute' in str(ALL_CANDIDATES[d]['sources'])])} domain variants")

# ============================================================
# STRATEGY 4: Known magnet search site list (curated)
# ============================================================
print("\nSTRATEGY 4: Curated list from industry knowledge")
curated = [
    'https://bitsearch.to', 'https://solidtorrents.to', 'https://aiosearch.com',
    'https://snowfl.com', 'https://idope.se', 'https://zooqle.com',
    'https://yourbittorrent.com', 'https://btscene.org', 'https://demonoid.is',
    'https://rutor.info', 'https://tokyotosho.info', 'https://anidex.info',
    'https://acg.rip', 'https://share.dmhy.org', 'https://nyaa.si',
    'https://animetosho.org', 'https://mikanani.me', 'https://nyafun.com',
    'https://bitcq.com', 'https://u3c3.org',
    'https://clmaoc.top', 'https://cilibra.org', 'https://magbot.xyz',
    'https://cili.one', 'https://cili123.com', 'https://cili.date',
    'https://xiguasousou.com', 'https://souxung.com',
    'https://cili8.biz', 'https://ciliss.cc', 'https://cilimaocili.com',
    'https://cilihezi.com', 'https://cilihezi.top', 'https://cilihezi.com',
    'https://www.btcat.bid', 'https://souzhongzi.com', 'https://www.zhongziso.in',
    'https://www.cili5.net', 'https://cilishenqi.me', 'https://wuqianaa.xyz',
    'https://bashi5.com', 'https://12580.org', 'https://cldq.cc',
    'https://www.ezhentang.com', 'https://www.cilitiantang.vip',
    'https://mag.net', 'https://www.6v520.com', 'https://www.seedhub.cc',
    'https://www.torrentdownload.info',
    'https://btfox.xyz', 'https://btfox12.top',
    'https://cilimao.biz', 'https://cilimao.im', 'https://clm8.top',
    'https://www.cilimaocili.com', 'https://clmaoc.top',
    'https://cilibili.fun', 'https://cilibili.net',
    'https://btbus.app', 'https://btav.xyz',
    'https://www.btdig.com', 'https://btdigg.org',
    'https://torrentkitty.tv', 'https://torrentkitty.net',
    'https://www.btsow.com', 'https://www.btsow.vip',
    'https://1337x.to', 'https://1337x.gd',
    'https://thepiratebay.org', 'https://thepiratebay.se.net',
    'https://rarbg.to', 'https://torrentgalaxy.to',
    'https://magnetdl.com', 'https://yts.mx', 'https://eztv.re',
    'https://limetorrents.lol', 'https://limetorrents.info',
    'https://extratorrent.ag', 'https://extratorrent.st',
    'https://kickasstorrents.to', 'https://katcr.co',
    'https://glodls.to', 'https://bitport.io',
    'https://www.moerats.com', 'https://tool.liumingye.cn',
    'https://www.cdbao.net', 'https://www.yinfans.me',
    'https://www.icezmz.com', 'https://www.lsjlp8.com',
]
for url in curated:
    add_candidate(url, 'curated', '')

print(f"  Curated list added")

# ============================================================
# Print summary
# ============================================================
print(f"\n{'='*60}")
print(f"TOTAL UNIQUE CANDIDATES: {len(ALL_CANDIDATES)}")

# Save candidates
with open('all_candidates.json', 'w', encoding='utf-8') as f:
    json.dump(ALL_CANDIDATES, f, indent=2, ensure_ascii=False)
print(f"Saved to all_candidates.json")

# ============================================================
# BATCH TEST ALL CANDIDATES
# ============================================================
print(f"\n{'='*60}")
print(f"BATCH TESTING {len(ALL_CANDIDATES)} CANDIDATES")
print(f"{'='*60}")

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')
with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

existing = set()
for rs in data.get('rulesets', []):
    for r in rs.get('rules', []):
        existing.add(r['site']['origin'].lower().rstrip('/'))
        existing.add(r['site']['name'].lower())

SEARCH_PATTERNS = [
    '/search?q={query}', '/search/{query}/', '/?q={query}', '/?wd={query}',
    '/s/{query}', '/search.php?q={query}', '/search.php?keywords={query}',
    '/search.php?wd={query}', '/?s={query}', '/search?wd={query}',
    '/search.html?q={query}', '/so/{query}.html',
]
TEST_QUERIES = ['Inception', 'Big Buck Bunny', 'test']
working = []
tested = 0
skipped = 0

for domain, info in sorted(ALL_CANDIDATES.items()):
    url = info['url'].rstrip('/')
    name = domain.replace('www.', '').split('.')[0]

    if url.lower() in existing or name.lower() in existing:
        skipped += 1
        continue

    tested += 1
    if tested % 50 == 0:
        print(f"\n  Progress: {tested}/{len(ALL_CANDIDATES)-skipped} tested, {len(working)} working so far")

    found = False
    for pattern in SEARCH_PATTERNS:
        if found:
            break
        for query in TEST_QUERIES:
            if found:
                break
            test_url = url + pattern.replace('{query}', query)
            try:
                resp = requests.get(test_url, timeout=8, headers=HEADERS, allow_redirects=True)
                if resp.status_code != 200:
                    continue
                if len(resp.text) < 300:
                    continue

                soup = BeautifulSoup(resp.text, 'lxml')
                title = soup.title.string[:30] if soup.title and soup.title.string else ''
                if 'just a moment' in title.lower():
                    break

                magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
                hashes = set()
                for a in soup.find_all('a', href=True):
                    m = hash_re.search(a['href'])
                    if m:
                        hashes.add(m.group(1))

                if magnets or len(hashes) >= 2:
                    count = max(len(magnets), len(hashes))
                    sample = magnets[0].get('href', '')[:60] if magnets else ''
                    working.append({
                        'domain': domain,
                        'url': url,
                        'pattern': pattern,
                        'query': query,
                        'count': count,
                        'sample': sample,
                        'title': title,
                    })
                    print(f"  FOUND: {domain:30s} | {count} magnets | {pattern}")
                    found = True

            except:
                pass

    if not found and tested <= 20:
        pass  # only print first 20

print(f"\n{'='*60}")
print(f"RESULTS")
print(f"{'='*60}")
print(f"  Total candidates: {len(ALL_CANDIDATES)}")
print(f"  Skipped (existing): {skipped}")
print(f"  Tested: {tested}")
print(f"  WORKING: {len(working)}")
print()

for w in working:
    print(f"  + {w['domain']:30s} | {w['count']} magnets | {w['pattern']} | {w['title']}")

# Add working sites to sources.json
if working:
    ruleset = data['rulesets'][0]
    for w in working:
        rule = {
            'id': hashlib.md5(w['url'].encode()).hexdigest()[:12],
            'site': {'name': w['domain'], 'origin': w['url']},
            'capabilities': {'supports_search': True, 'supports_detail': False},
            'search': {
                'request_template': w['pattern'],
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
    print(f"\n  Updated sources.json: {data['meta']['total_rules']} total rules")

# Save working results
with open('discovery_results.json', 'w', encoding='utf-8') as f:
    json.dump({'working': working, 'total_tested': tested, 'total_candidates': len(ALL_CANDIDATES)}, f, indent=2, ensure_ascii=False)

print("=" * 60)
