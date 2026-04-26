#!/usr/bin/env python3
"""
Extract real domain URLs from btmayi.top internal redirect pages.
Each btmayi.top/cilisousuo/xxx.html page contains a link/redirect to the actual magnet site.
"""
import json
import re
import sys
import os
import time
import base64
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import cloudscraper
    USE_CLOUDSCRAPER = True
except ImportError:
    import requests
    USE_CLOUDSCRAPER = False

from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

BTMAYI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'btmayi_sites.json')
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'btmayi_real_domains.json')

# Known domain hints from descriptions
HINT_DOMAINS = {
    '磁力天堂': 'cltt.me',
    '电影天堂': 'dytt8.net',
    'BT天堂': 'bttiantang',
    'BT之家': 'bthome',
    '迅雷电影天堂': 'ttdytt.cc',
}

# Non-magnet sites to skip
SKIP_NAMES = {'360搜索', '搜狗搜索', 'Bing搜索', '搜狗微信搜索', '简单搜索', 'Yandex',
              '一个开始', '秘迹搜索', '机器之心', '法信', '问答库', 'Lookao', '百度',
              '多吉搜索', '中国科技馆', '百度百科', 'wikiHow', '简书', '知乎',
              '十万个为什么', '豆瓣', '悟空问答', '科普中国网', '中国科普博览'}


def get_session():
    if USE_CLOUDSCRAPER:
        return cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    import requests
    return requests.Session()


def decode_go_url(href):
    """Decode a btmayi.top/go/?url=BASE64 redirect link."""
    if '/go/' not in href:
        return None
    m = re.search(r'[?&]url=([^&]+)', href)
    if not m:
        return None
    b64 = urllib.parse.unquote(m.group(1))
    # Add padding if needed
    b64 += '=' * (4 - len(b64) % 4) if len(b64) % 4 else ''
    try:
        return base64.b64decode(b64).decode('utf-8')
    except Exception:
        return None


def extract_external_url(html, page_url):
    """Extract the real external URL from a btmayi.top site detail page.

    The webstackpro theme structure:
    - <span class="site-go-url"> contains the "链接直达" <a> link
    - The link href is like https://btmayi.top/go/?url=BASE64_ENCODED_URL
    - Other data-url attrs in sidebar "相关导航" are NOT the current site
    """
    soup = BeautifulSoup(html, 'lxml')

    # Method 1 (PRIMARY): Find the "链接直达" button in site-go-url span
    go_span = soup.find('span', class_='site-go-url')
    if go_span:
        for a in go_span.find_all('a', href=True):
            real_url = decode_go_url(a['href'])
            if real_url:
                return [('链接直达', real_url, a.get_text(strip=True))]

    # Method 2: Any <a> with btn-arrow class and /go/ href (another variant)
    for a in soup.find_all('a', class_=re.compile(r'btn-arrow|btn-go', re.I), href=True):
        real_url = decode_go_url(a['href'])
        if real_url:
            return [('btn_link', real_url, a.get_text(strip=True))]

    # Method 3: Fallback — find first /go/ link that's in the main content area
    main = soup.find('div', class_=re.compile(r'site-detail|site-card|single-content', re.I))
    if main:
        for a in main.find_all('a', href=True):
            real_url = decode_go_url(a['href'])
            if real_url:
                return [('main_go', real_url, a.get_text(strip=True))]

    # Method 4: Look in page text for explicit URL mentions like "nyaa.net"
    text = soup.get_text()
    for m in re.finditer(r'(?:官网|地址|网址)[：:]\s*(https?://[^\s<>"\']+)', text):
        url = m.group(1)
        if 'btmayi.top' not in url:
            return [('text_url', url, '')]

    return []


def normalize_domain(url):
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        p = urllib.parse.urlparse(url)
        d = p.netloc.lower()
        if d.startswith('www.'):
            d = d[4:]
        return d
    except:
        return ''


def main():
    with open(BTMAYI_FILE, 'r', encoding='utf-8') as f:
        sites = json.load(f)

    # Filter to only magnet-related sites (first 59)
    magnet_sites = [s for s in sites if s['name'] not in SKIP_NAMES and
                    '/cilisousuo/' in s['url'] or '/bt-search/' in s['url']]

    print(f"Magnet sites to process: {len(magnet_sites)}")

    session = get_session()
    results = []

    for i, site in enumerate(magnet_sites):
        name = site['name']
        url = site['url']
        print(f"\n[{i+1}/{len(magnet_sites)}] {name}: {url}")

        try:
            resp = session.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                print(f"  HTTP {resp.status_code}")
                results.append({'name': name, 'url': url, 'status': f'http_{resp.status_code}',
                               'real_url': None, 'domain': None, 'desc': site.get('desc', '')})
                continue

            html = resp.text
            external_urls = extract_external_url(html, url)

            if external_urls:
                st, real_url, text = external_urls[0]
                domain = normalize_domain(real_url)
                print(f"  -> {domain} ({real_url})")
                results.append({
                    'name': name,
                    'url': url,
                    'status': 'found',
                    'real_url': real_url,
                    'domain': domain,
                    'source_type': st,
                    'desc': site.get('desc', ''),
                })
            else:
                print(f"  No external URL found")
                results.append({
                    'name': name, 'url': url, 'status': 'no_external_url',
                    'real_url': None, 'domain': None, 'desc': site.get('desc', ''),
                })

        except Exception as e:
            print(f"  Error: {str(e)[:80]}")
            results.append({'name': name, 'url': url, 'status': f'error',
                           'real_url': None, 'domain': None, 'error': str(e)[:100],
                           'desc': site.get('desc', '')})

        time.sleep(0.3)

    # Summary
    print(f"\n{'='*60}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*60}")

    found = [r for r in results if r.get('domain')]
    not_found = [r for r in results if not r.get('domain')]

    print(f"\n  Found domains: {len(found)}")
    for r in found:
        print(f"    {r['name']:20s} -> {r['domain']:30s} ({r.get('source_type', '')})")

    print(f"\n  Not found: {len(not_found)}")
    for r in not_found:
        print(f"    {r['name']:20s} ({r.get('status', '')})")

    # Save results
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'total': len(results),
            'found': len(found),
            'not_found': len(not_found),
            'results': results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Saved to: {OUTPUT_FILE}")

    # Also cross-reference with sources.json
    sources_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')
    try:
        with open(sources_file, 'r', encoding='utf-8') as f:
            src_data = json.load(f)
        existing = set()
        for rs in src_data.get('rulesets', []):
            for r in rs.get('rules', []):
                existing.add(normalize_domain(r['site']['origin']))

        new_domains = []
        for r in found:
            d = r.get('domain', '')
            if d and d not in existing:
                new_domains.append(r)

        print(f"\n  New domains (not in sources.json): {len(new_domains)}")
        for r in new_domains:
            print(f"    + {r['name']:20s} -> {r['domain']:30s} {r.get('real_url', '')}")
    except Exception as e:
        print(f"  Could not cross-reference: {e}")


if __name__ == '__main__':
    main()
