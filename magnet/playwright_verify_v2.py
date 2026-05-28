#!/usr/bin/env python3
"""
playwright_verify_v2.py — Scrapling StealthyFetcher 版本的 yellow→green 验证。

v2 vs v1 (playwright_verify.py):
  - 用 StealthyFetcher 替代裸 Playwright，自动应对 Cloudflare Turnstile/Interstitial
  - 反指纹 patches: navigator.webdriver=undefined, fake Chrome API, canvas noise...
  - 内置广告屏蔽，加速加载
  - 单页面会话改成短期独立会话（StealthyFetcher 内部维护）

接口与 v1 完全一致：
  python magnet/playwright_verify_v2.py
  python magnet/playwright_verify_v2.py --start 5 --limit 10
  python magnet/playwright_verify_v2.py --dry-run   # 不写回 sources.json
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

MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')
HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')

SEARCH_PATHS = [
    '/search?q={q}', '/search/{q}', '/?q={q}', '/?s={q}',
    '/search?keyword={q}', '/search?query={q}', '/s/{q}',
    '/search/{q}/1/', '/so/{q}.html', '/index.php?q={q}',
    '/vodsearch/{q}/', '/s?wd={q}', '/search/{q}/1/0/0.html',
    '/list.html?key={q}', '/search?q={q}&page=1',
]

BAIT_WORDS = ['Inception', 'Big Buck Bunny', 'mp4']


def extract_magnets(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    magnets, seen = [], set()
    for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
        ih = re.search(r'btih:([0-9A-Fa-f]{32,40})', a['href'], re.I)
        if ih:
            hh = ih.group(1).upper()
            if hh in seen:
                continue
            seen.add(hh)
        title = a.get_text(strip=True)[:80]
        magnets.append({'title': title, 'magnet': a['href'][:150]})
    if not magnets:
        for a in soup.find_all('a', href=True):
            m = HASH_RE.search(a['href'])
            if m:
                hh = m.group(0).upper()
                if hh in seen:
                    continue
                seen.add(hh)
                title = a.get_text(strip=True)[:80]
                magnets.append({'title': title, 'magnet': f'magnet:?xt=urn:btih:{hh}'})
    if not magnets:
        for m in HASH_RE.finditer(soup.get_text()):
            hh = m.group(0).upper()
            if hh not in seen:
                seen.add(hh)
                magnets.append({'title': f'Hash {hh[:8]}...', 'magnet': f'magnet:?xt=urn:btih:{hh}'})
    return magnets


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--dry-run', action='store_true', help='Do not write sources.json')
    args = parser.parse_args()

    log.info('=' * 60)
    log.info('  Playwright Verify V2 — Scrapling StealthyFetcher')
    log.info('=' * 60)

    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        log.error("scrapling not installed. Run: pip install 'scrapling[fetchers]'")
        sys.exit(1)

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    yellow_rules = []
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            if r.get('health', {}).get('status') == 'yellow':
                yellow_rules.append(r)

    log.info(f'Yellow sources: {len(yellow_rules)}')

    if args.limit > 0:
        yellow_rules = yellow_rules[args.start:args.start + args.limit]
    elif args.start > 0:
        yellow_rules = yellow_rules[args.start:]

    log.info(f'Will verify: {len(yellow_rules)}')

    promoted = 0
    updated = 0
    timeout_ms = args.timeout * 1000

    for idx, rule in enumerate(yellow_rules):
        origin = rule['site']['origin']
        brand = rule.get('site', {}).get('brand', '') or rule.get('site', {}).get('name', '')
        log.info(f'[{idx + 1}/{len(yellow_rules)}] {brand} ({origin})')

        found = False
        for bait in BAIT_WORDS:
            if found:
                break
            q = urllib.parse.quote(bait)
            for path_tpl in SEARCH_PATHS:
                if found:
                    break
                url = origin.rstrip('/') + path_tpl.replace('{q}', q)
                try:
                    resp = StealthyFetcher.fetch(
                        url,
                        headless=True,
                        network_idle=True,
                        timeout=timeout_ms,
                        block_images=True,
                    )
                    if resp.status not in (200, 304):
                        continue
                    html = str(resp.html_content) if resp.html_content else resp.body.decode('utf-8', errors='replace')
                    magnets = extract_magnets(html)
                    if magnets:
                        log.info(f'  OK: {len(magnets)} magnets (path={path_tpl} q={bait})')
                        for m in magnets[:2]:
                            log.info(f'    {m["title"][:60]}')
                        rule['health']['status'] = 'green'
                        rule['health']['status_detail'] = 'ok'
                        rule['health']['magnets_found'] = len(magnets)
                        rule['health']['sample_title'] = magnets[0].get('title', '')[:80]
                        rule['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()
                        rule['search']['request_template'] = path_tpl
                        rule['search']['requires_browser'] = True
                        rule['quality']['score'] = 70
                        promoted += 1
                        updated += 1
                        found = True
                except Exception as e:
                    estr = str(e)[:80]
                    if 'Timeout' not in estr and 'net::ERR' not in estr:
                        log.info(f'  err: {estr}')

        if not found:
            try:
                resp = StealthyFetcher.fetch(origin, headless=True, network_idle=False, timeout=15000)
                if resp.status in (200, 304):
                    html = str(resp.html_content) if resp.html_content else resp.body.decode('utf-8', errors='replace')
                    lower = html[:10000].lower()
                    has_kw = any(kw in lower for kw in ['magnet:', 'torrent', '种子', '磁力', 'btih'])
                    log.info(f'  No magnets found. Homepage: {len(html):>7d}b kw={has_kw}')
                    rule['health']['status_detail'] = 'parsing_failed'
                    note = 'homepage_has_keywords_needs_manual_or_site_adapter' if has_kw else 'homepage_no_keywords_likely_not_search_engine'
                    rule['health']['note'] = note
                    rule['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()
                    updated += 1
                else:
                    log.info(f'  homepage HTTP {resp.status}')
            except Exception as e:
                estr = str(e)[:80]
                if 'net::ERR_CONNECTION' in estr or 'net::ERR_NAME' in estr or 'Timeout' in estr:
                    log.info(f'  UNREACHABLE: {estr}')
                    rule['health']['status'] = 'gray'
                    rule['health']['status_detail'] = 'unreachable'
                    rule['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()
                    updated += 1
                else:
                    log.info(f'  homepage err: {estr}')

        time.sleep(0.3)

    if updated > 0 and not args.dry_run:
        data['generated_at'] = datetime.now(timezone.utc).isoformat()
        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    elif args.dry_run:
        log.info('[dry-run] sources.json NOT written')

    green = sum(1 for rs in data.get('rulesets', []) for r in rs.get('rules', [])
                if r.get('health', {}).get('status') == 'green')
    yellow = sum(1 for rs in data.get('rulesets', []) for r in rs.get('rules', [])
                 if r.get('health', {}).get('status') == 'yellow')
    red = sum(1 for rs in data.get('rulesets', []) for r in rs.get('rules', [])
              if r.get('health', {}).get('status') == 'red')
    gray = sum(1 for rs in data.get('rulesets', []) for r in rs.get('rules', [])
               if r.get('health', {}).get('status') == 'gray')

    log.info(f'\n{"=" * 60}')
    log.info(f'  Promoted to green: {promoted}')
    log.info(f'  Status: green={green} yellow={yellow} gray={gray} red={red} total={green + yellow + gray + red}')
    log.info(f'{"=" * 60}')


if __name__ == '__main__':
    main()
