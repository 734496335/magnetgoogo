#!/usr/bin/env python3
"""
Batch Verify — 批量验证 yellow 源，每次 8 个
=============================================
对 yellow/parsing_failed 源做 HTTP + Selenium 搜索验证：
  1. 尝试 HTTP 搜索多个关键词
  2. 提取 magnet/hash
  3. 找到就升级为 green
  4. 找不到就记录原因

用法：
  python magnet/batch_verify.py              # 验证前 8 个 yellow
  python magnet/batch_verify.py --start 8    # 从第 9 个开始
  python magnet/batch_verify.py --all        # 验证全部
"""

import sys
import os
import re
import json
import time
import logging
import urllib.parse
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
SOURCES_FILE = os.path.join(ROOT_DIR, 'sources.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')

SEARCH_QUERIES = [
    ('Big Buck Bunny', '/search/{query}'),
    ('Big Buck Bunny', '/search?q={query}'),
    ('Big Buck Bunny', '/?q={query}'),
    ('Big Buck Bunny', '/?s={query}'),
    ('Big Buck Bunny', '/search?keyword={query}'),
    ('Inception', '/search/{query}'),
    ('Inception', '/search?q={query}'),
    ('Inception', '/?q={query}'),
    ('Inception', '/?s={query}'),
    ('One Piece', '/search?q={query}'),
    ('One Piece', '/?q={query}'),
    ('Avengers', '/search?q={query}'),
    ('Avengers', '/?q={query}'),
    ('mp4', '/search?q={query}'),
    ('mp4', '/?q={query}'),
]

import requests
from bs4 import BeautifulSoup


def extract_magnets(html):
    soup = BeautifulSoup(html, 'lxml')
    results = []
    seen = set()
    for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
        m = MAGNET_RE.match(a['href'])
        if m:
            info_h = re.search(r'btih:([0-9A-Fa-f]{32,40})', a['href'], re.I)
            if info_h:
                hh = info_h.group(1).upper()
                if hh in seen:
                    continue
                seen.add(hh)
        title = a.get_text(strip=True)[:80]
        results.append({'title': title, 'magnet': a['href'][:150]})
    if not results:
        for a in soup.find_all('a', href=True):
            m = HASH_RE.search(a['href'])
            if m:
                hh = m.group(0).upper()
                if hh in seen:
                    continue
                seen.add(hh)
                title = a.get_text(strip=True)[:80]
                results.append({'title': title, 'magnet': f'magnet:?xt=urn:btih:{hh}'})
    if not results:
        for m in HASH_RE.finditer(soup.get_text()):
            hh = m.group(0).upper()
            if hh not in seen:
                seen.add(hh)
                results.append({'title': f'Hash {hh[:8]}...', 'magnet': f'magnet:?xt=urn:btih:{hh}'})
    return results


def try_http_search(origin, max_seconds=30):
    base = origin.rstrip('/')
    t0 = time.time()
    for query, path_tpl in SEARCH_QUERIES:
        if time.time() - t0 > max_seconds:
            break
        q = urllib.parse.quote(query)
        url = base + path_tpl.replace('{query}', q)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=6, allow_redirects=True)
            if resp.status_code >= 400:
                continue
            if len(resp.text) < 300:
                continue
            magnets = extract_magnets(resp.text)
            if magnets:
                return {
                    'ok': True,
                    'magnets': len(magnets),
                    'samples': magnets[:3],
                    'path': path_tpl,
                    'query': query,
                    'requires_browser': False,
                }
        except requests.RequestException:
            continue
    return None


def try_selenium_search(origin):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException

    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1366,900')
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(20)
    driver.implicitly_wait(2)

    try:
        base = origin.rstrip('/')
        for query, path_tpl in SEARCH_QUERIES[:6]:
            q = urllib.parse.quote(query)
            url = base + path_tpl.replace('{query}', q)
            try:
                driver.get(url)
                time.sleep(4)
            except (TimeoutException, Exception):
                continue
            magnets = extract_magnets(driver.page_source)
            if magnets:
                return {
                    'ok': True,
                    'magnets': len(magnets),
                    'samples': magnets[:3],
                    'path': path_tpl,
                    'query': query,
                    'requires_browser': True,
                }
        return None
    finally:
        driver.quit()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, default=0, help='start index (0-based)')
    parser.add_argument('--all', action='store_true', help='verify all yellow sources')
    parser.add_argument('--selenium', action='store_true', help='also try selenium')
    parser.add_argument('--probe', action='store_true', help='only probe homepage, no search')
    args = parser.parse_args()

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    yellow_rules = []
    for rs in data.get('rulesets', []):
        for rule in rs.get('rules', []):
            h = rule.get('health', {})
            if h.get('status') in ('yellow',) and h.get('status_detail') == 'parsing_failed':
                yellow_rules.append(rule)

    log.info(f'Yellow/parsing_failed 源总数: {len(yellow_rules)}')

    if args.all:
        batch = yellow_rules
    else:
        start = args.start
        batch = yellow_rules[start:start + 8]

    log.info(f'本次验证: {len(batch)} 个 (start={args.start})')
    log.info('=' * 70)

    if args.probe:
        for idx, rule in enumerate(batch):
            origin = rule['site']['origin']
            domain = rule['site'].get('name', origin)
            brand = rule['site'].get('brand', '')
            global_idx = args.start + idx
            try:
                resp = requests.get(origin, headers=HEADERS, timeout=8, allow_redirects=True)
                status = resp.status_code
                length = len(resp.text)
                has_magnet_kw = any(kw in resp.text[:10000].lower() for kw in ['magnet:', 'btih', 'torrent', '磁力', '种子'])
                has_form = 'search' in resp.text[:10000].lower() or '<form' in resp.text[:10000].lower()
                marker = 'HAS_MAGNET' if has_magnet_kw else ('HAS_FORM' if has_form else 'BLANK')
                log.info(f'[{global_idx+1}] {brand or domain:20s} {origin:40s} {status} {length:>7d}b {marker}')
            except requests.RequestException as e:
                log.info(f'[{global_idx+1}] {brand or domain:20s} {origin:40s} ERR {str(e)[:40]}')
        return

    updated = 0
    promoted = 0

    for idx, rule in enumerate(batch):
        origin = rule['site']['origin']
        domain = rule['site'].get('name', origin)
        brand = rule['site'].get('brand', '')
        label = f'{brand or domain}'
        global_idx = args.start + idx
        log.info(f'[{global_idx + 1}/{len(yellow_rules)}] {label} ({origin})')

        t0 = time.time()
        result = try_http_search(origin)
        dt = time.time() - t0
        log.info(f'  HTTP耗时 {dt:.1f}s')

        if result and result['ok']:
            magnets = result['magnets']
            log.info(f'  HTTP OK: {magnets} magnets (path={result["path"]} q={result["query"]})')
            for s in result['samples'][:2]:
                log.info(f'    {s["magnet"][:80]}')
            rule['health']['status'] = 'green'
            rule['health']['status_detail'] = 'ok'
            rule['health']['magnets_found'] = magnets
            rule['health']['sample_title'] = result['samples'][0]['title'][:80] if result['samples'] else ''
            rule['search']['request_template'] = result['path']
            rule['search']['requires_browser'] = result.get('requires_browser', False)
            rule['quality']['score'] = 70
            promoted += 1
            updated += 1
        elif args.selenium:
            log.info('  HTTP 未命中，尝试 Selenium...')
            result = try_selenium_search(origin)
            if result and result['ok']:
                magnets = result['magnets']
                log.info(f'  Selenium OK: {magnets} magnets (path={result["path"]} q={result["query"]})')
                rule['health']['status'] = 'green'
                rule['health']['status_detail'] = 'ok'
                rule['health']['magnets_found'] = magnets
                rule['health']['sample_title'] = result['samples'][0]['title'][:80] if result['samples'] else ''
                rule['search']['request_template'] = result['path']
                rule['search']['requires_browser'] = True
                rule['quality']['score'] = 70
                promoted += 1
                updated += 1
            else:
                log.info('  Selenium 也未命中')
        else:
            log.info('  未命中')

        time.sleep(0.5)

    if updated > 0:
        now = datetime.now(timezone.utc).isoformat()
        data['generated_at'] = now
        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f'\n已更新 {updated} 个源，其中 {promoted} 个升级为 green')

    green_count = sum(
        1 for rs in data.get('rulesets', []) for r in rs.get('rules', [])
        if r.get('health', {}).get('status') == 'green'
    )
    yellow_count = sum(
        1 for rs in data.get('rulesets', []) for r in rs.get('rules', [])
        if r.get('health', {}).get('status') == 'yellow'
    )
    log.info(f'当前状态: green={green_count} yellow={yellow_count}')


if __name__ == '__main__':
    main()
