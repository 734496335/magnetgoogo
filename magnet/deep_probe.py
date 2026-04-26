#!/usr/bin/env python3
"""
Deep Probe v2 — 深度探测可达但无法提取磁力的源
===============================================
增强能力：
1. Selenium 渲染（处理 SPA/JS 站）
2. 从页面文本中提取 40位 hash 并构造 magnet 链接
3. 两步提取（搜索 → 详情页 → magnet）
4. 重试机制（针对不稳定站如 0magnet.co）
5. 智能选择器：在 JS 渲染后的 DOM 中深度搜索
"""

import sys, os, re, json, time, hashlib, logging
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
    handlers=[logging.FileHandler('run.log', encoding='utf-8', mode='w'), logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

HASH_RE = re.compile(r'\b[0-9A-Fa-f]{40}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')

SOURCES_TO_PROBE = [
    {'brand': 'btsow.pics', 'url': 'https://btsow.pics', 'search': '/search/{query}', 'type': 'spa'},
    {'brand': '0magnet.co', 'url': 'https://0magnet.co', 'search': '/search?q={query}', 'type': 'twostep', 'retry': True},
    {'brand': 'magnetsearch.org', 'url': 'https://magnetsearch.org', 'search': '/search?q={query}', 'type': 'spa'},
    {'brand': 'isohunt.to', 'url': 'https://isohunt.to', 'search': '/search.php?ihq={query}', 'type': 'standard'},
    {'brand': 'anilibria.tv', 'url': 'https://www.anilibria.tv', 'search': '/search?q={query}', 'type': 'spa'},
    {'brand': 'bitru.org', 'url': 'https://bitru.org', 'search': '/search?q={query}', 'type': 'standard'},
    {'brand': 'blueroms.com', 'url': 'https://blueroms.com', 'search': '/search?q={query}', 'type': 'spa'},
    {'brand': 'animetime.xyz', 'url': 'https://animetime.xyz', 'search': '/search?q={query}', 'type': 'spa'},
    {'brand': 'btdigg.org', 'url': 'https://btdigg.org', 'search': '/search?q={query}', 'type': 'standard'},
]

BAIT_WORDS = ['Big Buck Bunny', 'Inception', 'Avengers', 'One Piece', 'The Witcher 3', 'sdde']


def get_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    d = webdriver.Chrome(options=opts)
    d.set_page_load_timeout(20)
    return d


def extract_hashes_from_text(text):
    hashes = set()
    for m in HASH_RE.finditer(text):
        h = m.group(0).upper()
        if h != '0' * 40 and not all(c == h[0] for c in h):
            hashes.add(h)
    return hashes


def extract_magnets_from_html(html, url=''):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    magnets = []
    seen = set()

    for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
        href = a['href']
        m = MAGNET_RE.match(href)
        if m:
            info_h = re.search(r'btih:([0-9A-Fa-f]{32,40})', href, re.I)
            if info_h:
                hh = info_h.group(1).upper()
                if hh in seen:
                    continue
                seen.add(hh)
        title = ''
        p = a.parent
        for _ in range(4):
            if p:
                for ta in p.find_all('a', href=True):
                    txt = ta.get_text(strip=True)
                    if txt and len(txt) > 3 and 'magnet:' not in ta['href']:
                        title = txt[:120]
                        break
                if title:
                    break
                p = p.parent
        if not title:
            title = a.get_text(strip=True)[:120]
        magnets.append({'title': title, 'magnet': href[:150], 'source': url})

    if not magnets:
        for a in soup.find_all('a', href=True):
            m = HASH_RE.search(a['href'])
            if m:
                hh = m.group(0).upper()
                if hh in seen:
                    continue
                seen.add(hh)
                title = a.get_text(strip=True)[:120]
                magnets.append({'title': title, 'magnet': f'magnet:?xt=urn:btih:{hh}', 'source': url})

    return magnets


def extract_hashes_from_links(html, base_url=''):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    results = []
    seen = set()

    for a in soup.find_all('a', href=True):
        href = a['href']
        m = HASH_RE.search(href)
        if m:
            hh = m.group(0).upper()
            if hh not in seen:
                seen.add(hh)
                title = a.get_text(strip=True)[:120]
                results.append({'hash': hh, 'title': title, 'href': href})

    for a in soup.find_all('a', href=True):
        href = a['href']
        txt = a.get_text(strip=True)
        size_match = re.search(r'[\d.]+\s*(?:MB|GB|TB)', txt)
        if size_match and href not in [r['href'] for r in results]:
            from urllib.parse import urljoin
            full = urljoin(base_url, href)
            if full not in [r['href'] for r in results]:
                results.append({'hash': None, 'title': txt[:120], 'href': full})

    return results


def probe_standard(src, driver):
    import requests
    url = src['url']
    search_tmpl = src.get('search', '/search?q={query}')

    for bait in BAIT_WORDS:
        search_url = url.rstrip('/') + '/' + search_tmpl.lstrip('/').replace('{query}', bait)
        if search_url.count('//') > 2:
            search_url = url.rstrip('/') + search_tmpl.replace('{query}', bait)

        for attempt in range(2):
            try:
                resp = requests.get(search_url, timeout=10, headers=HEADERS, allow_redirects=True)
                if resp.status_code != 200:
                    continue
                magnets = extract_magnets_from_html(resp.text, url)
                if magnets:
                    return {'ok': True, 'magnets': magnets, 'path': search_tmpl, 'bait': bait, 'method': 'http'}
            except Exception:
                pass
            time.sleep(1)
    return {'ok': False}


def probe_spa(src, driver):
    url = src['url']
    search_tmpl = src.get('search', '/search?q={query}')

    for bait in BAIT_WORDS[:3]:
        search_url = url.rstrip('/') + '/' + search_tmpl.lstrip('/').replace('{query}', bait)

        for attempt in range(2):
            try:
                log.info(f"    Selenium attempt {attempt+1}: {search_url}")
                driver.get(search_url)
                time.sleep(6)
                html = driver.page_source

                magnets = extract_magnets_from_html(html, url)
                if magnets:
                    return {'ok': True, 'magnets': magnets, 'path': search_tmpl, 'bait': bait, 'method': 'selenium'}

                links = extract_hashes_from_links(html, url)
                hash_results = [l for l in links if l.get('hash')]
                if hash_results:
                    constructed = []
                    for l in hash_results[:30]:
                        constructed.append({
                            'title': l['title'],
                            'magnet': f'magnet:?xt=urn:btih:{l["hash"]}',
                            'source': url,
                        })
                    return {'ok': True, 'magnets': constructed, 'path': search_tmpl, 'bait': bait, 'method': 'selenium-hash'}

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'lxml')
                body_text = soup.get_text()
                hashes = extract_hashes_from_text(body_text)
                if len(hashes) >= 2:
                    constructed = []
                    for h in list(hashes)[:30]:
                        constructed.append({
                            'title': f'Hash {h[:8]}...',
                            'magnet': f'magnet:?xt=urn:btih:{h}',
                            'source': url,
                        })
                    return {'ok': True, 'magnets': constructed, 'path': search_tmpl, 'bait': bait, 'method': 'selenium-texthash'}

            except Exception as e:
                log.info(f"    Selenium error: {e}")
            time.sleep(2)

    return {'ok': False}


def probe_twostep(src, driver):
    url = src['url']
    search_tmpl = src.get('search', '/search?q={query}')
    max_attempts = 3 if src.get('retry') else 1

    for bait in BAIT_WORDS[:3]:
        search_url = url.rstrip('/') + '/' + search_tmpl.lstrip('/').replace('{query}', bait)

        for attempt in range(max_attempts):
            try:
                log.info(f"    Two-step attempt {attempt+1}: {search_url}")
                driver.get(search_url)
                time.sleep(5)
                html = driver.page_source

                magnets = extract_magnets_from_html(html, url)
                if magnets:
                    return {'ok': True, 'magnets': magnets, 'path': search_tmpl, 'bait': bait, 'method': 'twostep-direct'}

                from bs4 import BeautifulSoup
                from urllib.parse import urljoin
                soup = BeautifulSoup(html, 'lxml')

                detail_links = []
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    txt = a.get_text(strip=True)
                    if href and len(href) > 3 and txt and len(txt) > 5:
                        if not any(skip in href for skip in ['#', 'javascript:', 'login', 'register', 'upload']):
                            full = urljoin(url, href)
                            if full.startswith('http') and full != url and url not in full + '/':
                                pass
                            detail_links.append((full, txt[:80]))

                seen_detail = set()
                for detail_url, detail_title in detail_links[:10]:
                    if detail_url in seen_detail:
                        continue
                    seen_detail.add(detail_url)
                    try:
                        driver.get(detail_url)
                        time.sleep(4)
                        detail_html = driver.page_source

                        magnets = extract_magnets_from_html(detail_html, url)
                        if magnets:
                            log.info(f"    Found {len(magnets)} magnets on detail page: {detail_url}")
                            return {'ok': True, 'magnets': magnets, 'path': search_tmpl, 'bait': bait, 'method': 'twostep-detail'}

                        hashes = extract_hashes_from_text(BeautifulSoup(detail_html, 'lxml').get_text())
                        if hashes:
                            constructed = []
                            for h in list(hashes)[:20]:
                                constructed.append({
                                    'title': detail_title,
                                    'magnet': f'magnet:?xt=urn:btih:{h}',
                                    'source': url,
                                })
                            log.info(f"    Found {len(constructed)} hashes on detail page: {detail_url}")
                            return {'ok': True, 'magnets': constructed, 'path': search_tmpl, 'bait': bait, 'method': 'twostep-detail-hash'}
                    except Exception:
                        pass

            except Exception as e:
                log.info(f"    Error: {e}")
            time.sleep(2)

    return {'ok': False}


def main():
    log.info("=" * 60)
    log.info("  DEEP PROBE v2")
    log.info("=" * 60)

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    existing = set()
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            from urllib.parse import urlparse
            d = urlparse(r['site']['origin']).netloc.lower()
            if d.startswith('www.'):
                d = d[4:]
            existing.add(d)

    log.info(f"Existing sources: {len(existing)}")

    driver = get_driver()
    results = []

    for i, src in enumerate(SOURCES_TO_PROBE):
        from urllib.parse import urlparse
        domain = urlparse(src['url']).netloc.lower().replace('www.', '')
        if domain in existing:
            log.info(f"\n[{i+1}/{len(SOURCES_TO_PROBE)}] {src['brand']}: ALREADY EXISTS")
            continue

        log.info(f"\n[{i+1}/{len(SOURCES_TO_PROBE)}] {src['brand']}: {src['url']} (type={src.get('type','standard')})")

        if src.get('type') == 'spa':
            r = probe_spa(src, driver)
        elif src.get('type') == 'twostep':
            r = probe_twostep(src, driver)
        else:
            r = probe_standard(src, driver)

        r['brand'] = src['brand']
        r['url'] = src['url']
        results.append(r)

        if r['ok']:
            log.info(f"  OK: {len(r['magnets'])} magnets (method={r.get('method')}, path={r.get('path')}, bait={r.get('bait')})")
            for m in r['magnets'][:3]:
                log.info(f"    {m.get('title','')[:60]} | {m.get('magnet','')[:60]}")
        else:
            log.info(f"  FAIL")

    driver.quit()

    ok = [r for r in results if r.get('ok')]
    fail = [r for r in results if not r.get('ok')]

    log.info("\n" + "=" * 60)
    log.info("  RESULTS")
    log.info("=" * 60)
    log.info(f"  WORKING: {len(ok)}")
    for r in ok:
        log.info(f"    + {r['brand']:20s} {r['url']:40s} {len(r['magnets']):3d} magnets")
        log.info(f"      method={r.get('method','')} path={r.get('path','')} bait={r.get('bait','')}")
    log.info(f"  FAILED: {len(fail)}")
    for r in fail:
        log.info(f"    - {r['brand']:20s} {r['url']:40s}")

    if ok:
        ruleset = data['rulesets'][0] if data.get('rulesets') else {
            'ruleset_id': 'base', 'priority': 1, 'max_sources_per_search': 10, 'rules': []
        }
        added = 0
        for r in ok:
            d = urlparse(r['url']).netloc.lower().replace('www.', '')
            if d in existing:
                continue
            existing.add(d)
            rule_id = hashlib.md5(r['url'].encode()).hexdigest()[:12]
            method = r.get('method', 'http')
            requires_browser = 'selenium' in method or 'twostep' in method
            rule = {
                'id': rule_id,
                'site': {'name': d, 'origin': r['url'].rstrip('/')},
                'capabilities': {'supports_search': True, 'supports_detail': 'twostep' in method},
                'search': {
                    'request_template': r.get('path', '/search?q={query}'),
                    'timeout_ms': 15000,
                    'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                    'requires_waf_bypass': False,
                    'requires_browser': requires_browser,
                    'extraction_method': method,
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
                    'magnets_found': len(r['magnets']),
                    'sample_title': r['magnets'][0].get('title', '')[:80] if r['magnets'] else '',
                },
            }
            ruleset['rules'].append(rule)
            added += 1
            log.info(f"  Added: {d}")

        data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
        data['generated_at'] = datetime.now(timezone.utc).isoformat()
        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"\n  {added} new sources. Total: {data['meta']['total_rules']}")

    log.info("=" * 60)


if __name__ == '__main__':
    from urllib.parse import urlparse
    main()
