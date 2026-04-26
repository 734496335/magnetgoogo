#!/usr/bin/env python3
"""
Smart Source Discovery v2 — 智能源发现器
==========================================
策略A: 百度/Bing 搜索引擎动态发现磁力站
策略B: 从已有可用源的页面中提取友链/外链

三层验证:
  L1 连通性 — HTTP 200 + 非 parking 页
  L2 搜索功能 — 能执行搜索并返回结果
  L3 磁力提取 — 能从搜索结果中提取 magnet: 链接或 40 位 hash

对 JS 渲染站使用 Selenium fallback
"""

import json
import os
import re
import sys
import time
import hashlib
import logging
import urllib.parse
from datetime import datetime, timezone
from collections import OrderedDict

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding='utf-8', mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')
REPORT_FILE = os.path.join(BASE_DIR, '..', 'smart_discover_report.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

TEST_QUERIES_GENERAL = ['Inception', 'Big Buck Bunny', 'Interstellar']
TEST_QUERIES_ANIME = ['One Piece', 'Naruto', 'Dragon Ball']
TEST_QUERIES_CN = ['阿凡达', '战狼', '三体']

SEARCH_KEYWORDS_CN = [
    '磁力搜索', '磁力链接搜索引擎', 'BT种子搜索',
    '磁力猫', '磁力狗', '磁力搜', '磁力下载',
    'BT搜索', '种子搜索', 'torrent搜索引擎',
    'magnet search', 'torrent search engine',
    'best magnet search site 2026',
]

PARKING_KEYWORDS = [
    'domain for sale', 'domain parking', 'buy this domain',
    'this domain is for sale', 'lander', 'sedo', 'parking page',
    '域名出售', '域名交易', '此域名正在出售',
]

NON_SEARCH_DOMAINS = {
    'baidu.com', 'baidu.com', 'bing.com', 'google.com', 'google.com.hk',
    'googleusercontent.com', 'bingj.com', 'microsoft.com',
    'github.com', 'zhihu.com', 'weibo.com', 'douyin.com',
    'bilibili.com', 'youtube.com', 'twitter.com', 'facebook.com',
    'wikipedia.org', 'taobao.com', 'jd.com', 'tmall.com',
    'qq.com', '163.com', 'sina.com.cn', 'sohu.com',
    'toutiao.com', 'csdn.net', 'jianshu.com', 'zhihu.com',
    'apple.com', 'microsoft.com', 'amazon.com',
}

HASH_RE = re.compile(r'[0-9A-Fa-f]{40}')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')


def get_browser_dom(url, wait=6):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument('--headless')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(wait)
        html = driver.page_source
        driver.quit()
        return html
    except Exception as e:
        log.warning(f"    [Browser] Failed: {e}")
        return None


def normalize_domain(url):
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        if not domain or '.' not in domain or len(domain) > 50 or '_' in domain:
            return ''
        if domain.startswith(('javascript:', 'data:', 'mailto:')):
            return ''
        return domain
    except:
        return ''


def extract_links_from_html(html, base_url):
    soup = BeautifulSoup(html, 'lxml')
    links = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if not href or href.startswith(('#', 'javascript:', 'mailto:')):
            continue
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            from urllib.parse import urljoin
            href = urljoin(base_url, href)
        domain = normalize_domain(href)
        if domain and domain not in NON_SEARCH_DOMAINS:
            links.add(href)
    return links


def extract_domains_from_search_results(html):
    soup = BeautifulSoup(html, 'lxml')
    domains = OrderedDict()
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if not href:
            continue

        real_url = href
        if 'baidu.com/link?' in href or 'baidu.com/s?' in href:
            match = re.search(r'[?&]url=([^&]+)', href)
            if match:
                real_url = urllib.parse.unquote(match.group(1))
            else:
                match = re.search(r'[?&]wd=([^&]+)', href)
                if match:
                    continue
                match = re.search(r'/(https?://[^/]+)', href)
                if match:
                    real_url = match.group(1)

        if 'bing.com' in href and 'bing.com/search' not in href:
            if 'bing.com/aclib?' in href or 'bing.com/aclick?' in href:
                continue

        domain = normalize_domain(real_url)
        if domain and domain not in NON_SEARCH_DOMAINS:
            if domain not in domains:
                title = a.get_text(strip=True)[:80]
                domains[domain] = {
                    'url': real_url if real_url.startswith('http') else f'https://{domain}',
                    'title': title,
                    'source_href': href[:100],
                }
    return domains


def is_parking_page(html):
    if not html:
        return False
    lower = html[:5000].lower()
    return any(kw in lower for kw in PARKING_KEYWORDS)


def has_torrent_keywords(html):
    lower = html[:10000].lower()
    return any(kw in lower for kw in ['magnet:', 'torrent', '种子', '磁力', 'btih'])


def _deep_keyword_check(url, html):
    soup = BeautifulSoup(html, 'lxml')
    cn_download_indicators = [
        '下载', 'BT下载', '磁力下载', '迅雷下载', '电驴下载',
        '种子', '磁力链接', 'magnet', 'torrent',
        '影视下载', '高清下载', '电影下载',
    ]
    text = soup.get_text()[:3000]
    found = [kw for kw in cn_download_indicators if kw in text]
    if len(found) >= 2:
        return True
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        txt = a.get_text(strip=True)
        if any(kw in txt for kw in ['下载', '磁力', '种子', 'BT']):
            links.append((href, txt))
        if any(kw in href.lower() for kw in ['download', 'torrent', 'magnet', 'bt']):
            links.append((href, txt))
    if links:
        from urllib.parse import urljoin
        for href, txt in links[:3]:
            full_url = urljoin(url, href)
            if full_url.startswith('http'):
                try:
                    resp = requests.get(full_url, timeout=10, headers=HEADERS, allow_redirects=True)
                    if resp.status_code == 200 and has_torrent_keywords(resp.text):
                        return True
                except Exception:
                    pass
    return False


class SourceProber:
    def __init__(self):
        self.existing_origins = set()
        self.existing_domains = set()
        self._load_existing()

    def _load_existing(self):
        try:
            with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for rs in data.get('rulesets', []):
                for r in rs.get('rules', []):
                    origin = r['site']['origin']
                    self.existing_origins.add(origin)
                    self.existing_domains.add(normalize_domain(origin))
        except Exception as e:
            log.warning(f"Cannot load sources.json: {e}")

    def is_existing(self, domain):
        return domain in self.existing_domains

    def probe_l1(self, url, timeout=12):
        try:
            resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
            if resp.status_code != 200:
                return {'pass': False, 'reason': f'HTTP {resp.status_code}'}
            html = resp.text
            if len(html) < 300:
                return {'pass': False, 'reason': 'page too small'}
            if is_parking_page(html):
                return {'pass': False, 'reason': 'parking page'}
            title = ''
            soup = BeautifulSoup(html, 'lxml')
            if soup.title and soup.title.string:
                title = soup.title.string.strip()[:80]
            return {'pass': True, 'html': html, 'final_url': resp.url, 'title': title}
        except requests.exceptions.Timeout:
            return {'pass': False, 'reason': 'timeout'}
        except requests.exceptions.ConnectionError:
            return {'pass': False, 'reason': 'connection failed'}
        except Exception as e:
            return {'pass': False, 'reason': str(e)[:60]}

    def probe_l2_search(self, url, html=None):
        soup = BeautifulSoup(html, 'lxml') if html else None

        search_paths = self._guess_search_paths(soup, url)

        queries = TEST_QUERIES_GENERAL[:2]

        for search_path in search_paths[:8]:
            for query in queries:
                test_url = url.rstrip('/') + search_path.replace('{query}', urllib.parse.quote(query))
                try:
                    resp = requests.get(test_url, timeout=10, headers=HEADERS, allow_redirects=True)
                except Exception:
                    continue

                if resp.status_code != 200:
                    continue

                result_html = resp.text
                if len(result_html) < 200:
                    continue

                has_magnets, magnet_data = self._extract_magnets(result_html, url)

                if has_magnets:
                    return {
                        'pass': True,
                        'html': result_html,
                        'search_path': search_path,
                        'query': query,
                        'magnets': magnet_data,
                    }

                time.sleep(0.2)

        post_attempts = self._guess_post_searches(soup, url)
        for post_path, body in post_attempts:
            for query in queries[:1]:
                test_url = url.rstrip('/') + post_path
                post_body = {}
                for k, v in body.items():
                    post_body[k] = v.replace('{query}', query) if isinstance(v, str) else v
                try:
                    resp = requests.post(test_url, data=post_body, timeout=10, headers={
                        **HEADERS,
                        'Content-Type': 'application/x-www-form-urlencoded',
                    }, allow_redirects=True)
                    if resp.status_code == 200 and len(resp.text) > 200:
                        has_magnets, magnet_data = self._extract_magnets(resp.text, url)
                        if has_magnets:
                            return {
                                'pass': True,
                                'html': resp.text,
                                'search_path': post_path,
                                'query': query,
                                'magnets': magnet_data,
                                'search_method': 'POST',
                                'search_body': body,
                            }
                except Exception:
                    pass

        return {'pass': False, 'reason': 'no search path produced magnet results via HTTP'}

    def probe_l2_search_browser(self, url, search_path, query):
        test_url = url.rstrip('/') + search_path.replace('{query}', urllib.parse.quote(query))
        log.info(f"    [Browser] Trying: {test_url}")
        html = get_browser_dom(test_url, wait=8)
        if not html:
            return {'pass': False, 'reason': 'browser failed'}

        has_magnets, magnet_data = self._extract_magnets(html, url)
        if has_magnets:
            return {'pass': True, 'html': html, 'magnets': magnet_data}

        return {'pass': False, 'reason': 'browser: no magnets found'}

    def probe_l3_full(self, url, search_path, html=None):
        queries = TEST_QUERIES_GENERAL[:2]
        all_magnets = []

        for query in queries:
            test_url = url.rstrip('/') + search_path.replace('{query}', urllib.parse.quote(query))
            try:
                resp = requests.get(test_url, timeout=15, headers=HEADERS, allow_redirects=True)
                if resp.status_code == 200:
                    found, magnets = self._extract_magnets(resp.text, url)
                    all_magnets.extend(magnets)
            except Exception:
                pass
            time.sleep(0.3)

        return all_magnets

    def _guess_search_paths(self, soup, url):
        paths = []

        if soup:
            forms = soup.find_all('form')
            for form in forms:
                action = form.get('action', '')
                method = form.get('method', 'get').lower()
                inputs = form.find_all('input', {'name': True, 'type': lambda t: t not in ('submit', 'button', 'hidden') if t else True})
                if not inputs:
                    inputs = form.find_all('input', {'name': True})

                if inputs:
                    query_param = inputs[0].get('name', 'q')
                    if action and action != '#':
                        if '?' in action:
                            paths.append(f"{action}&{query_param}={{query}}")
                        else:
                            paths.append(f"{action}?{query_param}={{query}}")
                    else:
                        paths.append(f"/search?{query_param}={{query}}")
                        paths.append(f"/?{query_param}={{query}}")

            search_links = soup.find_all('a', href=re.compile(r'search|find|query|s\?', re.I))
            for a in search_links:
                href = a.get('href', '')
                if '{query}' not in href and '=' in href:
                    match = re.match(r'([^?]+\?)(\w+)=', href)
                    if match:
                        paths.append(f"{match.group(1)}{match.group(2)}={{query}}")

        paths.extend([
            '/search?q={query}',
            '/search?keyword={query}',
            '/search?query={query}',
            '/search?q={query}&page=1',
            '/s?q={query}',
            '/?q={query}',
            '/?keyword={query}',
            '/search/{query}',
            '/search/{query}/1',
            '/{query}',
            '/e/search/index.php',
            '/index.php?search={query}',
            '/index.php?q={query}',
            '/so/{query}',
            '/vodsearch/{query}----------1---/',
            '/search?q={query}&s=',
            '/plus/search.php?q={query}',
        ])

        seen = set()
        unique = []
        for p in paths:
            if '{query}' in p and p not in seen:
                seen.add(p)
                unique.append(p)
        return unique

    def _guess_post_searches(self, soup, url):
        results = []
        if not soup:
            return results
        forms = soup.find_all('form')
        for form in forms:
            action = form.get('action', '')
            method = form.get('method', 'get').lower()
            if method != 'post':
                continue
            inputs = form.find_all('input', {'name': True})
            body = {}
            for inp in inputs:
                name = inp.get('name', '')
                value = inp.get('value', '')
                inp_type = inp.get('type', 'text')
                if inp_type in ('submit', 'button'):
                    continue
                if name and value:
                    body[name] = value
                elif name:
                    body[name] = '{query}'
            if body:
                results.append((action or '/e/search/index.php', body))
        if not results:
            results.append(('/e/search/index.php', {
                'show': 'title',
                'tempid': '1',
                'tbname': 'article',
                'mid': '1',
                'classid': '0',
                'keyboard': '{query}',
            }))
            results.append(('/e/search/index.php', {
                'show': 'title,smalltext',
                'tempid': '1',
                'tbname': 'article',
                'mid': '1',
                'classid': '0',
                'keyboard': '{query}',
            }))
        return results

    def _extract_magnets(self, html, base_url):
        soup = BeautifulSoup(html, 'lxml')

        magnets = []
        seen_hashes = set()

        for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
            href = a['href']
            match = MAGNET_RE.match(href)
            if match:
                info_hash = re.search(r'btih:([0-9A-Fa-f]{32,40})', href, re.I)
                if info_hash:
                    h = info_hash.group(1).upper()
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)

                title = ''
                parent = a.parent
                for _ in range(3):
                    if parent:
                        for ta in parent.find_all('a', href=True):
                            txt = ta.get_text(strip=True)
                            if txt and len(txt) > 3 and 'magnet:' not in ta['href']:
                                title = txt[:100]
                                break
                        if title:
                            break
                        parent = parent.parent
                if not title:
                    title = a.get_text(strip=True)[:100]

                magnets.append({'title': title, 'magnet': href[:120], 'source': base_url})

        if not magnets:
            for a in soup.find_all('a', href=True):
                m = HASH_RE.search(a['href'])
                if m:
                    h = m.group(1).upper()
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)
                    title = a.get_text(strip=True)[:100]
                    magnets.append({
                        'title': title,
                        'magnet': f'magnet:?xt=urn:btih:{h}',
                        'source': base_url,
                    })

        if not magnets:
            for script in soup.find_all(['script', 'textarea', 'pre']):
                text = script.get_text()
                for m in MAGNET_RE.finditer(text):
                    magnets.append({
                        'title': '',
                        'magnet': m.group(0)[:120],
                        'source': base_url,
                    })
                if magnets:
                    break

        return (len(magnets) > 0, magnets)


def discover_from_search_engines(prober):
    log.info("=" * 60)
    log.info("  STRATEGY A: Search Engine Discovery")
    log.info("=" * 60)

    all_candidates = OrderedDict()

    for kw_idx, keyword in enumerate(SEARCH_KEYWORDS_CN):
        log.info(f"\n[{kw_idx+1}/{len(SEARCH_KEYWORDS_CN)}] Keyword: {keyword}")

        bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(keyword)}&count=30"
        try:
            resp = requests.get(bing_url, timeout=15, headers={
                **HEADERS,
                'Accept-Language': 'en-US,en;q=0.5',
            })
            if resp.status_code == 200:
                domains = extract_domains_from_search_results(resp.text)
                new_count = 0
                for domain, info in domains.items():
                    if domain not in all_candidates and not prober.is_existing(domain):
                        all_candidates[domain] = {**info, 'discovery': f'bing:{keyword}'}
                        new_count += 1
                log.info(f"  Bing: {len(domains)} domains, {new_count} new")
            else:
                log.info(f"  Bing: HTTP {resp.status_code}")
        except Exception as e:
            log.info(f"  Bing: {e}")
        time.sleep(1)

        baidu_url = f"https://www.baidu.com/s?wd={urllib.parse.quote(keyword)}&rn=30"
        try:
            resp = requests.get(baidu_url, timeout=15, headers=HEADERS)
            if resp.status_code == 200:
                domains = extract_domains_from_search_results(resp.text)
                new_count = 0
                for domain, info in domains.items():
                    if domain not in all_candidates and not prober.is_existing(domain):
                        all_candidates[domain] = {**info, 'discovery': f'baidu:{keyword}'}
                        new_count += 1
                log.info(f"  Baidu: {len(domains)} domains, {new_count} new")
            else:
                log.info(f"  Baidu: HTTP {resp.status_code}")
        except Exception as e:
            log.info(f"  Baidu: {e}")
        time.sleep(1)

    log.info(f"\n  Total candidates from search engines: {len(all_candidates)}")
    return all_candidates


def discover_from_existing_sources(prober):
    log.info("\n" + "=" * 60)
    log.info("  STRATEGY B: Friend Link Discovery from Existing Sources")
    log.info("=" * 60)

    working_origins = []
    try:
        with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for rs in data.get('rulesets', []):
            for r in rs.get('rules', []):
                if r['health']['status'] == 'green':
                    working_origins.append(r['site']['origin'])
    except Exception as e:
        log.warning(f"Cannot load sources.json: {e}")
        return OrderedDict()

    all_candidates = OrderedDict()

    for origin in working_origins:
        log.info(f"\n  Crawling: {origin}")
        try:
            resp = requests.get(origin, timeout=12, headers=HEADERS, allow_redirects=True)
            if resp.status_code != 200:
                log.info(f"    HTTP {resp.status_code}")
                continue

            links = extract_links_from_html(resp.text, origin)
            log.info(f"    Found {len(links)} external links")

            new_count = 0
            for link in links:
                domain = normalize_domain(link)
                if domain and not prober.is_existing(domain) and domain not in all_candidates:
                    all_candidates[domain] = {
                        'url': link,
                        'title': '',
                        'discovery': f'friendlink:{origin}',
                    }
                    new_count += 1
            log.info(f"    New candidates: {new_count}")

            try:
                from urllib.parse import urlparse
                parsed = urlparse(origin)
                links_page = f"{parsed.scheme}://{parsed.netloc}/links"
                resp2 = requests.get(links_page, timeout=8, headers=HEADERS, allow_redirects=True)
                if resp2.status_code == 200:
                    links2 = extract_links_from_html(resp2.text, links_page)
                    for link in links2:
                        domain = normalize_domain(link)
                        if domain and not prober.is_existing(domain) and domain not in all_candidates:
                            all_candidates[domain] = {
                                'url': link,
                                'title': '',
                                'discovery': f'friendlink:{origin}/links',
                            }
            except Exception:
                pass

        except Exception as e:
            log.info(f"    Error: {e}")
        time.sleep(0.5)

    log.info(f"\n  Total candidates from friend links: {len(all_candidates)}")
    return all_candidates


def verify_candidates(candidates, prober):
    log.info("\n" + "=" * 60)
    log.info("  VERIFICATION: 3-Layer Probe")
    log.info("=" * 60)

    verified = []
    l1_failed = []
    l2_http_failed = []
    l2_browser_failed = []
    skipped = 0
    total = len(candidates)

    items = list(candidates.items())
    for idx in range(len(items)):
        domain, info = items[idx]
        url = info.get('url', f'https://{domain}')
        if not url.startswith('http'):
            url = f'https://{domain}'

        log.info(f"\n[{idx+1}/{total}] {domain}")

        if any(ext in domain for ext in ['.gov.cn', '.edu.cn', '.org.cn']):
            log.info(f"    SKIP: government/edu domain")
            skipped += 1
            continue

        if '.' not in domain or len(domain) > 60 or '_' in domain:
            log.info(f"    SKIP: invalid domain")
            skipped += 1
            continue

        if any(kw in domain for kw in ['baidu.com', 'microsoft.com', 'google.com', 'bing.com']):
            log.info(f"    SKIP: known non-search domain")
            skipped += 1
            continue

        l1 = prober.probe_l1(url)
        if not l1['pass']:
            log.info(f"    L1 FAIL: {l1['reason']}")
            l1_failed.append((domain, l1['reason']))
            continue

        log.info(f"    L1 OK: title='{l1.get('title', '')}'")

        if not has_torrent_keywords(l1['html']):
            log.info(f"    L1 SKIP: no torrent keywords, trying deep check...")
            deep_ok = _deep_keyword_check(url, l1['html'])
            if not deep_ok:
                log.info(f"    L1 SKIP: deep check also negative")
                l1_failed.append((domain, 'no torrent keywords'))
                continue
            log.info(f"    L1 DEEP OK: found torrent indicators on sub-pages")

        l2 = prober.probe_l2_search(url, l1['html'])
        if l2['pass']:
            log.info(f"    L2 OK (HTTP): search_path='{l2['search_path']}' query='{l2['query']}' magnets={len(l2['magnets'])}")

            magnets = prober.probe_l3_full(url, l2['search_path'])
            if magnets:
                log.info(f"    L3 OK: {len(magnets)} magnets extracted")
            verified.append({
                'domain': domain,
                'url': url,
                'search_path': l2['search_path'],
                'magnets_count': len(magnets) if magnets else len(l2['magnets']),
                'sample_title': (magnets or l2['magnets'])[0].get('title', '')[:80] if (magnets or l2['magnets']) else '',
                'sample_magnet': (magnets or l2['magnets'])[0].get('magnet', '')[:80] if (magnets or l2['magnets']) else '',
                'requires_browser': False,
                'search_method': l2.get('search_method', 'GET'),
                'search_body': l2.get('search_body'),
                'discovery': info.get('discovery', ''),
                'title': l1.get('title', ''),
            })
            continue

        log.info(f"    L2 HTTP FAIL: {l2.get('reason', '')}")

        log.info(f"    Trying L2 with browser...")
        guessed_paths = ['/search?q={query}', '/?q={query}', '/search/{query}']
        browser_ok = False
        for sp in guessed_paths:
            for q in TEST_QUERIES_GENERAL[:1]:
                l2b = prober.probe_l2_search_browser(url, sp, q)
                if l2b['pass']:
                    log.info(f"    L2 OK (Browser): search_path='{sp}' magnets={len(l2b['magnets'])}")
                    verified.append({
                        'domain': domain,
                        'url': url,
                        'search_path': sp,
                        'magnets_count': len(l2b['magnets']),
                        'sample_title': l2b['magnets'][0].get('title', '')[:80] if l2b['magnets'] else '',
                        'sample_magnet': l2b['magnets'][0].get('magnet', '')[:80] if l2b['magnets'] else '',
                        'requires_browser': True,
                        'discovery': info.get('discovery', ''),
                        'title': l1.get('title', ''),
                    })
                    browser_ok = True
                    break
            if browser_ok:
                break

        if not browser_ok:
            l2_browser_failed.append((domain, 'browser: no magnets'))
            log.info(f"    L2 Browser FAIL")

        time.sleep(0.5)

    return verified, l1_failed, l2_http_failed, l2_browser_failed


def build_rule(site_info):
    domain = site_info['domain']
    url = site_info['url']
    if not url.startswith('http'):
        url = f'https://{domain}'

    rule_id = hashlib.md5(url.encode()).hexdigest()[:12]

    rule = {
        'id': rule_id,
        'site': {
            'name': domain,
            'origin': url,
        },
        'capabilities': {
            'supports_search': True,
            'supports_detail': False,
        },
        'search': {
            'request_template': site_info['search_path'],
            'timeout_ms': 15000,
            'retries': {
                'max_attempts': 3,
                'backoff_ms': 1000,
            },
            'requires_waf_bypass': False,
            'requires_browser': site_info.get('requires_browser', False),
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
        'quality': {
            'score': 70,
            'tags': ['追新极客'],
        },
        'health': {
            'status': 'green',
            'status_detail': 'ok',
            'last_checked_at': datetime.now(timezone.utc).isoformat(),
            'magnets_found': site_info['magnets_count'],
            'sample_title': site_info.get('sample_title', ''),
        },
    }

    if site_info.get('search_method') == 'POST' and site_info.get('search_body'):
        rule['search']['search_method'] = 'POST'
        rule['search']['search_body'] = site_info['search_body']

    return rule


def main():
    log.info("=" * 60)
    log.info("  SMART SOURCE DISCOVERY v2")
    log.info("=" * 60)
    log.info(f"  Time: {datetime.now().isoformat()}")

    prober = SourceProber()
    log.info(f"  Existing sources: {len(prober.existing_origins)}")

    candidates_a = discover_from_search_engines(prober)
    candidates_b = discover_from_existing_sources(prober)

    all_candidates = OrderedDict()
    for d, info in candidates_a.items():
        all_candidates[d] = info
    for d, info in candidates_b.items():
        if d not in all_candidates:
            all_candidates[d] = info

    log.info(f"\n  TOTAL unique candidates: {len(all_candidates)}")
    log.info(f"    From search engines: {len(candidates_a)}")
    log.info(f"    From friend links: {len(candidates_b)}")

    if not all_candidates:
        log.info("No candidates found. Exiting.")
        return

    verified, l1_failed, l2_http, l2_browser = verify_candidates(all_candidates, prober)

    log.info("\n" + "=" * 60)
    log.info("  RESULTS SUMMARY")
    log.info("=" * 60)
    log.info(f"  Total candidates:      {len(all_candidates)}")
    log.info(f"  L1 failed (connect):   {len(l1_failed)}")
    log.info(f"  L2 HTTP failed:        {len(l2_http)}")
    log.info(f"  L2 Browser failed:     {len(l2_browser)}")
    log.info(f"  VERIFIED (new sources): {len(verified)}")

    for v in verified:
        log.info(f"    + {v['domain']} ({v['magnets_count']} magnets, browser={v['requires_browser']})")
        log.info(f"      sample: {v.get('sample_title', '')}")

    if verified:
        with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        ruleset = data['rulesets'][0] if data.get('rulesets') else {
            'ruleset_id': 'base', 'priority': 1, 'max_sources_per_search': 10, 'rules': []
        }

        added = 0
        for v in verified:
            if normalize_domain(v['url']) in prober.existing_domains:
                continue
            rule = build_rule(v)
            ruleset['rules'].append(rule)
            prober.existing_domains.add(normalize_domain(v['url']))
            added += 1
            log.info(f"  Added to sources.json: {v['domain']}")

        data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
        data['generated_at'] = datetime.now(timezone.utc).isoformat()

        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        log.info(f"\n  {added} new sources added to sources.json")
        log.info(f"  Total sources now: {data['meta']['total_rules']}")

    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'candidates_from_engines': len(candidates_a),
        'candidates_from_friendlinks': len(candidates_b),
        'total_candidates': len(all_candidates),
        'l1_failed': len(l1_failed),
        'l2_http_failed': len(l2_http),
        'l2_browser_failed': len(l2_browser),
        'verified': verified,
        'l1_failures': [{'domain': d, 'reason': r} for d, r in l1_failed[:50]],
    }
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"  Report saved to {REPORT_FILE}")
    log.info("=" * 60)


if __name__ == '__main__':
    main()
