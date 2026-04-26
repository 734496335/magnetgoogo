#!/usr/bin/env python3
"""
Nav Crawler — 导航站磁力源提取器
==================================
爬取导航站页面，识别磁力/BT相关分类，提取其中的站点链接并批量验证。
"""

import sys, os, re, json, time, hashlib, logging, urllib.parse
from datetime import datetime, timezone
from collections import OrderedDict

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
    handlers=[logging.FileHandler('run.log', encoding='utf-8', mode='a'), logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

TORRENT_SECTION_KEYWORDS = [
    '磁力', 'BT', '种子', 'torrent', 'magnet', '搜索', '下载',
    '影视下载', '资源下载', '影视搜索', '网盘搜索', '片源',
    'P2P', '番号', '资源站', '影视站', '福利',
]

TORRENT_SECTION_EXCLUDE = [
    '新闻', '资讯', '购物', '旅游', '招聘', '房产', '汽车', '彩票',
    '政府', '教育', '银行', '保险', '医疗', '美食', '宠物', '装修',
    '音乐播放器', '在线音乐', '图片素材', '设计', '编程', 'AI工具',
    '邮箱', '翻译', '词典', '天气', '地图', '快递', '查询',
    '游戏', '直播', '社交', '论坛', '博客', '问答',
]

HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')
BAIT_WORDS = ['Big Buck Bunny', 'Inception', 'One Piece']

TORRENT_POSITIVE = [
    'magnet:', 'torrent', '种子', '磁力', 'btih', 'seeders', 'leechers',
    'bt搜索', '种子搜索', '磁力搜索', '磁力下载', 'bt下载', 'hash',
]


def normalize_domain(url):
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        p = urllib.parse.urlparse(url)
        d = p.netloc.lower()
        if d.startswith('www.'): d = d[4:]
        return d
    except:
        return ''


def http_get(url, timeout=10):
    try:
        return requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
    except Exception:
        return None


def extract_from_html(html, url=''):
    soup = BeautifulSoup(html, 'lxml')
    magnets = []
    seen = set()
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
            d = normalize_domain(r['site']['origin'])
            existing.add(d)
    return existing, data


def crawl_nav_site(base_url):
    log.info(f"爬取导航站: {base_url}")
    resp = http_get(base_url)
    if not resp or resp.status_code != 200:
        log.info(f"  首页请求失败")
        return []

    soup = BeautifulSoup(resp.text, 'lxml')
    links = []

    sections = []
    for tag in ['h1', 'h2', 'h3', 'h4', 'div', 'section', 'details']:
        for el in soup.find_all(tag):
            text = el.get_text(strip=True)
            if text and len(text) < 50:
                sections.append((el, text))

    torrent_section_els = set()
    for el, text in sections:
        tl = text.lower()
        has_kw = any(kw.lower() in tl for kw in TORRENT_SECTION_KEYWORDS)
        has_excl = any(kw.lower() in tl for kw in TORRENT_SECTION_EXCLUDE)
        if has_kw and not has_excl:
            torrent_section_els.add(id(el))
            for sibling in el.find_next_siblings(limit=10):
                torrent_section_els.add(id(sibling))
            parent = el.parent
            if parent:
                for sibling in parent.find_next_siblings(limit=5):
                    torrent_section_els.add(id(sibling))

    all_links = soup.find_all('a', href=True)
    for a in all_links:
        href = a['href']
        txt = a.get_text(strip=True)
        if not href or href.startswith(('#', 'javascript:', 'mailto:')):
            continue

        near_torrent_section = False
        parent = a.parent
        for _ in range(6):
            if parent is None: break
            if id(parent) in torrent_section_els:
                near_torrent_section = True
                break
            parent = parent.parent

        link_text_lower = txt.lower()
        link_href_lower = href.lower()
        text_has_torrent_kw = any(kw.lower() in link_text_lower for kw in TORRENT_SECTION_KEYWORDS)
        href_has_torrent_kw = any(kw.lower() in link_href_lower for kw in ['magnet', 'torrent', 'bt', 'seed', 'peer', 'hash'])

        if near_torrent_section or text_has_torrent_kw or href_has_torrent_kw:
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = urllib.parse.urljoin(base_url, href)
            domain = normalize_domain(href)
            if domain and domain not in NON_SEARCH_DOMAINS:
                links.append({
                    'url': href,
                    'domain': domain,
                    'title': txt[:80],
                    'in_torrent_section': near_torrent_section,
                    'text_keyword_match': text_has_torrent_kw,
                })

    seen = set()
    unique = []
    for l in links:
        if l['domain'] not in seen:
            seen.add(l['domain'])
            unique.append(l)

    log.info(f"  找到 {len(unique)} 个磁力相关链接")
    for l in unique[:30]:
        marker = '[section]' if l['in_torrent_section'] else '[keyword]'
        log.info(f"    {marker} {l['domain']:30s} {l['title'][:40]}")
    if len(unique) > 30:
        log.info(f"    ... 还有 {len(unique)-30} 个")

    return unique


NON_SEARCH_DOMAINS = {
    'baidu.com', 'bing.com', 'google.com', 'microsoft.com', 'github.com',
    'zhihu.com', 'weibo.com', 'douyin.com', 'bilibili.com', 'youtube.com',
    'qq.com', '163.com', 'taobao.com', 'jd.com', 'douban.com', 'apple.com',
    't.me', 'discord.com', 'telegram.org', 'archive.org', 'wikipedia.org',
    'twitter.com', 'facebook.com', 'instagram.com', 'reddit.com',
    'netflix.com', 'iqiyi.com', 'youku.com', 'mgtv.com', 'letv.com',
    'pptv.com', 'sohu.com', 'toutiao.com', 'csdn.net', 'jianshu.com',
    'alipay.com', 'weixin.qq.com', 'pay.weixin.qq.com', 'open.weixin.qq.com',
    'jquery.com', 'bootstrapcdn.com', 'cdn.jsdelivr.net', 'cdnjs.cloudflare.com',
    'beian.miit.gov.cn', 'beian.mps.gov.cn',
}


def verify_source(url, domain):
    log.info(f"  验证: {domain}")
    resp = http_get(url, timeout=10)
    if not resp or resp.status_code != 200:
        return {'pass': False, 'reason': f'HTTP {resp.status_code if resp else "failed"}'}

    lower = resp.text[:15000].lower()
    has_kw = any(kw in lower for kw in TORRENT_POSITIVE)
    if not has_kw:
        return {'pass': False, 'reason': '无磁力关键词'}

    for bait in BAIT_WORDS:
        for sp in [f'/search/{urllib.parse.quote(bait)}', f'/search?q={urllib.parse.quote(bait)}',
                    f'/?q={urllib.parse.quote(bait)}', f'/?s={urllib.parse.quote(bait)}',
                    f'/search?query={urllib.parse.quote(bait)}']:
            test_url = url.rstrip('/') + sp
            r2 = http_get(test_url, timeout=8)
            if r2 and r2.status_code == 200 and len(r2.text) > 200:
                magnets = extract_from_html(r2.text, url)
                if magnets:
                    return {
                        'pass': True, 'magnets': len(magnets), 'path': sp, 'bait': bait,
                        'samples': magnets[:3],
                    }
        time.sleep(0.2)

    return {'pass': False, 'reason': '搜索未提取到磁力', 'has_kw': True}


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
        log.info(f"  已添加: {d} ({v.get('magnets', 0)} magnets)")
    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
    data['generated_at'] = datetime.now(timezone.utc).isoformat()
    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return added


def main():
    log.info("=" * 60)
    log.info("  导航站磁力源提取器")
    log.info("=" * 60)

    nav_sites = [
        'http://8.210.117.39',
    ]

    all_candidates = OrderedDict()
    existing, _ = load_existing()

    for nav_url in nav_sites:
        links = crawl_nav_site(nav_url)
        for l in links:
            d = l['domain']
            if d and d not in existing and d not in all_candidates:
                all_candidates[d] = {
                    'url': l['url'], 'domain': d, 'title': l['title'],
                    'in_torrent_section': l['in_torrent_section'],
                    'from_nav': nav_url,
                }

    log.info(f"\n  候选磁力源: {len(all_candidates)}")

    verified = []
    need_selenium = []

    for i, (d, info) in enumerate(all_candidates.items()):
        log.info(f"\n[{i+1}/{len(all_candidates)}] {d}: {info['url']}")
        r = verify_source(info['url'], d)
        if r['pass']:
            log.info(f"  OK: {r['magnets']} magnets path={r['path']}")
            verified.append({**info, 'magnets': r['magnets'], 'path': r['path'],
                            'bait': r['bait'], 'samples': r.get('samples', [])})
        elif r.get('has_kw'):
            log.info(f"  需浏览器确认: {r['reason']}")
            need_selenium.append(info)
        else:
            log.info(f"  跳过: {r['reason']}")

    log.info(f"\n{'='*60}")
    log.info(f"  结果: {len(verified)} HTTP验证通过, {len(need_selenium)} 需浏览器确认")
    for v in verified:
        log.info(f"    + {v['domain']:25s} {v['magnets']:3d} magnets")
    for v in need_selenium:
        log.info(f"    ? {v['domain']:25s} {v.get('title','')[:40]}")

    if need_selenium:
        log.info(f"\n  对 {len(need_selenium)} 个候选做 Selenium 验证...")
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument('--headless')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(20)

        for i, info in enumerate(need_selenium):
            url = info['url']
            log.info(f"\n  [{i+1}/{len(need_selenium)}] Selenium: {info['domain']}")
            for bait in BAIT_WORDS[:2]:
                for sp in [f'/search/{urllib.parse.quote(bait)}', f'/search?q={urllib.parse.quote(bait)}',
                            f'/?q={urllib.parse.quote(bait)}']:
                    test_url = url.rstrip('/') + sp
                    try:
                        driver.get(test_url)
                        time.sleep(5)
                        html = driver.page_source
                        magnets = extract_from_html(html, url)
                        if magnets:
                            log.info(f"    OK: {len(magnets)} magnets")
                            verified.append({**info, 'magnets': len(magnets), 'path': sp,
                                            'bait': bait, 'samples': magnets[:3], 'requires_browser': True})
                            break
                        hashes = set()
                        for m in HASH_RE.finditer(BeautifulSoup(html, 'lxml').get_text()):
                            hashes.add(m.group(0).upper())
                        if len(hashes) >= 2:
                            log.info(f"    OK: {len(hashes)} hashes")
                            verified.append({**info, 'magnets': len(hashes), 'path': sp,
                                            'bait': bait, 'samples': [], 'requires_browser': True})
                            break
                    except Exception:
                        pass
                if verified and verified[-1].get('domain') == info['domain']:
                    break
            time.sleep(0.5)
        driver.quit()

    added = add_to_sources(verified)
    log.info(f"\n  新增 {added} 个源到 sources.json")
    log.info("=" * 60)


if __name__ == '__main__':
    main()
