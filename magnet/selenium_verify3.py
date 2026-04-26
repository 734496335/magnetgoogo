#!/usr/bin/env python3
"""
Selenium Verify v3 — 用系统Chrome + webdriver-manager 验证 yellow 磁力源
=========================================================================
"""
import sys, os, re, json, time, logging, urllib.parse, argparse
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
    handlers=[logging.FileHandler('run.log', encoding='utf-8', mode='a'),
              logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
SOURCES_FILE = os.path.join(ROOT_DIR, 'sources.json')

MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')
HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')

SEARCH_PATHS = [
    '/search?q={q}', '/search/{q}', '/?q={q}', '/?s={q}',
    '/search?keyword={q}', '/search?query={q}', '/s/{q}',
    '/search/{q}/1/', '/so/{q}.html', '/vodsearch/{q}/',
    '/s?wd={q}', '/search/{q}/1/0/0.html',
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
            if hh in seen: continue
            seen.add(hh)
        title = a.get_text(strip=True)[:80]
        magnets.append({'title': title, 'magnet': a['href'][:150]})
    if not magnets:
        for a in soup.find_all('a', href=True):
            m = HASH_RE.search(a['href'])
            if m:
                hh = m.group(0).upper()
                if hh in seen: continue
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()

    log.info('=' * 60)
    log.info('  Selenium Verify v3 — 系统Chrome浏览器验证')
    log.info('=' * 60)

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

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1366,900')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(20)
    driver.implicitly_wait(2)

    promoted = 0
    updated = 0

    try:
        for idx, rule in enumerate(yellow_rules):
            origin = rule['site']['origin']
            brand = rule.get('site', {}).get('brand', '') or rule.get('site', {}).get('name', '')
            log.info(f'[{idx+1}/{len(yellow_rules)}] {brand} ({origin})')

            found = False
            for bait in BAIT_WORDS:
                if found: break
                q = urllib.parse.quote(bait)
                for path_tpl in SEARCH_PATHS:
                    if found: break
                    url = origin.rstrip('/') + path_tpl.replace('{q}', q)
                    try:
                        driver.get(url)
                        time.sleep(3)
                        html = driver.page_source
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
                        estr = str(e)[:40]
                        if 'timeout' not in estr.lower() and 'ERR_CONNECTION' not in estr:
                            pass

            if not found:
                try:
                    driver.get(origin)
                    time.sleep(2)
                    html = driver.page_source
                    lower = html[:10000].lower()
                    has_kw = any(kw in lower for kw in ['magnet:', 'torrent', '种子', '磁力', 'btih'])
                    log.info(f'  No magnets. Homepage: {len(html):>7d}b kw={has_kw}')
                except Exception as e:
                    estr = str(e)[:50]
                    log.info(f'  Homepage err: {estr}')

            time.sleep(0.3)

    finally:
        driver.quit()

    if updated > 0:
        data['generated_at'] = datetime.now(timezone.utc).isoformat()
        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

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
    log.info(f'  Status: green={green} yellow={yellow} gray={gray} red={red}')
    log.info(f'{"=" * 60}')


if __name__ == '__main__':
    main()
