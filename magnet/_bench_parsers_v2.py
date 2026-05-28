"""
Bake-off v2 — 公平测试 AutoScraper 的泛化能力。

流程：
  1. 对一个有效的 green 源，用 query A 抓首页
  2. 用 BeautifulSoup 找到页面上真实存在的一个 magnet + title（这才是有效的种子）
  3. 用这对种子训练 AutoScraper
  4. 用 query B 抓另一页搜索结果
  5. 看 AutoScraper 学到的规则在 query B 页面上能否 generalize
  6. 同时对比 v1_heuristic / regex_only

成功标准：AutoScraper 在 page B 上提取出的 magnet 数 >= v1_heuristic
"""
import sys
import os
import re
import json
import time
import argparse
from urllib.parse import quote

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HASH_RE = re.compile(r'\b[0-9a-fA-F]{40}\b')


def fetch(url, timeout=15):
    from scrapling.fetchers import Fetcher
    try:
        r = Fetcher.get(url, impersonate='chrome', timeout=timeout, retries=1, retry_delay=1)
        if r.status == 200:
            return str(r.html_content) if r.html_content else r.body.decode('utf-8', errors='replace')
    except UnicodeDecodeError:
        try:
            return r.body.decode('gbk', errors='replace')
        except Exception:
            pass
    except Exception:
        pass
    return None


def find_seed_pair(html):
    """Find one real (title, magnet) pair from the page to use as AutoScraper training."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    # Look for any anchor that has magnet: in href
    for a in soup.find_all('a', href=True):
        h = a['href']
        if 'magnet:' in h:
            # Look around for a sibling title
            title = a.get_text(strip=True)
            if not title or len(title) < 4:
                # Try parent's other anchors
                parent = a.find_parent(['tr', 'div', 'li'])
                if parent:
                    for sibling in parent.find_all('a'):
                        st = sibling.get_text(strip=True)
                        if st and len(st) > 4 and 'magnet' not in st.lower():
                            title = st
                            break
            if title:
                # Return short magnet (just btih part) so AutoScraper can match
                m = re.search(r'magnet:\?xt=urn:btih:[0-9a-fA-F]{32,40}', h, re.I)
                if m:
                    return (title, m.group(0))
    # No magnet anchors — try hash-bearing URLs
    for a in soup.find_all('a', href=True):
        m = HASH_RE.search(a['href'])
        if m:
            title = a.get_text(strip=True)
            if title and len(title) > 4:
                return (title, m.group(0).upper())
    return (None, None)


def count_hashes(items):
    """From a list of strings, count unique 40-char hashes (case-insensitive)."""
    found = set()
    for s in items or []:
        if not isinstance(s, str):
            continue
        for m in HASH_RE.findall(s):
            found.add(m.upper())
    return len(found)


def parse_v1(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    found = set()
    for a in soup.find_all('a', href=True):
        h = a['href']
        if 'magnet:' in h:
            m = re.search(r'btih:([0-9a-fA-F]{32,40})', h, re.I)
            if m:
                found.add(m.group(1).upper())
        m = HASH_RE.search(h)
        if m:
            found.add(m.group(0).upper())
    return len(found)


def parse_regex(html):
    return len(set(h.upper() for h in HASH_RE.findall(html)))


def parse_autoscraper(html_a, seed_pair, html_b):
    """Train on (html_a, seed_pair) and apply to html_b."""
    from autoscraper import AutoScraper
    scraper = AutoScraper()
    seed_title, seed_magnet = seed_pair
    wanted = [x for x in (seed_title, seed_magnet) if x]
    try:
        result_a = scraper.build(html=html_a, wanted_list=wanted)
        # Now apply to page B
        result_b = scraper.get_result_similar(html=html_b)
        return {
            'train_count': count_hashes(result_a) + sum(1 for r in result_a or [] if isinstance(r, str) and len(r) > 4),
            'train_raw': len(result_a or []),
            'apply_hashes': count_hashes(result_b),
            'apply_raw': len(result_b or []),
            'apply_sample': (result_b or [])[:3],
        }
    except Exception as e:
        return {'error': str(e)[:120]}


# Hand-picked test cases: sites known to work
TEST_CASES = [
    # International — needs VPN
    {'origin': 'https://fitgirl-repacks.site', 'tpl': '/?s={q}', 'query_a': 'Witcher', 'query_b': 'Cyberpunk'},
    # CN-accessible
    {'origin': 'https://clb12.xyz', 'tpl': '/s/{q}', 'query_a': '盗梦空间', 'query_b': '阿凡达'},
    {'origin': 'https://0cili.nl', 'tpl': '/search?q={q}', 'query_a': 'Inception', 'query_b': 'Dune'},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--origin', default='')
    ap.add_argument('--tpl', default='/?s={q}')
    ap.add_argument('--qa', default='Witcher')
    ap.add_argument('--qb', default='Inception')
    ap.add_argument('--proxy', default='', help='HTTP proxy (e.g. http://127.0.0.1:33210) for VPN access')
    args = ap.parse_args()

    if args.proxy:
        os.environ['HTTPS_PROXY'] = args.proxy
        os.environ['HTTP_PROXY'] = args.proxy
        print(f'[proxy ON] {args.proxy}')

    cases = TEST_CASES
    if args.origin:
        cases = [{'origin': args.origin, 'tpl': args.tpl, 'query_a': args.qa, 'query_b': args.qb}]

    for c in cases:
        url_a = c['origin'].rstrip('/') + c['tpl'].replace('{q}', quote(c['query_a']))
        url_b = c['origin'].rstrip('/') + c['tpl'].replace('{q}', quote(c['query_b']))
        print(f'\n{"=" * 80}\n  {c["origin"]}\n{"=" * 80}')

        print(f'  Fetching page A: {url_a}')
        html_a = fetch(url_a)
        if not html_a:
            print('  SKIP: A fetch failed'); continue
        print(f'    A size: {len(html_a)} bytes')

        print(f'  Fetching page B: {url_b}')
        html_b = fetch(url_b)
        if not html_b:
            print('  SKIP: B fetch failed'); continue
        print(f'    B size: {len(html_b)} bytes')

        # Find a real seed pair from page A
        title, magnet = find_seed_pair(html_a)
        if not magnet:
            print('  SKIP: no seed pair found in page A')
            continue
        print(f'  Seed pair from A:')
        print(f'    title:  "{title[:80]}"')
        print(f'    magnet: {magnet[:80]}')

        # Now compare parsers on page B
        v1_b = parse_v1(html_b)
        regex_b = parse_regex(html_b)
        as_result = parse_autoscraper(html_a, (title, magnet), html_b)

        print(f'\n  Results on page B (query={c["query_b"]}):')
        print(f'    v1_heuristic:  {v1_b} hashes')
        print(f'    regex_only:    {regex_b} hashes')
        if 'error' in as_result:
            print(f'    autoscraper:   ERROR {as_result["error"]}')
        else:
            print(f'    autoscraper:   {as_result["apply_hashes"]} hashes  '
                  f'(raw_results={as_result["apply_raw"]}, sample={as_result["apply_sample"]})')


if __name__ == '__main__':
    main()
