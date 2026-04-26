#!/usr/bin/env python3
"""
Nav Site Human Crawler — 导航站人机协作爬虫
============================================
弹出浏览器，用户手动操作：
  1. 过验证码/Cloudflare
  2. 点击切换到磁力/BT/下载分类
  3. 按 Enter，脚本自动提取当前页所有链接
  4. 脚本自动验证每个链接是否是可用磁力源
  5. 通过的自动加入 sources.json

用法:
  python magnet/nav_human_crawler.py https://www.ymaoo.cn
  python magnet/nav_human_crawler.py https://www.4abyte.com
  python magnet/nav_human_crawler.py https://ciligou.art   # 发布页
"""

import sys, os, re, json, time, hashlib, logging, urllib.parse, argparse
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from collections import OrderedDict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
    handlers=[logging.FileHandler('run.log', encoding='utf-8', mode='a'), logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')

HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')
BAIT_WORDS = ['Big Buck Bunny', 'Inception', 'One Piece']
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
TORRENT_POSITIVE = ['magnet:', 'torrent', '种子', '磁力', 'btih', 'seeders', 'leechers',
                    'bt搜索', '种子搜索', '磁力搜索', '磁力下载', 'bt下载']


def normalize_domain(url):
    try:
        if not url.startswith(('http://', 'https://')): url = 'http://' + url
        p = urlparse(url)
        d = p.netloc.lower()
        if d.startswith('www.'): d = d[4:]
        return d
    except:
        return ''


def extract_from_html(html, url=''):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    magnets, seen = [], set()
    for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
        m = MAGNET_RE.match(a['href'])
        if m:
            info_h = re.search(r'btih:([0-9A-Fa-f]{32,40})', a['href'], re.I)
            if info_h:
                hh = info_h.group(1).upper()
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


def load_existing():
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    existing = set()
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            existing.add(normalize_domain(r['site']['origin']))
    return existing, data


def add_to_sources(verified):
    if not verified: return 0
    existing, data = load_existing()
    ruleset = data['rulesets'][0]
    added = 0
    for v in verified:
        d = v['domain']
        if d in existing: continue
        existing.add(d)
        rule_id = hashlib.md5(v['url'].encode()).hexdigest()[:12]
        rule = {
            'id': rule_id,
            'site': {'name': d, 'origin': v['url'].rstrip('/'), 'countries': ['china']},
            'capabilities': {'supports_search': True, 'supports_detail': False},
            'search': {
                'request_template': v.get('path', '/search?q={query}'),
                'timeout_ms': 15000,
                'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                'requires_waf_bypass': False,
                'requires_browser': v.get('requires_browser', False),
                'parse_metadata': {'selectors': {
                    'list_item': 'div.item', 'title': 'a[href^="magnet:"]',
                    'magnet': 'a[href^="magnet:"]', 'size': 'span.size', 'date': 'span.date',
                }}
            },
            'quality': {'score': 70, 'tags': ['追新极客']},
            'health': {
                'status': 'green', 'status_detail': 'ok',
                'last_checked_at': datetime.now(timezone.utc).isoformat(),
                'magnets_found': v.get('magnets', 0),
                'sample_title': v.get('samples', [{}])[0].get('title', '')[:80] if v.get('samples') else '',
            },
        }
        if v.get('brand'): rule['site']['brand'] = v.get('brand')
        ruleset['rules'].append(rule)
        added += 1
        log.info(f"  Added: {d} ({v.get('magnets', 0)} magnets)")
    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
    data['generated_at'] = datetime.now(timezone.utc).isoformat()
    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return added


def extract_links_from_page(driver, base_url):
    from bs4 import BeautifulSoup
    html = driver.page_source
    soup = BeautifulSoup(html, 'lxml')
    base_dom = normalize_domain(base_url)
    links = {}
    for a in soup.find_all('a', href=True):
        href = a['href']
        txt = a.get_text(strip=True)
        if not href or not txt: continue
        if href.startswith('//'): href = 'https:' + href
        elif href.startswith('/'): href = urljoin(base_url, href)
        if not href.startswith('http'): continue
        dom = normalize_domain(href)
        if dom and dom != base_dom and dom not in links:
            links[dom] = {'url': href, 'domain': dom, 'title': txt[:80]}
    return links


def verify_one(url, domain):
    import requests
    resp = None
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
    except Exception:
        return None

    if not resp or resp.status_code != 200:
        return None
    if len(resp.text) < 300:
        return None

    lower = resp.text[:15000].lower()
    if not any(kw in lower for kw in TORRENT_POSITIVE):
        return None

    for bait in BAIT_WORDS:
        for sp in [f'/search/{urllib.parse.quote(bait)}', f'/search?q={urllib.parse.quote(bait)}',
                    f'/?q={urllib.parse.quote(bait)}', f'/?s={urllib.parse.quote(bait)}',
                    f'/search?query={urllib.parse.quote(bait)}']:
            test_url = url.rstrip('/') + sp
            try:
                r2 = requests.get(test_url, timeout=8, headers=HEADERS, allow_redirects=True)
                if r2 and r2.status_code == 200 and len(r2.text) > 200:
                    magnets = extract_from_html(r2.text, url)
                    if magnets:
                        return {'magnets': len(magnets), 'path': sp, 'bait': bait, 'samples': magnets[:3]}
            except Exception:
                pass
        time.sleep(0.2)

    return {'magnets': 0, 'path': '', 'bait': '', 'samples': []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='*', default=['https://www.ymaoo.cn'])
    parser.add_argument('--no-verify', action='store_true', help='Only extract links, skip verification')
    args = parser.parse_args()

    print("=" * 60, flush=True)
    print("  导航站人机协作爬虫", flush=True)
    print("  操作: 在浏览器中切换到磁力/BT分类 → 按 Enter 提取", flush=True)
    print("=" * 60, flush=True)

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1280,900')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    print("  启动浏览器...", flush=True)
    try:
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(30)
        print("  浏览器已启动!", flush=True)
    except Exception as e:
        print(f"  浏览器启动失败: {e}", flush=True)
        return

    existing, _ = load_existing()
    all_new_links = OrderedDict()

    for nav_url in args.urls:
        print(f"\n{'='*60}", flush=True)
        print(f"  打开导航站: {nav_url}", flush=True)
        print(f"{'='*60}", flush=True)

        try:
            print(f"  正在加载页面（最多等30秒）...", flush=True)
            driver.get(nav_url)
            print(f"  页面加载完成!", flush=True)
        except Exception as e:
            print(f"  页面加载超时或失败: {e}", flush=True)
            print(f"  但浏览器可能已经显示了部分内容，可以继续操作", flush=True)

        while True:
            print(f"\n  [浏览器已打开] 请操作:", flush=True)
            print(f"    1. 过验证码（如果有）", flush=True)
            print(f"    2. 点击切换到磁力/BT/下载分类", flush=True)
            print(f"    3. 等页面加载完", flush=True)
            print(f"    4. 按 Enter 提取当前页面链接", flush=True)
            print(f"    n=下一个导航站  d=完成当前站并继续  q=退出", flush=True)

            ans = input("  >>> ").strip().lower()
            if ans == 'q':
                driver.quit()
                return
            if ans == 'n':
                break
            if ans == 'd':
                links = extract_links_from_page(driver, nav_url)
                for dom, info in links.items():
                    if dom not in existing and dom not in all_new_links:
                        all_new_links[dom] = info
                print(f"  提取到 {len(links)} 个链接（新增 {sum(1 for d in links if d not in existing and d not in [normalize_domain(x) for x in all_new_links.values()])}）")
                break

            links = extract_links_from_page(driver, nav_url)
            new_count = 0
            for dom, info in links.items():
                if dom not in existing and dom not in all_new_links:
                    all_new_links[dom] = info
                    new_count += 1
            print(f"  提取到 {len(links)} 个链接，新增 {new_count}", flush=True)
            for dom, info in links.items():
                if dom not in existing:
                    print(f"      {info.get('title','')[:40]:42s} {dom}", flush=True)

    driver.quit()

    if not all_new_links:
        print("\n  没有提取到新链接")
        return

    print(f"\n{'='*60}")
    print(f"  提取汇总: {len(all_new_links)} 个新域名")
    print(f"{'='*60}")
    for dom, info in all_new_links.items():
        print(f"    {dom:30s} {info.get('title','')[:40]}")

    if args.no_verify:
        with open('nav_links.json', 'w', encoding='utf-8') as f:
            json.dump(list(all_new_links.values()), f, indent=2, ensure_ascii=False)
        print(f"  已保存到 nav_links.json（跳过验证）")
        return

    # Auto verify
    print(f"\n  开始自动验证 {len(all_new_links)} 个候选...")
    verified = []
    need_browser = []

    for i, (dom, info) in enumerate(all_new_links.items()):
        print(f"  [{i+1}/{len(all_new_links)}] {dom}: ", end='', flush=True)
        r = verify_one(info['url'], dom)
        if r and r.get('magnets', 0) > 0:
            print(f"OK ({r['magnets']} magnets)")
            verified.append({**info, 'magnets': r['magnets'], 'path': r['path'],
                            'bait': r['bait'], 'samples': r.get('samples', [])})
        elif r is not None:
            print(f"有磁力关键词但HTTP搜索未提取到，需浏览器验证")
            need_browser.append(info)
        else:
            print(f"跳过")
        time.sleep(0.3)

    # Selenium verify for need_browser
    if need_browser:
        print(f"\n  对 {len(need_browser)} 个候选做 Selenium 验证...")
        opts2 = Options()
        opts2.add_argument('--headless');opts2.add_argument('--disable-gpu');opts2.add_argument('--no-sandbox')
        opts2.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        drv = webdriver.Chrome(options=opts2)
        drv.set_page_load_timeout(20)
        for info in need_browser:
            url = info['url']
            print(f"    {info['domain']}: ", end='', flush=True)
            for bait in BAIT_WORDS[:2]:
                for sp in [f'/search/{urllib.parse.quote(bait)}', f'/search?q={urllib.parse.quote(bait)}',
                            f'/?q={urllib.parse.quote(bait)}']:
                    try:
                        drv.get(url.rstrip('/') + sp)
                        time.sleep(5)
                        magnets = extract_from_html(drv.page_source, url)
                        if magnets:
                            print(f"OK ({len(magnets)} magnets)")
                            verified.append({**info, 'magnets': len(magnets), 'path': sp,
                                            'bait': bait, 'samples': magnets[:3], 'requires_browser': True})
                            break
                        from bs4 import BeautifulSoup
                        hashes = set()
                        for m in HASH_RE.finditer(BeautifulSoup(drv.page_source, 'lxml').get_text()):
                            hashes.add(m.group(0).upper())
                        if len(hashes) >= 2:
                            print(f"OK ({len(hashes)} hashes)")
                            verified.append({**info, 'magnets': len(hashes), 'path': sp,
                                            'bait': bait, 'samples': [], 'requires_browser': True})
                            break
                    except Exception:
                        pass
                if verified and verified[-1].get('domain') == info['domain']:
                    break
            else:
                print(f"未提取到")
            time.sleep(0.3)
        drv.quit()

    # Summary
    print(f"\n{'='*60}")
    print(f"  最终结果")
    print(f"{'='*60}")
    print(f"  验证通过: {len(verified)}")
    for v in verified:
        print(f"    + {v['domain']:25s} {v.get('magnets',0):3d} magnets")

    added = add_to_sources(verified)
    print(f"\n  已添加 {added} 个新源到 sources.json")

    # Save all extracted links for reference
    with open('nav_links.json', 'w', encoding='utf-8') as f:
        json.dump({
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total': len(all_new_links),
            'verified': verified,
            'all_links': list(all_new_links.values()),
        }, f, indent=2, ensure_ascii=False)
    print(f"  完整数据保存到 nav_links.json")
    print("=" * 60)


if __name__ == '__main__':
    main()
