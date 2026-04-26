#!/usr/bin/env python3
"""
Nav Auto Crawler — 导航站全自动磁力源提取器
=============================================
全自动流程，无需人工参与：
  1. 打开导航站
  2. 扫描页面所有Tab/分类按钮，用关键词识别"磁力/BT"相关Tab
  3. 自动点击该Tab
  4. 等待卡片加载
  5. 识别卡片区域中的链接
  6. 逐个点击卡片 → 详情页 → 找"直达链接" → 跳转页 → 提取真实URL
  7. 批量验证 → 加入 sources.json

用法:
  python magnet/nav_auto_crawler.py https://www.ymaoo.cn
  python magnet/nav_auto_crawler.py https://www.4abyte.com
  python magnet/nav_auto_crawler.py https://www.ymaoo.cn https://www.4abyte.com http://8.210.117.39
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
TORRENT_POSITIVE = ['magnet:', 'torrent', '种子', '磁力', 'btih', 'seeders', 'leechers',
                    'bt搜索', '种子搜索', '磁力搜索', '磁力下载', 'bt下载']

TAB_CLICK_KW = ['磁力', 'BT', '种子', 'torrent', 'magnet', '下载', '资源下载', '影视下载', '片源']
TAB_EXCLUDE_KW = ['在线', '直播', '观看', '购物', '音乐', 'AI', '工具', '导航', '排行榜', '热搜']
CARD_KW = ['磁力', 'BT', '种子', 'torrent', 'magnet', '搜索', '引擎', '下载站']


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


def resolve_redirect_url(href):
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    for key in ['url', 'target', 'link', 'redirect', 'goto', 'jump', 'dst', 'to', 'u']:
        if key in qs:
            real = qs[key][0]
            if real.startswith('http'): return real
            decoded = unquote(real)
            if decoded.startswith('http'): return decoded
    for key in ['url', 'target', 'link', 'redirect', 'goto', 'u']:
        m = re.search(rf'{key}=([^&]+)', href, re.I)
        if m:
            real = unquote(m.group(1))
            if real.startswith('http'): return real
    return None


def find_and_click_torrent_tab(driver, base_url):
    """扫描页面所有可点击元素，找到磁力/BT相关的Tab并点击"""
    from selenium.webdriver.common.by import By
    from bs4 import BeautifulSoup

    log.info("  扫描页面Tab/分类按钮...")

    # 找所有可点击元素（Tab/按钮/链接）
    candidates = driver.find_elements(By.CSS_SELECTOR,
        'a, button, span[onclick], div[onclick], li[onclick], '
        'a[href="#"], a[href="javascript:void(0)"], '
        '.tab, .nav-item, .category, .menu-item, .filter-btn, '
        '[role="tab"], [data-tab], [data-toggle], [data-category]')

    log.info(f"  找到 {len(candidates)} 个可点击元素")

    torrent_tabs = []
    for el in candidates:
        try:
            if not el.is_displayed(): continue
            text = el.text.strip()
            if not text or len(text) > 30: continue
            tl = text.lower()
            is_match = any(kw.lower() in tl for kw in TAB_CLICK_KW)
            is_exclude = any(kw.lower() in tl for kw in TAB_EXCLUDE_KW)
            if is_match and not is_exclude:
                torrent_tabs.append((el, text))
        except Exception:
            continue

    log.info(f"  识别到 {len(torrent_tabs)} 个磁力相关Tab:")
    for el, text in torrent_tabs:
        log.info(f"    - \"{text}\"")

    if not torrent_tabs:
        log.info("  未找到磁力Tab，尝试滚动页面查找...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        time.sleep(2)
        # 再找一次
        candidates2 = driver.find_elements(By.CSS_SELECTOR, 'a, button, [role="tab"], [data-tab]')
        for el in candidates2:
            try:
                if not el.is_displayed(): continue
                text = el.text.strip()
                if not text or len(text) > 30: continue
                tl = text.lower()
                is_match = any(kw.lower() in tl for kw in TAB_CLICK_KW)
                is_exclude = any(kw.lower() in tl for kw in TAB_EXCLUDE_KW)
                if is_match and not is_exclude:
                    if not any(t == text for _, t in torrent_tabs):
                        torrent_tabs.append((el, text))
                        log.info(f"    + \"{text}\" (滚动后)")
            except Exception:
                continue

    # 点击找到的Tab
    clicked = []
    for el, text in torrent_tabs:
        try:
            log.info(f"  点击Tab: \"{text}\"")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.5)
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            time.sleep(3)
            clicked.append(text)
        except Exception as e:
            log.info(f"    点击失败: {e}")

    return clicked


def extract_card_links(driver, base_url):
    """从当前页面提取磁力卡片的链接"""
    from bs4 import BeautifulSoup

    html = driver.page_source
    soup = BeautifulSoup(html, 'lxml')
    base_dom = normalize_domain(base_url)

    # 标记磁力区域
    torrent_section_ids = set()
    for tag in soup.find_all(True):
        if tag.name not in ('h1','h2','h3','h4','h5','span','div','dt','a','button','li','section'): continue
        text = tag.get_text(strip=True)
        if not text or len(text) > 40: continue
        tl = text.lower()
        is_t = any(kw.lower() in tl for kw in ['磁力','BT','种子','torrent','magnet','下载专区','影视下载','资源下载'])
        is_e = any(kw.lower() in tl for kw in ['在线观看','直播','在线影视','购物','AI'])
        if is_t and not is_e:
            torrent_section_ids.add(id(tag))
            if tag.parent: torrent_section_ids.add(id(tag.parent))
            if tag.parent and tag.parent.parent: torrent_section_ids.add(id(tag.parent.parent))

    # 提取卡片链接
    cards = []
    seen = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        txt = a.get_text(strip=True)
        if not href or not txt or len(txt) < 2: continue
        if href.startswith(('#', 'javascript:', 'mailto:')): continue

        in_section = False
        el = a
        for _ in range(10):
            if el is None: break
            if id(el) in torrent_section_ids:
                in_section = True
                break
            el = el.parent

        tl = txt.lower()
        text_match = any(kw.lower() in tl for kw in CARD_KW)

        if in_section or text_match:
            if href.startswith('//'): href = 'https:' + href
            elif href.startswith('/'): href = urljoin(base_url, href)
            if not href.startswith('http'): continue
            dom = normalize_domain(href)
            if dom == base_dom: continue
            if href in seen: continue
            seen.add(href)
            cards.append({'href': href, 'domain': dom, 'title': txt[:80],
                         'in_section': in_section, 'text_match': text_match})

    return cards


def click_and_resolve(driver, card_href, base_url):
    """点击卡片 → 详情页 → 找直达链接 → 跳转页 → 提取真实URL"""
    from selenium.webdriver.common.by import By
    from bs4 import BeautifulSoup

    main_window = driver.current_window_handle

    # 定位卡片
    try:
        el = driver.find_element(By.CSS_SELECTOR, f'a[href="{card_href}"]')
    except Exception:
        try:
            short = card_href[-40:] if len(card_href) > 40 else card_href
            el = driver.find_element(By.CSS_SELECTOR, f'a[href*="{short}"]')
        except Exception:
            return None

    # 点击
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.3)
        el.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
        except Exception:
            return None

    time.sleep(2)

    # 检查新标签
    windows = driver.window_handles
    new_tab = len(windows) > 1
    if new_tab:
        driver.switch_to.window(windows[-1])
        time.sleep(2)

    detail_html = driver.page_source
    detail_url = driver.current_url

    # 找直达链接
    real_url = _find_direct_link(detail_html, detail_url, base_url)

    if not real_url:
        real_url = _extract_from_interstitial(detail_html, detail_url, base_url)

    if not real_url:
        # 没找到直达链接，当前页面可能就是目标站（某些导航站直接跳转）
        dom = normalize_domain(detail_url)
        base_dom = normalize_domain(base_url)
        if dom and dom != base_dom:
            real_url = detail_url

    # 回到列表
    if new_tab:
        try:
            driver.close()
            driver.switch_to.window(main_window)
        except Exception:
            pass
    else:
        try:
            driver.back()
            time.sleep(2)
        except Exception:
            pass

    return real_url


def _find_direct_link(html, current_url, base_url):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')

    for a in soup.find_all('a', href=True):
        t = a.get_text(strip=True).lower()
        href = a['href']
        if any(kw in t for kw in ['直达', '立即访问', '点击访问', '前往', 'continue', 'visit',
                                    '确认跳转', '访问站点', '进入站点', '前往站点', 'go to',
                                    '进入网站', '点此访问', '立即前往', '获取链接', '打开']):
            if href.startswith('http'):
                dom = normalize_domain(href)
                if dom != normalize_domain(base_url):
                    return href
            resolved = resolve_redirect_url(href)
            if resolved: return resolved
            if href.startswith('/'):
                full = urljoin(current_url, href)
                return _follow_redirect(full)

    for a in soup.find_all('a', href=True):
        href = a['href']
        if any(kw in href.lower() for kw in ['go.php', 'link.php', '/go/', '/link/', 'redirect', 'out.php', 'jump']):
            resolved = resolve_redirect_url(href)
            if resolved: return resolved

    return None


def _extract_from_interstitial(html, current_url, base_url):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    base_dom = normalize_domain(base_url)
    cur_dom = normalize_domain(current_url)

    meta = soup.find('meta', attrs={'http-equiv': 'refresh'})
    if meta:
        content = meta.get('content', '')
        m = re.search(r'url=(.+)', content, re.I)
        if m: return m.group(1).strip("'\"")

    for script in soup.find_all('script'):
        text = script.get_text()
        urls = re.findall(r'https?://[^\s\'"<>\\]+', text)
        for u in urls:
            dom = normalize_domain(u)
            if dom and dom != base_dom and dom != cur_dom:
                return u.split('\\')[0].rstrip("');")

    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('http'):
            dom = normalize_domain(href)
            if dom and dom != base_dom and dom != cur_dom:
                if 'go.php' not in href:
                    return href
    return None


def _follow_redirect(url):
    import requests
    try:
        resp = requests.get(url, timeout=5, headers=HEADERS, allow_redirects=True)
        if resp.status_code == 200:
            return resp.url
    except Exception:
        pass
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
    if not any(kw in lower for kw in TORRENT_POSITIVE):
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
    return {'magnets': 0, 'has_kw': True}


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


def process_nav_site(driver, nav_url, existing):
    """处理单个导航站：找Tab → 点击 → 提取卡片 → 点击穿透"""
    log.info(f"\n{'='*60}")
    log.info(f"  NAV: {nav_url}")
    log.info(f"{'='*60}")

    try:
        driver.get(nav_url)
        log.info(f"  页面加载完成")
    except Exception:
        log.info(f"  加载超时，继续...")

    time.sleep(3)

    # Step 1: 找并点击磁力Tab
    tabs = find_and_click_torrent_tab(driver, nav_url)
    if not tabs:
        log.info("  未找到磁力Tab，尝试直接提取当前页卡片...")

    time.sleep(2)

    # Step 2: 提取卡片
    cards = extract_card_links(driver, nav_url)
    new_cards = [c for c in cards if c['domain'] not in existing]
    log.info(f"  识别到 {len(cards)} 个卡片，{len(new_cards)} 个新的")
    for c in new_cards:
        marker = '[区域]' if c['in_section'] else '[文本]'
        log.info(f"    {marker} {c['domain']:30s} {c['title'][:35]}")

    if not new_cards:
        log.info("  没有新卡片")
        return {}

    # Step 3: 逐个点击穿透提取真实URL
    log.info(f"\n  开始点击穿透 {len(new_cards)} 个卡片...")

    resolved = {}
    for i, card in enumerate(new_cards):
        log.info(f"  [{i+1}/{len(new_cards)}] {card['title'][:30]} ({card['domain']})")
        real_url = click_and_resolve(driver, card['href'], nav_url)
        if real_url:
            dom = normalize_domain(real_url)
            if dom and dom not in existing and dom not in resolved:
                resolved[dom] = {
                    'url': real_url, 'domain': dom,
                    'title': card['title'][:80],
                    'brand': card['title'].split()[0] if card['title'] else '',
                }
                log.info(f"    => {dom}")
            else:
                log.info(f"    => 已存在: {dom or real_url[:40]}")
        else:
            log.info(f"    => 未提取到真实地址")
        time.sleep(0.5)

    log.info(f"\n  从 {nav_url} 提取到 {len(resolved)} 个真实地址")
    return resolved


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='*', default=['https://www.ymaoo.cn'])
    parser.add_argument('--max-clicks', type=int, default=50)
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("  Nav Auto Crawler — 全自动导航站磁力源提取")
    log.info("=" * 60)

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1280,900')
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(3)

    existing, _ = load_existing()
    all_resolved = {}

    for nav_url in args.urls:
        resolved = process_nav_site(driver, nav_url, existing)
        all_resolved.update(resolved)

    driver.quit()

    if not all_resolved:
        log.info("\n  没有提取到新链接")
        return

    log.info(f"\n{'='*60}")
    log.info(f"  共提取到 {len(all_resolved)} 个真实地址，开始验证...")
    log.info(f"{'='*60}")

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

    log.info(f"\n{'='*60}")
    log.info(f"  最终结果")
    log.info(f"{'='*60}")
    log.info(f"  验证通过: {len(verified)}")
    for v in verified:
        log.info(f"    + {v['domain']:25s} {v.get('magnets',0):3d} magnets")

    added = add_to_sources(verified)
    log.info(f"\n  新增 {added} 个源到 sources.json")
    log.info("=" * 60)

    with open('nav_resolved.json', 'w', encoding='utf-8') as f:
        json.dump({'generated_at': datetime.now(timezone.utc).isoformat(),
                   'total': len(all_resolved), 'verified': verified,
                   'all': list(all_resolved.values())}, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
