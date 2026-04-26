#!/usr/bin/env python3
"""
10-hour autonomous magnet source discovery pipeline.
Phase 1: Discover nav hubs via search engines + parse nav hubs for real magnet site links
Phase 2: Full probe of all candidates with precise failure tagging
Phase 3: Deep retry REACHABLE sites with extended patterns

State file: probe_state.json (one entry per domain, supports resume)
Nav hubs file: nav_hubs.json
Candidate pool: candidates_pool.json
Log: run.log
"""
import sys, os, time, json, re, hashlib, logging, signal
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, quote_plus

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(SCRIPT_DIR, '..', 'sources.json')
STATE_FILE = os.path.join(SCRIPT_DIR, 'probe_state.json')
NAV_FILE = os.path.join(SCRIPT_DIR, 'nav_hubs.json')
POOL_FILE = os.path.join(SCRIPT_DIR, 'candidates_pool.json')
LOG_FILE = os.path.join(SCRIPT_DIR, 'run.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8', mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}
hash_re = re.compile(r'([0-9A-Fa-f]{40})')
HTTP_TIMEOUT = 8
QUICK_MODE = '--quick' in sys.argv

def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def maybe_limit(items):
    return items[:1] if QUICK_MODE else items

def http_get(url, timeout=None):
    timeout = timeout or HTTP_TIMEOUT
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        return resp
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.ReadTimeout:
        return None
    except requests.exceptions.ChunkedEncodingError:
        return None
    except requests.exceptions.ContentDecodingError:
        return None
    except requests.exceptions.TooManyRedirects:
        return None
    except Exception:
        return None

def classify_failure(url):
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT, headers=HEADERS, allow_redirects=True)
        if resp is None:
            return 'timeout'
        code = resp.status_code
        if code == 404:
            return '404'
        if code == 403:
            html = resp.text.lower()[:3000]
            if 'cloudflare' in html or 'just a moment' in html:
                return 'cloudflare'
            return '403'
        if code == 503:
            html = resp.text.lower()[:3000]
            if 'cloudflare' in html:
                return 'cloudflare'
            return str(code)
        if code >= 400:
            return str(code)
        if len(resp.text) < 200:
            return 'empty_response'
        return 'reachable'
    except requests.exceptions.Timeout:
        return 'timeout'
    except requests.exceptions.ConnectionError as e:
        estr = str(e).lower()
        if 'nodename' in estr or 'getaddrinfo' in estr or 'dns' in estr:
            return 'dns_fail'
        if 'refused' in estr:
            return 'refused'
        if 'reset' in estr or 'aborted' in estr:
            return 'connection_reset'
        return 'connection_error'
    except Exception:
        return 'error'

# ============================================================
# PHASE 1A: Discover navigation hub sites via search engines
# ============================================================
def phase1a_discover_nav_hubs():
    log.info("=" * 60)
    log.info("PHASE 1A: Discovering navigation hub sites")
    log.info("=" * 60)

    queries = [
        '磁力搜索 导航', '磁力搜索 网站 大全', '磁力链接 搜索引擎 网站',
        '磁力搜索 最新网址 2025', '磁力搜索 最新网址 2026',
        '种子搜索 网址导航', 'bt搜索 磁力 网址大全',
        '磁力猫 磁力狗 磁力熊猫 网址', '磁力搜 搜磁力',
        '磁力搜索引擎 推荐 国内可用', '磁力搜索 导航站',
        '磁力吧 磁力海 磁力天堂 网址',
    ]

    nav_keywords = ['磁力', '种子', '搜索', '导航', 'bt', 'magnet', 'torrent',
                    'cilimao', 'cilihezi', 'cili', 'btso', 'btsow', 'btdb', '磁力猫',
                    '磁力狗', '磁力熊', '磁力天堂', '磁力多', '磁力爬', '磁力星']

    known_nav_hubs = [
        'cilihezi.com', 'cilihezi.top', 'cilimao.biz', 'cilimao.fun', 'cilimao.im',
        'cilimao.io', 'cilimao.live', 'cilimao.me', 'cilimao.top',
        'cilitiantang.vip', 'ezhentang.com', 'bashi5.com', 'cili5.net',
        '12580.org', 'cldq.cc', 'cilishenqi.me', 'wuqianaa.xyz',
        'soucili.org', 'soucili.cc', 'dengshe.com',
        'cilihezi.com', 'cilsousuoyinqng.com.cn',
        'xiguasousou.com', 'souzhongzi.com', 'btcat.bid',
        'cilijun.cc', 'clmaoc.top', 'ciliss.cc', 'btfox12.top',
    ]

    discovered = set(known_nav_hubs)

    for qi, query in enumerate(maybe_limit(queries)):
        log.info(f"  Search [{qi+1}/{len(queries)}]: {query}")

        bing_url = f'https://cn.bing.com/search?q={quote_plus(query)}'
        resp = http_get(bing_url, timeout=20)
        if resp and resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'lxml')
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                if not href.startswith('http'):
                    continue
                if 'bing.com' in href or 'microsoft.com' in href:
                    continue
                parsed = urlparse(href)
                domain = parsed.netloc.lower()
                if not domain or '.' not in domain:
                    continue
                if domain.startswith('www.'):
                    domain = domain[4:]
                text = a.get_text(strip=True).lower()
                if any(kw in text for kw in nav_keywords) or any(kw in domain for kw in nav_keywords):
                    if domain not in discovered:
                        discovered.add(domain)
                        log.info(f"    NAV_HUB: {domain} | {a.get_text(strip=True)[:40]}")
        else:
            log.info(f"    Bing search failed")

        baidu_url = f'https://www.baidu.com/s?wd={quote_plus(query)}'
        resp = http_get(baidu_url, timeout=20)
        if resp and resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'lxml')
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                text = a.get_text(strip=True)
                if not text:
                    continue
                text_lower = text.lower()
                if not any(kw in text_lower for kw in nav_keywords):
                    continue
                if href.startswith('http://www.baidu.com/link') or href.startswith('https://www.baidu.com/link'):
                    domain = href.split('url=')[-1].split('&')[0] if 'url=' in href else ''
                    if domain.startswith('http'):
                        parsed = urlparse(domain)
                        real_domain = parsed.netloc.lower()
                        if real_domain and '.' in real_domain:
                            if real_domain.startswith('www.'):
                                real_domain = real_domain[4:]
                            if real_domain not in discovered and 'baidu' not in real_domain:
                                discovered.add(real_domain)
                                log.info(f"    NAV_HUB(baidu): {real_domain} | {text[:40]}")
                elif href.startswith('http'):
                    parsed = urlparse(href)
                    domain = parsed.netloc.lower()
                    if domain and '.' in domain and 'baidu.com' not in domain:
                        if domain.startswith('www.'):
                            domain = domain[4:]
                        if domain not in discovered:
                            discovered.add(domain)
                            log.info(f"    NAV_HUB(baidu): {domain} | {text[:40]}")
        else:
            log.info(f"    Baidu search failed")

        time.sleep(3)

    nav_list = sorted(discovered)
    save_json(NAV_FILE, nav_list)
    log.info(f"PHASE 1A DONE: {len(nav_list)} nav hubs discovered")
    return nav_list

# ============================================================
# PHASE 1B: Parse nav hubs for real magnet site links
# ============================================================
def phase1b_parse_nav_hubs(nav_hubs):
    log.info("")
    log.info("=" * 60)
    log.info("PHASE 1B: Parsing nav hubs for real magnet site links")
    log.info("=" * 60)

    existing_pool = load_json(POOL_FILE, [])
    candidates = set(existing_pool)

    for hub in maybe_limit(nav_hubs):
        hub_url = 'https://' + hub if '://' not in hub else hub
        log.info(f"  Parsing: {hub}")
        try:
            resp = http_get(hub_url, timeout=15)
            if not resp or resp.status_code != 200:
                log.info(f"    Failed (HTTP {resp.status_code if resp else 'None'})")
                save_json(POOL_FILE, sorted(candidates))
                continue

            soup = BeautifulSoup(resp.text, 'lxml')

            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue

                if href.startswith('/'):
                    full = urljoin(resp.url, href)
                else:
                    full = href

                if not full.startswith('http'):
                    continue

                parsed = urlparse(full)
                domain = parsed.netloc.lower()
                if not domain or '.' not in domain:
                    continue
                if domain.startswith('www.'):
                    domain = domain[4:]

                if domain == hub.lower().replace('www.', ''):
                    continue

                if any(kw in full.lower() for kw in ['beian', 'miit', 'gov.cn', 'javascript', 'void']):
                    continue

                candidates.add(domain)

            log.info(f"    Extracted links, total pool now: {len(candidates)}")
            save_json(POOL_FILE, sorted(candidates))
            time.sleep(1)
        except Exception as e:
            log.info(f"    ERROR: {e}")
            save_json(POOL_FILE, sorted(candidates))

    pool = sorted(candidates)
    save_json(POOL_FILE, pool)
    log.info(f"PHASE 1B DONE: {len(pool)} unique candidate domains")
    return pool

# ============================================================
# PHASE 2: Full probe with precise failure tagging
# ============================================================
def phase2_probe(candidates):
    log.info("")
    log.info("=" * 60)
    log.info("PHASE 2: Full probe with precise failure tagging")
    log.info("=" * 60)

    state = load_json(STATE_FILE, {})

    existing = set()
    src_data = load_json(SOURCES_FILE, {})
    for rs in src_data.get('rulesets', []):
        for r in rs.get('rules', []):
            existing.add(r['site']['origin'].lower().rstrip('/'))
            existing.add(r['site']['name'].lower())

    SEARCH_PATTERNS = [
        '/search?q=Inception', '/search?q=test', '/?q=Inception', '/?wd=Inception',
        '/search/Inception/', '/s/Inception', '/search.php?q=Inception',
        '/search.php?keywords=Inception', '/?s=Inception', '/so/Inception.html',
        '/search/Inception/1-0-0-0.html', '/search?q=Big+Buck+Bunny',
        '/hash/', '/popular', '/latest', '/top',
    ]

    total = len(candidates)
    done = sum(1 for d in candidates if d in state)
    log.info(f"  Total: {total}, already probed: {done}, remaining: {total - done}")

    for i, domain in enumerate(maybe_limit(candidates)):
        if domain in state:
            continue

        url = 'https://' + domain

        if url.lower().rstrip('/') in existing or domain in existing:
            state[domain] = {'status': 'existing', 'tested_at': datetime.now(timezone.utc).isoformat()}
            save_json(STATE_FILE, state)
            continue

        best_result = None
        best_count = 0

        for pattern in SEARCH_PATTERNS:
            test_url = url.rstrip('/') + pattern
            resp = http_get(test_url, timeout=HTTP_TIMEOUT)
            if not resp:
                continue
            if resp.status_code != 200:
                continue
            if len(resp.text) < 300:
                continue

            soup = BeautifulSoup(resp.text, 'lxml')
            title = soup.title.string[:40] if soup.title and soup.title.string else ''
            if 'just a moment' in title.lower():
                state[domain] = {
                    'status': 'cloudflare',
                    'tested_at': datetime.now(timezone.utc).isoformat(),
                    'url': url,
                    'title': title,
                }
                save_json(STATE_FILE, state)
                best_result = 'cloudflare'
                break

            magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
            hashes = set()
            for a in soup.find_all('a', href=True):
                m = hash_re.search(a['href'])
                if m:
                    hashes.add(m.group(1))

            count = len(magnets) + len(hashes)
            if count > best_count:
                best_count = count
                best_result = {
                    'status': 'ok' if count >= 2 else 'empty_result',
                    'tested_at': datetime.now(timezone.utc).isoformat(),
                    'url': url,
                    'pattern': pattern,
                    'magnets': count,
                    'title': title,
                }

            if count >= 2:
                break

        if best_result == 'cloudflare':
            log.info(f"  [{i+1}/{total}] {domain:35s} CLOUDFLARE")
        elif best_result and best_result.get('status') == 'ok':
            state[domain] = best_result
            save_json(STATE_FILE, state)
            log.info(f"  [{i+1}/{total}] {domain:35s} OK! {best_result['magnets']} magnets | {best_result['pattern']}")
        elif best_result:
            state[domain] = best_result
            save_json(STATE_FILE, state)
            log.info(f"  [{i+1}/{total}] {domain:35s} EMPTY (reachable but no magnets)")
        else:
            failure = classify_failure(url)
            state[domain] = {
                'status': failure,
                'tested_at': datetime.now(timezone.utc).isoformat(),
                'url': url,
            }
            save_json(STATE_FILE, state)
            log.info(f"  [{i+1}/{total}] {domain:35s} {failure.upper()}")

        if (i + 1) % 50 == 0:
            elapsed_names = [d for d in state]
            ok_count = sum(1 for v in state.values() if v.get('status') == 'ok')
            log.info(f"  --- Progress: {i+1}/{total} | ok={ok_count} | probed={len(state)} ---")

        time.sleep(0.3)

    log.info(f"PHASE 2 DONE: {len(state)} domains probed")

# ============================================================
# PHASE 3: Deep retry REACHABLE/empty_result sites
# ============================================================
def phase3_deep_retry():
    log.info("")
    log.info("=" * 60)
    log.info("PHASE 3: Deep retry REACHABLE/empty_result sites")
    log.info("=" * 60)

    state = load_json(STATE_FILE, {})

    retry_domains = [d for d, v in state.items() if v.get('status') in ('empty_result',)]
    log.info(f"  {len(retry_domains)} sites to deep retry")

    EXTENDED = [
        '/search/Big+Buck+Bunny/1-0-0-0.html', '/search?q=Big+Buck+Bunny',
        '/list?q=Big+Buck+Bunny', '/q/Big+Buck+Bunny',
        '/search/Interstellar', '/search?q=Interstellar',
        '/search/One+Piece', '/search?q=One+Piece',
        '/e/search/index.php', '/s/Big+Buck+Bunny',
        '/so/Big+Buck+Bunny.html', '/search.html?q=test',
        '/api/search?q=Inception', '/feed?q=Inception',
    ]

    upgraded = 0
    for i, domain in enumerate(retry_domains):
        url = 'https://' + domain
        log.info(f"  [{i+1}/{len(retry_domains)} Deep retry: {domain}")

        for pattern in EXTENDED:
            test_url = url.rstrip('/') + pattern
            resp = http_get(test_url, timeout=HTTP_TIMEOUT)
            if not resp or resp.status_code != 200 or len(resp.text) < 300:
                continue

            soup = BeautifulSoup(resp.text, 'lxml')
            t = soup.title
            title = t.string[:30] if t and t.string else ''
            if 'just a moment' in title.lower():
                continue

            magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
            hashes = set()
            for a in soup.find_all('a', href=True):
                m = hash_re.search(a['href'])
                if m:
                    hashes.add(m.group(1))

            count = len(magnets) + len(hashes)
            if count >= 2:
                state[domain] = {
                    'status': 'ok',
                    'tested_at': datetime.now(timezone.utc).isoformat(),
                    'url': url,
                    'pattern': pattern,
                    'magnets': count,
                    'title': title,
                    'upgraded_from': 'empty_result',
                }
                save_json(STATE_FILE, state)
                upgraded += 1
                log.info(f"    UPGRADED! {count} magnets via {pattern}")
                break

            time.sleep(0.3)

    log.info(f"PHASE 3 DONE: {upgraded} sites upgraded to OK")

# ============================================================
# FINAL: Generate report
# ============================================================
def generate_report():
    log.info("")
    log.info("=" * 60)
    log.info("FINAL REPORT")
    log.info("=" * 60)

    state = load_json(STATE_FILE, {})

    by_status = {}
    for domain, info in state.items():
        st = info.get('status', 'unknown')
        by_status.setdefault(st, []).append(domain)

    for st in sorted(by_status.keys()):
        domains = by_status[st]
        log.info(f"  {st:20s}: {len(domains):4d}")
        if st in ('ok', 'cloudflare') or len(domains) <= 10:
            for d in domains:
                info = state[d]
                extra = ''
                if info.get('magnets'):
                    extra = f" ({info['magnets']} magnets)"
                if info.get('title'):
                    extra += f" | {info['title']}"
                log.info(f"    {d:35s}{extra}")

    ok_domains = by_status.get('ok', [])
    log.info("")
    log.info(f"  WORKING SOURCES: {len(ok_domains)}")

    save_json(os.path.join(SCRIPT_DIR, 'final_state.json'), state)
    log.info(f"  Full state saved to probe_state.json and final_state.json")
    log.info("=" * 60)

# ============================================================
# MAIN
# ============================================================
def main():
    log.info(f"Pipeline started at {datetime.now().isoformat()}")
    log.info(f"Working dir: {SCRIPT_DIR}")

    signal.signal(signal.SIGBREAK, signal.SIG_IGN)

    nav_hubs = load_json(NAV_FILE, None)
    if nav_hubs is None or len(nav_hubs) == 0:
        nav_hubs = phase1a_discover_nav_hubs()
    else:
        log.info(f"PHASE 1A: Loaded {len(nav_hubs)} nav hubs from {NAV_FILE}")

    pool = load_json(POOL_FILE, None)
    if pool is None or len(pool) == 0:
        pool = phase1b_parse_nav_hubs(nav_hubs)
    else:
        log.info(f"PHASE 1B: Loaded {len(pool)} candidates from {POOL_FILE}")

    existing_urls = set()
    for d in pool:
        existing_urls.add('https://' + d)
    existing_urls.update(nav_hubs)

    all_candidates = sorted(set(pool + nav_hubs))
    log.info(f"Total candidates to probe: {len(all_candidates)}")

    phase2_probe(all_candidates)
    phase3_deep_retry()
    generate_report()

    log.info(f"Pipeline finished at {datetime.now().isoformat()}")

if __name__ == '__main__':
    main()
