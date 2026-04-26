#!/usr/bin/env python3
"""
Nav Site Link Extractor — 导航站链接深度提取器
===============================================
弹出浏览器，用户手动切到磁力分类后按 Enter，脚本自动：
  1. 提取当前页所有站点链接
  2. 逐个点击进入详情页
  3. 从跳转提示页（"您将离开xxx"）提取真实URL
  4. 收集所有真实URL后批量验证磁力提取

用法:
  python magnet/nav_link_extractor.py https://www.ymaoo.cn
  python magnet/nav_link_extractor.py https://www.4abyte.com http://8.210.117.39
"""
import sys, os, re, json, time, hashlib, logging, urllib.parse
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, parse_qs, unquote

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
    handlers=[logging.FileHandler('run.log', encoding='utf-8', mode='a'), logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')
BAIT_WORDS = ['Big Buck Bunny', 'Inception', 'One Piece']
TORRENT_KW = ['磁力', 'BT', '种子', 'torrent', 'magnet', 'btih', 'seed']


def normalize_domain(url):
    try:
        if not url.startswith(('http://', 'https://')): url = 'http://' + url
        p = urlparse(url); d = p.netloc.lower()
        if d.startswith('www.'): d = d[4:]
        return d
    except:
        return ''


def load_existing():
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    existing = set()
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            existing.add(normalize_domain(r['site']['origin']))
    return existing, data


def extract_magnets(html, url=''):
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


def resolve_redirect_url(href, base_url):
    """从 go.php?url=xxx, link?url=xxx 等中间跳转链接中提取真实URL"""
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)

    for key in ['url', 'target', 'link', 'redirect', 'goto', 'jump', 'dst', 'to']:
        if key in qs:
            real = qs[key][0]
            if real.startswith('http'):
                return real
            decoded = unquote(real)
            if decoded.startswith('http'):
                return decoded

    for key in ['url', 'target', 'link', 'redirect', 'goto']:
        m = re.search(rf'{key}=([^&]+)', href, re.I)
        if m:
            real = unquote(m.group(1))
            if real.startswith('http'):
                return real

    return None


def collect_links_from_page(driver, base_url):
    """从当前页面提取所有外部链接，智能解析跳转链接"""
    from bs4 import BeautifulSoup
    html = driver.page_source
    soup = BeautifulSoup(html, 'lxml')
    base_dom = normalize_domain(base_url)
    links = {}
    for a in soup.find_all('a', href=True):
        href = a['href']
        txt = a.get_text(strip=True)
        if not href or not txt or len(txt) < 2: continue
        if href.startswith(('#', 'javascript:', 'mailto:')): continue

        real_url = None

        # Case 1: go.php?url=xxx 跳转链接
        if any(kw in href.lower() for kw in ['go.php', 'link.php', 'jump.php', 'redirect', 'out.php',
                                               'goto.php', '/go/', '/link/', '/jump/', '/out/']):
            real_url = resolve_redirect_url(href, base_url)

        # Case 2: 完整外部链接
        elif href.startswith('http'):
            real_url = href

        # Case 3: 相对路径
        elif href.startswith('/'):
            real_url = urljoin(base_url, href)

        if not real_url or not real_url.startswith('http'):
            continue

        dom = normalize_domain(real_url)
        if dom and dom != base_dom:
            if dom not in links:
                links[dom] = {'url': real_url, 'domain': dom, 'title': txt[:80]}
    return links


def click_and_resolve(driver, base_url, max_clicks=30):
    """
    遍历当前页面上的站点链接，逐个点击进入详情页，
    从详情页/跳转提示页提取真实URL，然后返回列表页
    """
    from bs4 import BeautifulSoup
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    base_dom = normalize_domain(base_url)
    resolved = {}

    # 收集所有可点击的站点链接元素
    html = driver.page_source
    soup = BeautifulSoup(html, 'lxml')
    clickables = []
    seen_hrefs = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        txt = a.get_text(strip=True)
        if not href or not txt or len(txt) < 2: continue
        if href.startswith(('#', 'javascript:', 'mailto:')): continue

        if href.startswith('http'):
            dom = normalize_domain(href)
            if dom == base_dom: continue
        elif href.startswith('/'):
            dom = None
        else:
            continue

        abs_url = urljoin(base_url, href) if href.startswith('/') else href
        if abs_url in seen_hrefs: continue
        seen_hrefs.add(abs_url)

        # 用URL找selenium元素
        css = f'a[href="{href}"]'
        try:
            el = driver.find_element(By.CSS_SELECTOR, css)
            if el.is_displayed():
                clickables.append((el, href, txt, abs_url))
        except Exception:
            pass

    log.info(f"  找到 {len(clickables)} 个可点击链接")

    for i, (el, href, txt, abs_url) in enumerate(clickables[:max_clicks]):
        if i > 0 and i % 5 == 0:
            log.info(f"  [{i}/{len(clickables)}] 已处理...")

        # 先尝试从href直接解析跳转链接
        real_url = None
        if any(kw in href.lower() for kw in ['go.php', 'link.php', '/go/', '/link/', 'redirect', 'out.php']):
            real_url = resolve_redirect_url(href, base_url)

        if real_url:
            dom = normalize_domain(real_url)
            if dom and dom != base_dom and dom not in resolved:
                resolved[dom] = {'url': real_url, 'domain': dom, 'title': txt[:80]}
                log.info(f"    + {dom:30s} {txt[:30]} (跳转解析)")
            continue

        # 点击打开详情页
        try:
            main_window = driver.current_window_handle
            el.click()
            time.sleep(2)

            # 检查是否打开了新标签页
            windows = driver.window_handles
            if len(windows) > 1:
                driver.switch_to.window(windows[-1])
                time.sleep(2)
                detail_url = driver.current_url
                detail_html = driver.page_source

                # 检查是否是跳转提示页
                real_url = extract_real_url_from_interstitial(detail_html, detail_url, base_url)

                if real_url:
                    dom = normalize_domain(real_url)
                    if dom and dom != base_dom and dom not in resolved:
                        resolved[dom] = {'url': real_url, 'domain': dom, 'title': txt[:80]}
                        log.info(f"    + {dom:30s} {txt[:30]} (新标签跳转页)")
                else:
                    dom = normalize_domain(detail_url)
                    if dom and dom != base_dom and dom not in resolved:
                        resolved[dom] = {'url': detail_url, 'domain': dom, 'title': txt[:80]}
                        log.info(f"    + {dom:30s} {txt[:30]} (新标签直达)")

                driver.close()
                driver.switch_to.window(main_window)
            else:
                # 同标签页跳转
                detail_url = driver.current_url
                detail_html = driver.page_source

                real_url = extract_real_url_from_interstitial(detail_html, detail_url, base_url)
                if real_url:
                    dom = normalize_domain(real_url)
                    if dom and dom != base_dom and dom not in resolved:
                        resolved[dom] = {'url': real_url, 'domain': dom, 'title': txt[:80]}
                        log.info(f"    + {dom:30s} {txt[:30]} (跳转页)")
                else:
                    dom = normalize_domain(detail_url)
                    if dom and dom != base_dom and dom not in resolved:
                        resolved[dom] = {'url': detail_url, 'domain': dom, 'title': txt[:80]}
                        log.info(f"    + {dom:30s} {txt[:30]} (直达)")

                driver.back()
                time.sleep(2)
                # 重新定位元素（DOM可能变了）
                try:
                    css = f'a[href="{href}"]'
                    els = driver.find_elements(By.CSS_SELECTOR, css)
                    if els:
                        clickables[i] = (els[0], href, txt, abs_url)
                except Exception:
                    pass

        except Exception as e:
            log.info(f"    x {txt[:30]} 错误: {str(e)[:40]}")
            try:
                driver.switch_to.window(main_window)
            except Exception:
                pass

    return resolved


def extract_real_url_from_interstitial(html, current_url, base_url):
    """从跳转提示页提取真实URL"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')

    # 1. 查找带跳转关键词的链接
    for a in soup.find_all('a', href=True):
        href = a['href']
        txt = a.get_text(strip=True).lower()
        if any(kw in txt for kw in ['直达', '立即访问', '点击访问', '前往', 'continue', 'visit', 'go to',
                                      '确认跳转', '访问', 'enter', '进入', '前往站点']):
            if href.startswith('http'):
                return href
            real = resolve_redirect_url(href, base_url)
            if real:
                return real

    # 2. 查找所有外部链接（排除当前站和导航站）
    base_dom = normalize_domain(base_url)
    cur_dom = normalize_domain(current_url)
    for a in soup.find_all('a', href=True):
        href = a['href']
        if not href.startswith('http'): continue
        dom = normalize_domain(href)
        if dom and dom != base_dom and dom != cur_dom:
            # 优先找看起来像目标站的链接
            if 'go.php' not in href and 'redirect' not in href:
                return href

    # 3. 从JS中提取URL
    for script in soup.find_all('script'):
        text = script.get_text()
        urls = re.findall(r'https?://[^\s\'"<>]+', text)
        for u in urls:
            dom = normalize_domain(u)
            if dom and dom != base_dom and dom != cur_dom:
                return u.split('\\')[0].rstrip("');")

    # 4. 从meta refresh提取
    meta = soup.find('meta', attrs={'http-equiv': 'refresh'})
    if meta:
        content = meta.get('content', '')
        m = re.search(r'url=(.+)', content, re.I)
        if m:
            return m.group(1).strip("'\"")

    return None


def verify_source(url, domain):
    import requests
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
    except Exception:
        return None
    if not resp or resp.status_code != 200 or len(resp.text) < 300:
        return None

    lower = resp.text[:15000].lower()
    if not any(kw in lower for kw in TORRENT_KW):
        return None

    for bait in BAIT_WORDS:
        for sp in [f'/search/{urllib.parse.quote(bait)}', f'/search?q={urllib.parse.quote(bait)}',
                    f'/?q={urllib.parse.quote(bait)}', f'/?s={urllib.parse.quote(bait)}',
                    f'/search?keyword={urllib.parse.quote(bait)}', f'/search?query={urllib.parse.quote(bait)}',
                    f'/s/{urllib.parse.quote(bait)}']:
            try:
                r2 = requests.get(url.rstrip('/') + sp, timeout=8, headers=HEADERS, allow_redirects=True)
                if r2 and r2.status_code == 200 and len(r2.text) > 200:
                    magnets = extract_magnets(r2.text, url)
                    if magnets:
                        return {'magnets': len(magnets), 'path': sp, 'bait': bait, 'samples': magnets[:3]}
            except Exception:
                pass
        time.sleep(0.2)

    return {'magnets': 0, 'path': '', 'has_kw': True}


def selenium_verify(driver, url, domain):
    from bs4 import BeautifulSoup
    for bait in BAIT_WORDS[:2]:
        for sp in [f'/search/{urllib.parse.quote(bait)}', f'/search?q={urllib.parse.quote(bait)}',
                    f'/?q={urllib.parse.quote(bait)}']:
            try:
                driver.get(url.rstrip('/') + sp)
                time.sleep(5)
                magnets = extract_magnets(driver.page_source, url)
                if magnets:
                    return {'magnets': len(magnets), 'path': sp, 'bait': bait, 'samples': magnets[:3]}
                hashes = set()
                for m in HASH_RE.finditer(BeautifulSoup(driver.page_source, 'lxml').get_text()):
                    hashes.add(m.group(0).upper())
                if len(hashes) >= 2:
                    return {'magnets': len(hashes), 'path': sp, 'bait': bait, 'samples': []}
            except Exception:
                pass
    return None


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
        if v.get('brand'): rule['site']['brand'] = v['brand']
        ruleset['rules'].append(rule)
        added += 1
        log.info(f"  Added: {d} ({v.get('magnets', 0)} magnets)")
    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
    data['generated_at'] = datetime.now(timezone.utc).isoformat()
    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return added


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='*', default=['https://www.ymaoo.cn'])
    parser.add_argument('--skip-click', action='store_true', help='Only extract from current page, skip clicking into details')
    parser.add_argument('--max-clicks', type=int, default=30)
    args = parser.parse_args()

    print("=" * 60, flush=True)
    print("  导航站链接深度提取器", flush=True)
    print("=" * 60, flush=True)

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1280,900')
    print("  启动浏览器...", flush=True)
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(3)
    print("  OK!", flush=True)

    existing, _ = load_existing()
    all_resolved = {}

    for nav_url in args.urls:
        print(f"\n{'='*60}", flush=True)
        print(f"  打开: {nav_url}", flush=True)
        print(f"{'='*60}", flush=True)

        try:
            driver.get(nav_url)
            print(f"  页面加载完成", flush=True)
        except Exception:
            print(f"  加载超时，但页面可能已部分显示", flush=True)

        while True:
            print(f"\n  请在浏览器中操作:", flush=True)
            print(f"    1. 手动切换到磁力/BT/下载分类", flush=True)
            print(f"    2. 等页面加载完", flush=True)
            print(f"  然后按:", flush=True)
            print(f"    Enter = 提取当前页面链接（不点击）", flush=True)
            print(f"    c = 自动点击每个链接并提取真实URL", flush=True)
            print(f"    d = 完成，进入下一站", flush=True)
            print(f"    q = 退出", flush=True)

            ans = input("  >>> ").strip().lower()

            if ans == 'q':
                driver.quit()
                return
            if ans == 'd':
                break
            if ans == 'c':
                print(f"\n  开始自动点击提取...", flush=True)
                resolved = click_and_resolve(driver, nav_url, max_clicks=args.max_clicks)
                new = 0
                for dom, info in resolved.items():
                    if dom not in existing and dom not in all_resolved:
                        all_resolved[dom] = info
                        new += 1
                print(f"\n  点击提取完成: {len(resolved)} 个站点，新增 {new}", flush=True)
                for dom, info in all_resolved.items():
                    print(f"    {dom:30s} {info.get('title','')[:30]}", flush=True)
                continue

            # Enter: extract from current page
            links = collect_links_from_page(driver, nav_url)
            new = 0
            for dom, info in links.items():
                if dom not in existing and dom not in all_resolved:
                    all_resolved[dom] = info
                    new += 1
            print(f"\n  提取到 {len(links)} 个链接，新增 {new}", flush=True)
            for dom, info in links.items():
                if dom not in existing:
                    print(f"    {dom:30s} {info.get('title','')[:30]}", flush=True)

    driver.quit()

    if not all_resolved:
        print("\n  没有提取到新链接", flush=True)
        return

    print(f"\n{'='*60}", flush=True)
    print(f"  共提取到 {len(all_resolved)} 个新域名，开始验证...", flush=True)
    print(f"{'='*60}", flush=True)

    verified = []
    need_browser = []

    for i, (dom, info) in enumerate(all_resolved.items()):
        log.info(f"  [{i+1}/{len(all_resolved)}] {dom}")
        r = verify_source(info['url'], dom)
        if r and r.get('magnets', 0) > 0:
            log.info(f"    OK! {r['magnets']} magnets path={r['path']}")
            verified.append({**info, 'magnets': r['magnets'], 'path': r['path'],
                            'bait': r['bait'], 'samples': r.get('samples', [])})
        elif r and r.get('has_kw'):
            log.info(f"    有磁力关键词，需浏览器验证")
            need_browser.append(info)
        else:
            log.info(f"    跳过")
        time.sleep(0.3)

    if need_browser:
        log.info(f"\n  Selenium 验证 {len(need_browser)} 个...")
        opts2 = Options()
        opts2.add_argument('--headless'); opts2.add_argument('--disable-gpu'); opts2.add_argument('--no-sandbox')
        drv = webdriver.Chrome(options=opts2)
        drv.set_page_load_timeout(20)
        for info in need_browser:
            log.info(f"    {info['domain']}")
            r = selenium_verify(drv, info['url'], info['domain'])
            if r:
                log.info(f"      OK! {r['magnets']} magnets")
                verified.append({**info, 'magnets': r['magnets'], 'path': r['path'],
                                'bait': r['bait'], 'samples': r.get('samples', []), 'requires_browser': True})
        drv.quit()

    print(f"\n{'='*60}", flush=True)
    print(f"  结果", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  验证通过: {len(verified)}", flush=True)
    for v in verified:
        print(f"    + {v['domain']:25s} {v.get('magnets',0):3d} magnets", flush=True)

    added = add_to_sources(verified)
    print(f"\n  新增 {added} 个源到 sources.json", flush=True)
    print("=" * 60, flush=True)

    with open('nav_resolved.json', 'w', encoding='utf-8') as f:
        json.dump({'generated_at': datetime.now(timezone.utc).isoformat(),
                   'total': len(all_resolved), 'verified': verified,
                   'all': list(all_resolved.values())}, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
