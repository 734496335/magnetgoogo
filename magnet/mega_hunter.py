#!/usr/bin/env python3
"""
Mega Hunter v1 — 多策略源发现引擎
==================================
策略矩阵:
  S1 品牌复活: 已知品牌名 → 搜索引擎找新域名 → 域名发布页
  S2 搜索引擎: 多关键词多引擎搜索 → 提取域名
  S3 导航站深度爬取: 导航站 → 提取所有链接 → 递归到其他导航站 → 提取磁力源
  S4 论坛/社区: 搜索引擎找磁力相关论坛/贴吧/频道 → 提取分享的源
  S5 DHT索引站: 已知 DHT 索引站域名变体探测
  S6 域名发布页: 找品牌的域名发布页（更长久）

输出: 绿色源直接写入 sources.json，候选源写入 candidates.json 待 Selenium 验证
"""

import sys, os, re, json, time, hashlib, logging, urllib.parse
from datetime import datetime, timezone
from collections import OrderedDict

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
    handlers=[logging.FileHandler('run.log', encoding='utf-8', mode='w'), logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')
CANDIDATES_FILE = os.path.join(BASE_DIR, '..', 'mega_hunter_candidates.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}
HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')

TORRENT_KW = ['magnet:', 'torrent', '种子', '磁力', 'btih', 'bit torrent', 'bittorrent', 'bt下载']
PARKING_KW = ['domain for sale', 'domain parking', 'buy this domain', 'sedo', 'parking page', '域名出售']

SKIP_DOMAINS = {
    'baidu.com', 'bing.com', 'google.com', 'google.com.hk', 'googleusercontent.com',
    'microsoft.com', 'github.com', 'zhihu.com', 'weibo.com', 'douyin.com',
    'bilibili.com', 'youtube.com', 'twitter.com', 'facebook.com', 'wikipedia.org',
    'taobao.com', 'jd.com', 'tmall.com', 'qq.com', '163.com', 'sina.com.cn',
    'sohu.com', 'toutiao.com', 'csdn.net', 'jianshu.com', 'apple.com', 'amazon.com',
    'go.microsoft.com', 'passport.baidu.com', 'voice.baidu.com', 'news.baidu.com',
    'hao123.com', 'map.baidu.com', 'v.baidu.com', 'tieba.baidu.com', 'image.baidu.com',
    'wenku.baidu.com', 'top.baidu.com', 'zhidao.baidu.com', 'jingyan.baidu.com',
    'help.baidu.com', 'e.baidu.com', 'open.baidu.com', 'chat.baidu.com',
    'xueshu.baidu.com', 'discord.com', 'discord.gg', 't.me', 'telegram.org',
    'archive.org', 'douban.com', 'movie.douban.com',
}


BRAND_REGISTRY = {
    'javbus': {'names': ['javbus', 'jav bus', 'javbus论坛'], 'publish_pages': ['https://www.javbus.com', 'https://www.javbus.org']},
    'btsow': {'names': ['btsow', 'bt sow', 'btsow磁力'], 'publish_pages': []},
    'nyaa': {'names': ['nyaa', 'nyaa.si', 'nyaa pantsu'], 'publish_pages': []},
    '磁力猫': {'names': ['磁力猫', 'cilimao', 'cili猫'], 'publish_pages': []},
    '磁力狗': {'names': ['磁力狗', 'ciligou'], 'publish_pages': []},
    'torrentkitty': {'names': ['torrentkitty', 'torrent kitty', '磁力猫kitty'], 'publish_pages': []},
    'thepiratebay': {'names': ['thepiratebay', 'tpb', 'pirate bay'], 'publish_pages': []},
    '1337x': {'names': ['1337x', '1337x.to'], 'publish_pages': []},
    'rarbg': {'names': ['rarbg', 'rarbg.to'], 'publish_pages': []},
    'yts': {'names': ['yts', 'yts.mx', 'yify'], 'publish_pages': []},
    'eztv': {'names': ['eztv', 'eztv.re'], 'publish_pages': []},
    'limetorrents': {'names': ['limetorrents'], 'publish_pages': []},
    'solidtorrents': {'names': ['solidtorrents'], 'publish_pages': []},
    'torlock': {'names': ['torlock'], 'publish_pages': []},
    'kickasstorrents': {'names': ['kickasstorrents', 'kat', 'kickass'], 'publish_pages': []},
    'torrentgalaxy': {'names': ['torrentgalaxy'], 'publish_pages': []},
    'extratorrent': {'names': ['extratorrent'], 'publish_pages': []},
    'bitsnoop': {'names': ['bitsnoop'], 'publish_pages': []},
    'torrentz2': {'names': ['torrentz2', 'torrentz'], 'publish_pages': []},
    'idope': {'names': ['idope'], 'publish_pages': []},
    'aiosearch': {'names': ['aiosearch', 'aio search'], 'publish_pages': []},
    'magnetdl': {'names': ['magnetdl'], 'publish_pages': []},
    'snowfl': {'names': ['snowfl', 'snowfl.com'], 'publish_pages': []},
    '0magnet': {'names': ['0magnet', 'omagnet'], 'publish_pages': []},
    'btdigg': {'names': ['btdigg'], 'publish_pages': []},
    'bt4g': {'names': ['bt4g'], 'publish_pages': []},
    'acgrip': {'names': ['acgrip', 'acg.rip'], 'publish_pages': []},
    'mikanani': {'names': ['mikanani', 'mikan', '蜜柑计划'], 'publish_pages': []},
    'dmhy': {'names': ['dmhy', '动漫花园'], 'publish_pages': []},
    'bangumi': {'names': ['bangumi.moe'], 'publish_pages': []},
    'share.dmhy': {'names': ['share.dmhy.org'], 'publish_pages': []},
    'judas': {'names': ['judas'], 'publish_pages': []},
    'jps': {'names': ['jps', 'jpopsuki'], 'publish_pages': []},
    'redacted': {'names': ['redacted', 'red'], 'publish_pages': []},
}

SEARCH_KEYWORDS_S1 = ['新域名', '最新地址', '网址发布页', '最新网址', 'address', 'new domain', 'official site 2026', '最新入口']
SEARCH_KEYWORDS_S2 = [
    '磁力搜索', '磁力链接', 'BT搜索', '种子搜索', 'magnet search',
    'torrent search', '磁力搜索引擎', 'BT下载', '磁力下载',
    'magnet link search engine', 'best torrent site 2026',
    '磁力搜索导航', 'BT导航', '磁力网址导航', 'torrent site list',
    '种子网站大全', '磁力网站大全', '免费BT下载', 'free torrent download',
]
SEARCH_KEYWORDS_S3 = [
    '磁力导航', 'BT导航', '磁力网址导航', '磁力网站大全',
    '种子网站导航', 'BT网站大全', '磁力搜索导航站',
]
SEARCH_KEYWORDS_S4 = [
    '磁力搜索 site:v2ex.com', '磁力搜索 site:reddit.com',
    '磁力站推荐 2026', '好用的磁力搜索', '磁力搜索推荐',
    'torrent site recommendation 2026', 'best magnet site',
]


def normalize_domain(url):
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        p = urllib.parse.urlparse(url)
        d = p.netloc.lower()
        if d.startswith('www.'):
            d = d[4:]
        if not d or '.' not in d or len(d) > 60 or '_' in d:
            return ''
        if d.startswith(('javascript:', 'data:', 'mailto:')):
            return ''
        return d
    except:
        return ''


def extract_domains_from_search(html, engine='unknown'):
    soup = BeautifulSoup(html, 'lxml')
    domains = OrderedDict()
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if not href:
            continue

        real_url = href
        if 'baidu.com/link?' in href:
            match = re.search(r'[?&]url=([^&]+)', href)
            if match:
                real_url = urllib.parse.unquote(match.group(1))
        elif 'bing.com' in href and '/search?' not in href:
            if any(k in href for k in ['aclib?', 'aclick?', '/a/']):
                continue
        elif 'google.com/url?' in href:
            match = re.search(r'[?&]q=([^&]+)', href)
            if match:
                real_url = urllib.parse.unquote(match.group(1))

        domain = normalize_domain(real_url)
        if domain and domain not in SKIP_DOMAINS and domain not in domains:
            title = a.get_text(strip=True)[:80]
            domains[domain] = {'url': f'https://{domain}', 'title': title, 'engine': engine}
    return domains


def extract_all_links(html, base_url):
    soup = BeautifulSoup(html, 'lxml')
    links = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if not href or href.startswith(('#', 'javascript:', 'mailto:')):
            continue
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = urllib.parse.urljoin(base_url, href)
        domain = normalize_domain(href)
        if domain and domain not in SKIP_DOMAINS:
            links.add(href)
    return links


def has_torrent_keywords(html):
    lower = html[:15000].lower()
    return any(kw.lower() in lower for kw in TORRENT_KW)


def is_parking(html):
    lower = html[:5000].lower()
    return any(kw in lower for kw in PARKING_KW)


def extract_magnets_from_html(html, url=''):
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
        results.append({'title': title, 'magnet': a['href'][:120]})
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
    return results


def http_get(url, timeout=8):
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        return resp
    except Exception:
        return None


def search_bing(query, count=30):
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={count}"
    try:
        resp = http_get(url, timeout=12)
        if resp and resp.status_code == 200:
            return extract_domains_from_search(resp.text, 'bing')
    except Exception as e:
        log.info(f"    Bing error: {e}")
    return OrderedDict()


def search_baidu(query, count=20):
    url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}&rn={count}"
    try:
        resp = http_get(url, timeout=12)
        if resp and resp.status_code == 200 and len(resp.text) > 500:
            return extract_domains_from_search(resp.text, 'baidu')
    except Exception:
        pass
    return OrderedDict()


def search_google(query, count=10):
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num={count}&hl=zh-CN"
    try:
        h = {**HEADERS, 'Accept-Language': 'zh-CN,zh;q=0.9'}
        resp = requests.get(url, timeout=12, headers=h, allow_redirects=True)
        if resp and resp.status_code == 200:
            return extract_domains_from_search(resp.text, 'google')
    except Exception:
        pass
    return OrderedDict()


class CandidatePool:
    def __init__(self):
        self.pool = OrderedDict()
        self.existing = set()
        self._load_existing()

    def _load_existing(self):
        try:
            with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for rs in data.get('rulesets', []):
                for r in rs.get('rules', []):
                    d = normalize_domain(r['site']['origin'])
                    self.existing.add(d)
        except Exception:
            pass

    def add(self, domain, info):
        if domain in self.existing or domain in SKIP_DOMAINS:
            return False
        if domain not in self.pool:
            self.pool[domain] = info
            return True
        else:
            existing = self.pool[domain]
            if 'strategies' not in existing:
                existing['strategies'] = [existing.get('strategy', '')]
            existing['strategies'].append(info.get('strategy', ''))
            existing['priority'] = min(existing.get('priority', 5), info.get('priority', 5))
            return False

    def save(self):
        with open(CANDIDATES_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'total': len(self.pool),
                'candidates': list(self.pool.values()),
            }, f, indent=2, ensure_ascii=False)


def s1_brand_resurrection(pool):
    log.info("\n" + "=" * 60)
    log.info("  S1: BRAND RESURRECTION — 品牌复活")
    log.info("=" * 60)

    for brand, info in BRAND_REGISTRY.items():
        log.info(f"\n  Brand: {brand}")
        names = info['names']

        # Check publish pages first
        for pp in info.get('publish_pages', []):
            resp = http_get(pp, timeout=8)
            if resp and resp.status_code == 200 and not is_parking(resp.text):
                d = normalize_domain(pp)
                if d:
                    pool.add(d, {
                        'domain': d, 'url': pp, 'brand': brand,
                        'strategy': 's1-publish-page', 'priority': 1,
                        'title': BeautifulSoup(resp.text, 'lxml').title.string.strip()[:60] if BeautifulSoup(resp.text, 'lxml').title else ''
                    })
                    log.info(f"    Publish page OK: {pp}")

        # Search for new domains
        for name in names:
            for kw in SEARCH_KEYWORDS_S1[:3]:
                query = f"{name} {kw}"
                domains = search_bing(query, 20)
                for d, di in domains.items():
                    pool.add(d, {
                        'domain': d, 'url': di['url'], 'brand': brand,
                        'strategy': f's1-bing:{query}', 'priority': 1, 'title': di.get('title', '')
                    })
                time.sleep(0.5)
            time.sleep(0.5)

    log.info(f"  S1 total candidates: {len(pool.pool)}")


def s2_search_engine_discovery(pool):
    log.info("\n" + "=" * 60)
    log.info("  S2: SEARCH ENGINE DISCOVERY — 搜索引擎发现")
    log.info("=" * 60)

    for kw in SEARCH_KEYWORDS_S2:
        log.info(f"  Keyword: {kw}")

        domains = search_bing(kw, 20)
        new = 0
        for d, di in domains.items():
            if pool.add(d, {
                'domain': d, 'url': di['url'], 'strategy': f's2-bing:{kw}', 'priority': 2, 'title': di.get('title', '')
            }):
                new += 1
        log.info(f"    Bing: {len(domains)} domains, {new} new")
        time.sleep(0.8)

        domains = search_baidu(kw, 20)
        new = 0
        for d, di in domains.items():
            if pool.add(d, {
                'domain': d, 'url': di['url'], 'strategy': f's2-baidu:{kw}', 'priority': 2, 'title': di.get('title', '')
            }):
                new += 1
        if new:
            log.info(f"    Baidu: {new} new")
        time.sleep(0.8)

    log.info(f"  S2 total candidates: {len(pool.pool)}")


def s3_navsite_deep_crawl(pool):
    log.info("\n" + "=" * 60)
    log.info("  S3: NAVSITE DEEP CRAWL — 导航站深度爬取")
    log.info("=" * 60)

    nav_seeds = [
        'https://www.ezhentang.com',
        'https://www.cilihezi.top',
        'https://cilihezi.com',
        'https://www.xddh.cn',
        'https://www.wawadh.cn',
    ]

    for kw in SEARCH_KEYWORDS_S3[:5]:
        domains = search_bing(kw, 20)
        for d, di in domains.items():
            if d not in SKIP_DOMAINS:
                nav_seeds.append(di['url'])
        time.sleep(0.8)

    nav_seeds = list(dict.fromkeys(nav_seeds))
    log.info(f"  Nav seeds: {len(nav_seeds)}")

    visited = set()
    queue = list(nav_seeds)
    depth_0 = list(nav_seeds)

    while queue:
        url = queue.pop(0)
        d = normalize_domain(url)
        if not d or d in visited:
            continue
        visited.add(d)

        log.info(f"  Crawling: {url}")
        resp = http_get(url, timeout=10)
        if not resp or resp.status_code != 200:
            continue
        if is_parking(resp.text):
            continue

        links = extract_all_links(resp.text, url)
        log.info(f"    Found {len(links)} links")

        for link in links:
            ld = normalize_domain(link)
            if not ld:
                continue

            if has_torrent_keywords(resp.text) and ld not in [normalize_domain(u) for u in depth_0]:
                pool.add(ld, {
                    'domain': ld, 'url': link,
                    'strategy': f's3-nav:{d}', 'priority': 2,
                    'title': ''
                })

            if ld not in visited and len(visited) < 50:
                nav_lower = link.lower()
                if any(kw in nav_lower for kw in ['导航', 'nav', '大全', 'directory', 'hao123', 'dh']):
                    queue.append(link)

        time.sleep(0.5)

    log.info(f"  S3 total candidates: {len(pool.pool)}")


def s4_forum_community(pool):
    log.info("\n" + "=" * 60)
    log.info("  S4: FORUM/COMMUNITY — 论坛社区发现")
    log.info("=" * 60)

    for kw in SEARCH_KEYWORDS_S4:
        domains = search_bing(kw, 15)
        new = 0
        for d, di in domains.items():
            if pool.add(d, {
                'domain': d, 'url': di['url'], 'strategy': f's4-bing:{kw}', 'priority': 3, 'title': di.get('title', '')
            }):
                new += 1
        if new:
            log.info(f"  '{kw}': {new} new")
        time.sleep(0.8)

    forum_urls = [
        'https://www.52pojie.cn',
        'https://www.v2ex.com',
        'https://www.reddit.com/r/torrents',
        'https://www.reddit.com/r/megalinks',
    ]
    for url in forum_urls:
        resp = http_get(url, timeout=10)
        if resp and resp.status_code == 200:
            links = extract_all_links(resp.text, url)
            for link in links:
                ld = normalize_domain(link)
                if ld:
                    pool.add(ld, {
                        'domain': ld, 'url': link,
                        'strategy': f's4-forum:{normalize_domain(url)}', 'priority': 3, 'title': ''
                    })

    log.info(f"  S4 total candidates: {len(pool.pool)}")


def s5_dht_variants(pool):
    log.info("\n" + "=" * 60)
    log.info("  S5: DHT INDEX VARIANTS — DHT索引站域名变体")
    log.info("=" * 60)

    dht_brands = {
        'btsow': ['btsow.pics', 'btsow.one', 'btsow.cc', 'btsow.fun', 'btsow.life', 'btsow.xyz', 'btsow.live', 'btsow.app'],
        'torlock': ['torlock.com', 'torlock.info', 'torlock.xyz', 'torlock.cc'],
        'torrentkitty': ['torrentkitty.red', 'torrentkitty.net', 'torrentkitty.org', 'torrentkitty.se'],
        'magnetdl': ['magnetdl.com', 'magnetdl.org', 'magnetdl.net', 'magnetdl.cc'],
        'idope': ['idope.se', 'idope.site', 'idope.cc', 'idope.xyz'],
        'snowfl': ['snowfl.com', 'snowfl.xyz', 'snowfl.cc'],
        'bt4g': ['bt4g.org', 'bt4g.pr0x.org', 'bt4g.cc', 'bt4g.xyz'],
        'btdigg': ['btdigg.org', 'btdigg.cc', 'btdigg.xyz'],
        'torrentz2': ['torrentz2eu.org', 'torrentz2.is', 'torrentz2.nz'],
    }

    for brand, variants in dht_brands.items():
        for v in variants:
            d = normalize_domain(v)
            if d and d not in pool.existing:
                resp = http_get(f'https://{v}', timeout=5)
                if resp and resp.status_code == 200 and not is_parking(resp.text):
                    pool.add(d, {
                        'domain': d, 'url': f'https://{v}', 'brand': brand,
                        'strategy': 's5-variant', 'priority': 2, 'title': ''
                    })
                    log.info(f"    OK: {v}")
                elif resp and resp.status_code == 200:
                    pass
            time.sleep(0.2)

    log.info(f"  S5 total candidates: {len(pool.pool)}")


def s6_publish_pages(pool):
    log.info("\n" + "=" * 60)
    log.info("  S6: PUBLISH PAGE DISCOVERY — 域名发布页发现")
    log.info("=" * 60)

    publish_queries = [
        'javbus 最新地址 发布页', 'btsow 最新地址', '磁力猫 最新网址',
        'torrentkitty 最新地址', 'nyaa 最新域名', 'nyaa镜像',
        'thepiratebay 镜像 最新', '1337x 镜像 proxy',
        'rarbg proxy mirror 最新', 'yts 镜像 proxy',
        'kickass proxy 最新', 'eztv proxy mirror',
        'extratorrent proxy 镜像', 'limetorrents proxy',
        'solidtorrents mirror', 'torrentgalaxy proxy',
        'magnetdl proxy mirror', 'idope proxy',
        '磁力搜索 发布页 2026', '磁力网站 网址发布',
        'bt搜索 最新网址 发布', 'torrent proxy list 2026',
        'unblock torrent site', 'torrent mirror sites',
        '磁力搜 官方地址', '磁力狗 最新入口',
    ]

    for q in publish_queries:
        domains = search_bing(q, 20)
        new = 0
        for d, di in domains.items():
            if pool.add(d, {
                'domain': d, 'url': di['url'], 'strategy': f's6-bing:{q}', 'priority': 1, 'title': di.get('title', '')
            }):
                new += 1
        if new:
            log.info(f"  '{q[:30]}': {new} new")
        time.sleep(0.8)

    log.info(f"  S6 total candidates: {len(pool.pool)}")


def quick_verify(domain_info):
    url = domain_info.get('url', f"https://{domain_info['domain']}")
    domain = domain_info['domain']

    resp = http_get(url, timeout=8)
    if not resp:
        return {'pass': False, 'reason': 'connection failed'}
    if resp.status_code != 200:
        return {'pass': False, 'reason': f'HTTP {resp.status_code}'}
    if is_parking(resp.text):
        return {'pass': False, 'reason': 'parking page'}
    if len(resp.text) < 200:
        return {'pass': False, 'reason': 'page too small'}

    title = ''
    soup = BeautifulSoup(resp.text, 'lxml')
    if soup.title and soup.title.string:
        title = soup.title.string.strip()[:60]

    has_tk = has_torrent_keywords(resp.text)

    for bait in ['Big Buck Bunny', 'Inception', 'One Piece']:
        for sp in ['/search?q={q}', '/search/{q}', '/?q={q}', '/?s={q}', '/search?query={q}']:
            test_url = url.rstrip('/') + sp.replace('{q}', urllib.parse.quote(bait))
            try:
                r2 = http_get(test_url, timeout=8)
                if r2 and r2.status_code == 200 and len(r2.text) > 200:
                    magnets = extract_magnets_from_html(r2.text, url)
                    if magnets:
                        return {
                            'pass': True, 'magnets': len(magnets), 'path': sp,
                            'bait': bait, 'title': title, 'has_torrent_kw': has_tk,
                            'sample': magnets[0].get('title', '')[:60],
                        }
            except Exception:
                pass
        time.sleep(0.2)

    return {'pass': False, 'reason': 'no magnets via HTTP', 'title': title, 'has_torrent_kw': has_tk}


def verify_all(pool):
    log.info("\n" + "=" * 60)
    log.info("  VERIFICATION: Quick HTTP Verify All Candidates")
    log.info("=" * 60)

    items = list(pool.pool.values())
    total = len(items)
    verified = []
    needs_selenium = []

    for i, info in enumerate(items):
        domain = info['domain']
        log.info(f"\n[{i+1}/{total}] {domain} (from {info.get('strategy', '?')})")

        r = quick_verify(info)
        info['verify_result'] = r

        if r.get('pass'):
            log.info(f"  OK: {r['magnets']} magnets path={r['path']} bait={r['bait']}")
            verified.append(info)
        elif r.get('has_torrent_kw'):
            log.info(f"  NEEDS SELENIUM: {r.get('reason', '')} title={r.get('title', '')}")
            needs_selenium.append(info)
        else:
            log.info(f"  FAIL: {r.get('reason', '')}")

        time.sleep(0.2)

    return verified, needs_selenium


def selenium_verify(candidates):
    if not candidates:
        return []

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    log.info(f"\n  Selenium verify: {len(candidates)} candidates")

    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(20)

    verified = []
    for i, info in enumerate(candidates):
        url = info.get('url', f"https://{info['domain']}")
        log.info(f"\n  [{i+1}/{len(candidates)}] {info['domain']}")

        for bait in ['Big Buck Bunny', 'Inception']:
            for sp in ['/search/{q}', '/search?q={q}', '/?q={q}']:
                test_url = url.rstrip('/') + sp.replace('{q}', urllib.parse.quote(bait))
                try:
                    driver.get(test_url)
                    time.sleep(5)
                    html = driver.page_source
                    magnets = extract_magnets_from_html(html, url)
                    if magnets:
                        log.info(f"    OK: {len(magnets)} magnets (Selenium)")
                        info['verify_result'] = {'pass': True, 'magnets': len(magnets), 'path': sp, 'bait': bait, 'requires_browser': True}
                        verified.append(info)
                        break
                    hashes = set()
                    for m in HASH_RE.finditer(BeautifulSoup(html, 'lxml').get_text()):
                        hashes.add(m.group(0).upper())
                    if len(hashes) >= 2:
                        log.info(f"    OK: {len(hashes)} hashes (Selenium)")
                        info['verify_result'] = {'pass': True, 'magnets': len(hashes), 'path': sp, 'bait': bait, 'requires_browser': True}
                        verified.append(info)
                        break
                except Exception:
                    pass
            if info.get('verify_result', {}).get('pass'):
                break
        time.sleep(0.5)

    driver.quit()
    return verified


def add_to_sources(verified, pool):
    if not verified:
        return 0

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    ruleset = data['rulesets'][0]
    added = 0
    for info in verified:
        d = info['domain']
        if d in pool.existing:
            continue
        pool.existing.add(d)

        vr = info.get('verify_result', {})
        rule_id = hashlib.md5(info['url'].encode()).hexdigest()[:12]
        rule = {
            'id': rule_id,
            'site': {'name': d, 'origin': info['url'].rstrip('/')},
            'capabilities': {'supports_search': True, 'supports_detail': False},
            'search': {
                'request_template': vr.get('path', '/search?q={query}'),
                'timeout_ms': 15000,
                'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                'requires_waf_bypass': False,
                'requires_browser': vr.get('requires_browser', False),
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
                'magnets_found': vr.get('magnets', 0),
                'sample_title': vr.get('sample', ''),
            },
        }

        brand = info.get('brand', '')
        if brand:
            rule['site']['brand'] = brand

        ruleset['rules'].append(rule)
        added += 1
        log.info(f"  Added: {d} ({vr.get('magnets', 0)} magnets)")

    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
    data['generated_at'] = datetime.now(timezone.utc).isoformat()

    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return added


def main():
    log.info("=" * 70)
    log.info("  MEGA HUNTER v1 — 多策略源发现引擎")
    log.info("=" * 70)

    pool = CandidatePool()
    log.info(f"  Existing sources: {len(pool.existing)}")

    s1_brand_resurrection(pool)
    s2_search_engine_discovery(pool)
    s3_navsite_deep_crawl(pool)
    s4_forum_community(pool)
    s5_dht_variants(pool)
    s6_publish_pages(pool)

    log.info(f"\n  TOTAL unique candidates: {len(pool.pool)}")

    pool.save()
    log.info(f"  Candidates saved to {CANDIDATES_FILE}")

    verified_http, needs_selenium = verify_all(pool)
    log.info(f"\n  HTTP verified: {len(verified_http)}")
    log.info(f"  Needs Selenium: {len(needs_selenium)}")

    verified_se = selenium_verify(needs_selenium)
    log.info(f"  Selenium verified: {len(verified_se)}")

    all_verified = verified_http + verified_se

    log.info("\n" + "=" * 70)
    log.info("  FINAL RESULTS")
    log.info("=" * 70)
    log.info(f"  Total candidates discovered: {len(pool.pool)}")
    log.info(f"  Verified new sources: {len(all_verified)}")
    for v in all_verified:
        vr = v.get('verify_result', {})
        log.info(f"    + {v['domain']:25s} {vr.get('magnets', 0):3d} magnets {v.get('strategy', '')[:30]}")

    added = add_to_sources(all_verified, pool)
    log.info(f"\n  {added} new sources added to sources.json")
    log.info("=" * 70)


if __name__ == '__main__':
    main()
