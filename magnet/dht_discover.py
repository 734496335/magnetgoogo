#!/usr/bin/env python3
"""
DHT Source Discovery — 通过 DHT 热门资源反向发现磁力源
=======================================================

思路:
  1. 从已有 green 源搜索热门关键词，收集真实 info_hash + 文件名
  2. 用搜索引擎 (Bing) 搜索这些 hash / 文件名
  3. 从搜索结果中提取收录了这些资源的域名
  4. 去重已知源，过滤无效域名 (CDN/社交/论坛等)
  5. 对新域名批量探测搜索接口
  6. 输出可用源报告
"""

import json, os, sys, re, time, hashlib, logging, urllib.parse, random
from datetime import datetime, timezone
from collections import Counter

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('dht_discover.log', encoding='utf-8', mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

HASH_RE = re.compile(r'\b[0-9A-Fa-f]{40}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:([0-9A-Fa-f]{32,40})', re.I)

# ── Phase 1: Bait queries to harvest real hashes from existing sources ──

HARVEST_QUERIES = [
    # Movies — recent & popular
    'Dune Part Two', 'Oppenheimer', 'Deadpool Wolverine',
    # Anime — currently airing / popular
    'One Piece 1100', 'Jujutsu Kaisen', 'Frieren',
    # TV
    'Shogun 2024', 'The Penguin',
    # Games
    'Black Myth Wukong', 'Elden Ring DLC',
    # XXX — common codes
    'SSIS-900', 'ABP-500', 'SDDE-720',
    # CN
    '庆余年2', '三体',
    # Software
    'Ubuntu 24.04',
]

# Domains to always ignore (not magnet sites)
IGNORE_DOMAINS = {
    # Search engines
    'google.com', 'bing.com', 'yahoo.com', 'baidu.com', 'sogou.com',
    'duckduckgo.com', 'yandex.ru', 'yandex.com', 'so.com', '360.cn',
    # Social / forums / content
    'reddit.com', 'twitter.com', 'x.com', 'facebook.com', 'instagram.com',
    'youtube.com', 'bilibili.com', 'douban.com', 'zhihu.com', 'tieba.baidu.com',
    'quora.com', 'pinterest.com', 'tumblr.com', 'weibo.com', 'tiktok.com',
    'mp.weixin.qq.com', 'weixin.qq.com', 'qq.com', 'ima.qq.com',
    # Wiki / docs / code
    'wikipedia.org', 'wikimedia.org', 'fandom.com',
    'github.com', 'gitlab.com', 'gitee.com', 'stackoverflow.com',
    'blog.csdn.net', 'csdn.net', 'cnblogs.com', 'jianshu.com',
    # CDN / infra / mirrors
    'cloudflare.com', 'amazonaws.com', 'microsoft.com', 'apple.com',
    'mirrors.aliyun.com', 'mirrors.sjtug.sjtu.edu.cn', 'mirrors.cqupt.edu.cn',
    'nodejs.org', 'php.net', 'pkg.oracle.com',
    # Government / institutions
    'gov.cn', 'miit.gov.cn', 'mps.gov.cn', 'edu.cn',
    # Generic non-magnet
    'imdb.com', 'rottentomatoes.com', 'metacritic.com',
    'archive.org', 'steamdb.info', 'hao123.com',
    # Chinese non-magnet
    'iqiyi.com', 'youku.com', 'mgtv.com', 'v.qq.com',
    'ali213.net', 'magnetvideo.com', 'cnysmagnet.com',
    'gloriousmag.com.cn', 'umag.com.cn', '7mag.net',
    'pastebin.com', 'testredirect.com',
}


def normalize_domain(url):
    """Extract clean domain from URL."""
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        p = urllib.parse.urlparse(url)
        d = p.netloc.lower()
        if ':' in d:
            d = d.split(':')[0]
        if d.startswith('www.'):
            d = d[4:]
        return d
    except:
        return ''


def load_existing_domains():
    """Load all domains already in sources.json."""
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    domains = set()
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            origin = r.get('site', {}).get('origin', '')
            d = normalize_domain(origin)
            if d:
                domains.add(d)
    return domains, data


def is_ignorable(domain):
    """Check if domain should be skipped."""
    for ig in IGNORE_DOMAINS:
        if domain == ig or domain.endswith('.' + ig):
            return True
    # Skip very short domains (likely CDN subdomains)
    if len(domain) < 5:
        return True
    # Skip common non-search patterns
    if any(x in domain for x in ['cdn.', 'api.', 'static.', 'img.', 'dl.']):
        return True
    return False


# ── Phase 1: Harvest hashes from our own green sources ──

def harvest_hashes_from_sources(data, max_queries=8):
    """Search our own green sources to collect real info_hashes and file names."""
    green_rules = []
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            if r.get('health', {}).get('status') == 'green':
                green_rules.append(r)

    if not green_rules:
        log.warning("  No green sources found!")
        return []

    log.info(f"  Found {len(green_rules)} green sources")

    # Pick a few sources to harvest from
    harvest_sources = random.sample(green_rules, min(5, len(green_rules)))
    queries = random.sample(HARVEST_QUERIES, min(max_queries, len(HARVEST_QUERIES)))

    collected = []  # list of {'hash': ..., 'title': ...}

    for rule in harvest_sources:
        origin = rule['site']['origin']
        tmpl = rule.get('search', {}).get('request_template', '/search?q={query}')
        name = rule['site'].get('name', origin)

        for query in queries[:3]:  # 3 queries per source
            url = origin.rstrip('/') + tmpl.replace('{query}', urllib.parse.quote(query))
            # Handle {query_b64}
            if '{query_b64}' in url:
                import base64
                url = url.replace('{query_b64}', base64.b64encode(query.encode()).decode())

            try:
                resp = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
                if resp.status_code != 200:
                    continue

                # Extract magnet hashes from the page
                for m in MAGNET_RE.finditer(resp.text):
                    h = m.group(1).upper()
                    if len(h) == 40:
                        collected.append({'hash': h, 'query': query})

                # Also extract titles near magnet links
                soup = BeautifulSoup(resp.text, 'html.parser')
                for a in soup.find_all('a', href=lambda h: h and 'magnet:' in h):
                    href = a['href']
                    hm = re.search(r'btih:([0-9A-Fa-f]{40})', href, re.I)
                    if hm:
                        # Try to find title
                        title = ''
                        parent = a.parent
                        for _ in range(3):
                            if parent:
                                for ta in parent.find_all('a', href=True):
                                    txt = ta.get_text(strip=True)
                                    if txt and len(txt) > 5 and 'magnet:' not in ta['href']:
                                        title = txt[:120]
                                        break
                                if title:
                                    break
                                parent = parent.parent
                        if not title:
                            title = a.get_text(strip=True)[:120]
                        if title:
                            collected.append({
                                'hash': hm.group(1).upper(),
                                'title': title,
                                'query': query,
                            })

                log.info(f"    {name} / '{query}' → {len(MAGNET_RE.findall(resp.text))} hashes")
            except Exception as e:
                log.info(f"    {name} / '{query}' → error: {e}")
                continue

            time.sleep(0.5)

    # Deduplicate by hash
    seen = set()
    unique = []
    for item in collected:
        if item['hash'] not in seen:
            seen.add(item['hash'])
            unique.append(item)

    log.info(f"  Harvested {len(unique)} unique hashes from green sources")
    return unique


# ── Phase 2: Search engines to find sites that index these hashes ──

def search_google(query, count=30):
    """Scrape Google search results."""
    urls = []
    try:
        search_url = f'https://www.google.com/search?q={urllib.parse.quote(query)}&num={count}'
        resp = requests.get(search_url, timeout=15, headers={
            **HEADERS,
            'Accept': 'text/html,application/xhtml+xml',
        }, allow_redirects=True)
        if resp.status_code != 200:
            log.info(f"    Google HTTP {resp.status_code}")
            return urls
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/url?q=' in href:
                m = re.search(r'/url\?q=([^&]+)', href)
                if m:
                    real_url = urllib.parse.unquote(m.group(1))
                    if real_url.startswith(('http://', 'https://')):
                        urls.append(real_url)
            elif href.startswith(('http://', 'https://')) and 'google.' not in href:
                urls.append(href)
        log.info(f"    Google: {len(urls)} raw URLs")
    except Exception as e:
        log.info(f"    Google error: {e}")
    return urls


def search_bing(query, count=30):
    """Search Bing international."""
    urls = []
    try:
        search_url = f'https://www.bing.com/search?q={urllib.parse.quote(query)}&count={count}'
        resp = requests.get(search_url, timeout=15, headers={
            **HEADERS,
            'Accept': 'text/html,application/xhtml+xml',
        }, allow_redirects=True)
        if resp.status_code != 200:
            log.info(f"    Bing HTTP {resp.status_code}")
            return urls
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Bing results in <li class="b_algo">
        for li in soup.find_all('li', class_='b_algo'):
            a = li.find('a', href=True)
            if a:
                href = a['href']
                if href.startswith(('http://', 'https://')):
                    urls.append(href)
        # Fallback
        if len(urls) < 3:
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith(('http://', 'https://')) and 'bing.com' not in href and 'microsoft.com' not in href:
                    urls.append(href)
        log.info(f"    Bing: {len(urls)} raw URLs")
    except Exception as e:
        log.info(f"    Bing error: {e}")
    return urls


def search_duckduckgo(query, count=30):
    """Search DuckDuckGo HTML version."""
    urls = []
    try:
        search_url = f'https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}'
        resp = requests.get(search_url, timeout=15, headers={
            **HEADERS,
            'Accept': 'text/html,application/xhtml+xml',
        }, allow_redirects=True)
        if resp.status_code != 200:
            log.info(f"    DDG HTTP {resp.status_code}")
            return urls
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.find_all('a', class_='result__a', href=True):
            href = a['href']
            # DDG wraps URLs in //duckduckgo.com/l/?uddg=...
            if 'uddg=' in href:
                m = re.search(r'uddg=([^&]+)', href)
                if m:
                    real_url = urllib.parse.unquote(m.group(1))
                    if real_url.startswith(('http://', 'https://')):
                        urls.append(real_url)
            elif href.startswith(('http://', 'https://')):
                urls.append(href)
        log.info(f"    DDG: {len(urls)} raw URLs")
    except Exception as e:
        log.info(f"    DDG error: {e}")
    return urls


def discover_domains_from_hashes(harvested, existing_domains, max_searches=20):
    """Search for harvested hashes/titles in search engines, extract new domains."""
    domain_counter = Counter()  # domain → how many times seen
    domain_urls = {}  # domain → sample URL

    # Strategy: use resource titles + torrent keywords (NOT raw hashes)
    # Raw hashes return hash-tool sites, not magnet indexers.
    searches = []

    # A) Title-based: "resource_title" torrent magnet download
    titles_seen = set()
    for item in harvested:
        title = item.get('title', item.get('query', ''))
        if not title or title in titles_seen or len(title) < 5:
            continue
        titles_seen.add(title)
        clean = re.sub(r'[^\w\s\-.]', '', title)[:50].strip()
        if clean:
            searches.append(('title', f'"{clean}" torrent magnet download'))
        if len(searches) >= max_searches // 2:
            break

    # B) Site-discovery: queries that find magnet search engines themselves
    site_discovery = [
        'magnet search engine torrent',
        'best torrent search sites 2024',
        'torrent index magnet links',
        'DHT torrent search engine',
        'magnet link search site',
        'alternative torrent search engine',
        'torrent metasearch magnet',
        'BT磁力搜索引擎 推荐',
    ]
    for q in site_discovery:
        searches.append(('discovery', q))

    searches = searches[:max_searches]
    log.info(f"  Prepared {len(searches)} search queries")

    for i, (stype, query) in enumerate(searches):
        log.info(f"\n  [{i+1}/{len(searches)}] [{stype}] Searching: {query[:80]}")

        result_urls = []
        result_urls.extend(search_google(query))
        time.sleep(2)
        result_urls.extend(search_bing(query))
        time.sleep(2)
        result_urls.extend(search_duckduckgo(query))

        for url in result_urls:
            d = normalize_domain(url)
            if not d:
                continue
            if d in existing_domains:
                continue
            if is_ignorable(d):
                continue
            domain_counter[d] += 1
            if d not in domain_urls:
                domain_urls[d] = url

        log.info(f"    Total {len(result_urls)} URLs → {len(domain_counter)} unique new domains so far")
        time.sleep(random.uniform(2, 4))  # Rate limit

    return domain_counter, domain_urls


# ── Phase 2b: Scrape recommendation articles for torrent site links ──

# Curated list of "best torrent sites" articles (these articles LIST real sites)
RECOMMENDATION_ARTICLES = [
    'https://www.privacysavvy.com/security/torrents/best-torrent-search-engines/',
    'https://www.techworm.net/2018/10/best-torrent-search-engine.html',
    'https://beencrypted.com/privacy/torrenting/best-torrent-search-engines/',
    'https://techpp.com/2024/01/torrent-search-engines/',
    'https://troypoint.com/best-torrent-search-engines/',
    'https://www.techcult.com/best-torrent-search-engine/',
    'https://torrentfreak.com/top-torrent-sites/',
    'https://vpnmentor.com/blog/10-best-torrent-search-engines/',
    'https://www.fossbytes.com/best-torrent-sites/',
    'https://www.vpncentral.com/best-torrent-search-engines/',
]

# Known torrent/magnet domains to seed probing (not yet in sources.json)
SEED_DOMAINS = [
    # Major international torrent indexes
    'torrentz2.eu', 'torrentz2.is', 'torrentgalaxy.to', 'torrentgalaxy.mx',
    'solidtorrents.to', 'solidtorrents.net', 'bt4gprx.com', 'bt4g.org',
    'bitsearch.to', 'torrends.to', 'snowfl.com',
    'idope.se', 'torrentdownload.info', 'torrentdownloads.pro',
    'yourbittorrent.com', 'limetorrents.lol', 'limetorrents.info',
    'glodls.to', 'magnetdl.com', 'magnetdl.hair',
    'torlock.com', 'torlock2.com',
    'btdig.com', 'btmet.com',
    '1337x.to', '1337x.st', '1337x.gd', '1337xx.to',
    'ettv.be', 'ettv.to', 'eztv.re', 'eztv.wf',
    # Anime
    'nyaa.si', 'nyaa.land', 'anidex.info', 'animelayer.ru',
    'tokyotosho.info', 'animetosho.org', 'acg.rip', 'bangumi.moe',
    # Chinese
    'ciliso.com', 'cilimo.com', 'clm15.xyz', 'clm66.xyz',
    'eciliso.com', 'ciliss.com', 'ciliwang.net',
    'btmao.cc', 'btmao1.com', 'btsow.click', 'btsow.motorcycles',
    'cilidog.com', 'cili001.com', 'cilibaba.com',
    'sukebto.com', 'sobt.org', 'diancili.com',
    # DHT search
    'btdig.com', 'btmet.com', 'btdb.eu',
    'bthash.cc', 'infohash.org',
    # Proxies/mirrors
    'piratebay.party', 'thepiratebay.zone', 'tpb.party',
    'rarbg.to', 'rarbggo.to', 'rarbgmirror.com',
    # Multi-purpose
    'rutracker.org', 'nnmclub.to',
    'torrentfunk2.com', 'torrentfunk.com',
    'zooqle.com', 'zooqle.skin',
    'xtorx.com', '1337xxx.to',
    'torrentquest.com', 'torrentscsv.com',
    'academictorrents.com',
]


def scrape_articles_for_domains(existing_domains):
    """Scrape recommendation articles and extract outbound links to torrent sites."""
    domain_counter = Counter()
    domain_urls = {}

    for article_url in RECOMMENDATION_ARTICLES:
        log.info(f"  Scraping: {article_url[:70]}")
        try:
            resp = requests.get(article_url, timeout=15, headers=HEADERS, allow_redirects=True)
            if resp.status_code != 200:
                log.info(f"    HTTP {resp.status_code}, skipping")
                continue
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Extract all outbound links
            for a in soup.find_all('a', href=True):
                href = a['href']
                if not href.startswith(('http://', 'https://')):
                    continue
                d = normalize_domain(href)
                if not d:
                    continue
                if d in existing_domains:
                    continue
                if is_ignorable(d):
                    continue
                # Filter out the article host itself
                article_domain = normalize_domain(article_url)
                if d == article_domain:
                    continue
                domain_counter[d] += 1
                if d not in domain_urls:
                    domain_urls[d] = href
            log.info(f"    Found {len(domain_counter)} unique new domains so far")
        except Exception as e:
            log.info(f"    Error: {str(e)[:60]}")
        time.sleep(2)

    return domain_counter, domain_urls


def add_seed_domains(domain_counter, domain_urls, existing_domains):
    """Add well-known torrent domains for probing."""
    for d in SEED_DOMAINS:
        if d not in existing_domains and not is_ignorable(d):
            domain_counter[d] += 5  # High weight — known sites
            if d not in domain_urls:
                domain_urls[d] = f'https://{d}'
    return domain_counter, domain_urls


# ── Phase 3: Probe discovered domains ──

def extract_magnets_from_html(html):
    """Extract magnet links from HTML."""
    magnets = []
    seen = set()
    for m in MAGNET_RE.finditer(html):
        h = m.group(1).upper()
        if h not in seen:
            seen.add(h)
            magnets.append(h)
    return magnets


def probe_domain(domain, sample_url, timeout=25):
    """Probe a domain to see if it's a usable magnet search site."""
    result = {
        'domain': domain,
        'sample_url': sample_url,
        'status': 'unknown',
        'magnets_found': 0,
        'working_path': None,
        'has_search': False,
    }

    base_url = f'https://{domain}'

    # Step 1: Can we reach the homepage? (with retry)
    resp = None
    for attempt in range(2):
        try:
            resp = requests.get(base_url, timeout=timeout, headers=HEADERS, allow_redirects=True)
            result['http_status'] = resp.status_code
            result['final_domain'] = normalize_domain(resp.url)
            if resp.status_code == 200:
                break
            if resp.status_code == 403:
                result['status'] = 'unreachable'
                result['reason'] = f'HTTP {resp.status_code}'
                return result
            # Try http fallback
            resp = requests.get(f'http://{domain}', timeout=timeout, headers=HEADERS, allow_redirects=True)
            if resp.status_code == 200:
                base_url = f'http://{domain}'
                break
            result['status'] = 'unreachable'
            result['reason'] = f'HTTP {resp.status_code}'
            return result
        except requests.exceptions.Timeout:
            if attempt == 0:
                time.sleep(2)
                continue
            result['status'] = 'timeout'
            result['reason'] = 'connection timeout'
            return result
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            result['status'] = 'error'
            result['reason'] = str(e)[:80]
            return result
    if resp is None or resp.status_code != 200:
        result['status'] = 'unreachable'
        result['reason'] = 'failed after retries'
        return result

    homepage_html = resp.text

    # Check if it looks like a torrent/magnet site
    magnet_indicators = ['magnet:', 'torrent', 'bt', 'hash', 'download', '磁力', '种子']
    indicator_count = sum(1 for ind in magnet_indicators if ind.lower() in homepage_html.lower())
    if indicator_count < 2:
        result['status'] = 'not_magnet_site'
        result['reason'] = f'Only {indicator_count} magnet indicators on homepage'
        return result

    # Check for search functionality on homepage
    soup = BeautifulSoup(homepage_html, 'html.parser')
    search_forms = soup.find_all('form', action=True)
    search_inputs = soup.find_all('input', attrs={'type': 'search'}) + \
                    soup.find_all('input', attrs={'name': re.compile(r'q|query|search|keyword|wd|s', re.I)})

    # Step 2: Try searching with bait words
    test_queries = ['SSIS-900', 'Inception', 'One Piece']
    search_paths = [
        '/search?q={query}', '/search/{query}', '/?q={query}', '/?s={query}',
        '/search?keyword={query}', '/search.php?q={query}',
        '/search/{query}/1/', '/search?wd={query}',
        '/search-{query}-0-0-1.html',  # 磁力帝 style
    ]

    # If we found forms, try to extract the search path
    for form in search_forms:
        action = form.get('action', '/')
        method = form.get('method', 'get').lower()
        if method == 'get':
            # Find the input name for the query
            for inp in form.find_all('input'):
                name = inp.get('name', '')
                if name and name.lower() in ('q', 'query', 'search', 'keyword', 'wd', 's', 'k', 'word'):
                    path = action.rstrip('/') + f'?{name}={{query}}'
                    if path not in search_paths:
                        search_paths.insert(0, path)  # Priority
                    break

    all_magnets = []
    working_path = None
    used_query = None

    for query in test_queries:
        for sp in search_paths:
            test_url = base_url.rstrip('/') + sp.replace('{query}', urllib.parse.quote(query))
            try:
                resp = requests.get(test_url, timeout=timeout, headers=HEADERS, allow_redirects=True)
            except Exception:
                continue
            if resp.status_code != 200:
                continue

            magnets = extract_magnets_from_html(resp.text)
            if magnets:
                all_magnets = magnets
                working_path = sp
                used_query = query

                # Extract title from first result for reporting
                search_soup = BeautifulSoup(resp.text, 'html.parser')
                sample_title = ''
                for a in search_soup.find_all('a', href=lambda h: h and 'magnet:' in h):
                    parent = a.parent
                    for _ in range(3):
                        if parent:
                            for ta in parent.find_all('a', href=True):
                                txt = ta.get_text(strip=True)
                                if txt and len(txt) > 5 and 'magnet:' not in ta['href']:
                                    sample_title = txt[:120]
                                    break
                            if sample_title:
                                break
                            parent = parent.parent
                result['sample_title'] = sample_title
                break
            time.sleep(0.3)

        if all_magnets:
            break

    if all_magnets:
        result['status'] = 'ok'
        result['magnets_found'] = len(all_magnets)
        result['working_path'] = working_path
        result['has_search'] = True
        result['test_query'] = used_query
        log.info(f"    ✓ OK: {len(all_magnets)} magnets (path={working_path}, query={used_query})")
        if result.get('sample_title'):
            log.info(f"      sample: {result['sample_title'][:80]}")
    else:
        result['status'] = 'no_magnets'
        result['reason'] = 'no working search endpoint found'
        result['has_search'] = bool(search_inputs or search_forms)
        log.info(f"    ✗ No magnets (has_search_form={result['has_search']})")

    return result


# ── Main ──

def main():
    log.info("=" * 70)
    log.info("  DHT SOURCE DISCOVERY v2")
    log.info("  Strategy: Harvest hashes + Article scraping + Seed list → Probe")
    log.info("=" * 70)

    existing_domains, data = load_existing_domains()
    log.info(f"  Existing sources: {len(existing_domains)} domains")

    # ── Phase 1: Harvest real hashes from our green sources ──
    log.info("\n" + "=" * 70)
    log.info("  PHASE 1: Harvesting hashes from green sources")
    log.info("=" * 70)

    harvested = harvest_hashes_from_sources(data, max_queries=10)

    if not harvested:
        log.warning("  No hashes harvested. Using fallback approach with bait queries only.")
        # Fallback: use our bait queries directly in search engines
        harvested = [
            {'hash': 'FALLBACK', 'title': q, 'query': q}
            for q in HARVEST_QUERIES[:10]
        ]

    log.info(f"  Total probes: {len(harvested)}")
    for item in harvested[:10]:
        log.info(f"    {item['hash'][:16]}... title={item.get('title', item.get('query', ''))[:60]}")

    # ── Phase 2: Search engines to discover indexing sites ──
    log.info("\n" + "=" * 70)
    log.info("  PHASE 2: Searching engines for sites that index these resources")
    log.info("=" * 70)

    domain_counter, domain_urls = discover_domains_from_hashes(
        harvested, existing_domains, max_searches=15
    )

    # ── Phase 2b: Scrape recommendation articles ──
    log.info("\n" + "=" * 70)
    log.info("  PHASE 2b: Scraping torrent site recommendation articles")
    log.info("=" * 70)

    article_domains, article_urls = scrape_articles_for_domains(existing_domains)
    # Merge
    for d, c in article_domains.items():
        domain_counter[d] += c
        if d not in domain_urls:
            domain_urls[d] = article_urls.get(d, '')

    # ── Phase 2c: Add seed domains ──
    log.info("\n" + "=" * 70)
    log.info("  PHASE 2c: Adding known torrent site seed list")
    log.info("=" * 70)

    domain_counter, domain_urls = add_seed_domains(domain_counter, domain_urls, existing_domains)
    log.info(f"  Seed list added. Total candidates: {len(domain_counter)}")

    # Sort by frequency (sites seen multiple times are more likely real)
    sorted_domains = domain_counter.most_common()
    log.info(f"\n  Discovered {len(sorted_domains)} unique new domains:")
    for domain, count in sorted_domains[:50]:
        log.info(f"    {domain:40s} seen {count}x  ({domain_urls.get(domain, '')[:60]})")

    # ── Phase 3: Probe discovered domains ──
    log.info("\n" + "=" * 70)
    log.info("  PHASE 3: Probing discovered domains")
    log.info("=" * 70)

    # Probe domains sorted by frequency (most promising first)
    candidates = [(d, c) for d, c in sorted_domains if c >= 1][:50]
    log.info(f"  Probing top {len(candidates)} candidates...")

    probe_results = []
    for i, (domain, count) in enumerate(candidates):
        log.info(f"\n  [{i+1}/{len(candidates)}] {domain} (seen {count}x)")
        r = probe_domain(domain, domain_urls.get(domain, ''))
        r['search_hits'] = count
        probe_results.append(r)
        time.sleep(1)

    # ── Phase 4: Summary ──
    ok = [r for r in probe_results if r['status'] == 'ok']
    potential = [r for r in probe_results if r['status'] == 'no_magnets' and r.get('has_search')]
    failed = [r for r in probe_results if r['status'] not in ('ok', 'no_magnets') or
              (r['status'] == 'no_magnets' and not r.get('has_search'))]

    log.info("\n" + "=" * 70)
    log.info("  DISCOVERY RESULTS")
    log.info("=" * 70)

    log.info(f"\n  ✓ WORKING ({len(ok)}):")
    for r in ok:
        log.info(f"    + {r['domain']:35s} {r['magnets_found']:3d} magnets  path={r['working_path']}")
        if r.get('sample_title'):
            log.info(f"      sample: {r['sample_title'][:80]}")

    log.info(f"\n  ? POTENTIAL — has search form but no magnets found ({len(potential)}):")
    for r in potential:
        log.info(f"    ? {r['domain']:35s} ({r.get('reason', '')})")

    log.info(f"\n  ✗ FAILED ({len(failed)}):")
    for r in failed:
        log.info(f"    - {r['domain']:35s} {r['status']}: {r.get('reason', '')[:50]}")

    # ── Auto-add working sources to sources.json ──
    if ok:
        log.info(f"\n  Adding {len(ok)} new sources to sources.json...")
        ruleset = data['rulesets'][0]
        added = 0
        for r in ok:
            d = r['domain']
            if d in existing_domains:
                continue
            existing_domains.add(d)

            rule_id = hashlib.md5(d.encode()).hexdigest()[:12]
            origin = f'https://{d}'

            rule = {
                'id': rule_id,
                'site': {'name': d, 'origin': origin},
                'capabilities': {'supports_search': True, 'supports_detail': False},
                'search': {
                    'request_template': r['working_path'],
                    'timeout_ms': 15000,
                    'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                    'requires_waf_bypass': False,
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'NEED_MANUAL_CONFIG',
                            'title': 'NEED_MANUAL_CONFIG',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'NEED_MANUAL_CONFIG',
                            'date': 'NEED_MANUAL_CONFIG',
                        }
                    }
                },
                'quality': {'score': 60, 'tags': ['dht-discovered']},
                'health': {
                    'status': 'yellow',
                    'status_detail': 'ok',
                    'last_checked_at': datetime.now(timezone.utc).isoformat(),
                    'magnets_found': r['magnets_found'],
                    'sample_title': r.get('sample_title', ''),
                    'note': f'Auto-discovered via DHT. search_hits={r["search_hits"]}. Selectors need manual config.',
                },
            }
            ruleset['rules'].append(rule)
            added += 1
            log.info(f"    Added: {d} (path={r['working_path']})")

        if added:
            data['meta']['total_rules'] = sum(
                len(rs.get('rules', [])) for rs in data.get('rulesets', [])
            )
            data['generated_at'] = datetime.now(timezone.utc).isoformat()

            with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.info(f"\n  ✓ {added} new sources added. Total: {data['meta']['total_rules']}")
        else:
            log.info(f"\n  No new sources to add (all already exist).")

    # Save full report
    report_file = os.path.join(BASE_DIR, 'dht_discover_report.json')
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'harvested_hashes': len(harvested),
            'domains_discovered': len(sorted_domains),
            'probed': len(probe_results),
            'working': [r for r in probe_results if r['status'] == 'ok'],
            'potential': [r for r in probe_results if r['status'] == 'no_magnets' and r.get('has_search')],
            'all_results': probe_results,
        }, f, indent=2, ensure_ascii=False)
    log.info(f"\n  Full report saved to: {report_file}")
    log.info("=" * 70)


if __name__ == '__main__':
    main()
