#!/usr/bin/env python3
"""
一键磁力源健康检查 — Health Check for all green sources
=========================================================
对 sources.json 中所有 green 源执行真实搜索探测：
  1. 构造搜索 URL（使用诱饵关键词）
  2. 发送 HTTP 请求
  3. 用源的选择器解析 HTML，检查是否能找到磁力链接
  4. 更新 health 字段（status / status_detail / magnets_found / sample_title）
  5. 输出报告 + 可选写回 sources.json

用法:
  python magnet/health_check.py                 # 检查所有 green 源
  python magnet/health_check.py --write         # 检查并写回 sources.json
  python magnet/health_check.py --name btso.cc  # 只检查指定源
  python magnet/health_check.py --include-gray  # 也检查 gray 源（看是否恢复）
"""

import json, os, sys, re, time, argparse, concurrent.futures
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

TIMEOUT = 12  # seconds

# Bait queries by category — use common terms likely to have results
BAIT_QUERIES = {
    'default':  ['Avengers', '复仇者联盟'],
    'anime':    ['One Piece', 'Naruto', '海贼王'],
    'xxx':      ['sdde', 'ABP', 'SSIS'],
    'cn':       ['复仇者联盟', '战狼', '流浪地球'],
    'movie':    ['Inception', 'Interstellar', '复仇者联盟'],
    'music':    ['Taylor Swift', 'Adele'],
    'game':     ['Elden Ring', 'Cyberpunk'],
    'software': ['Fedora', 'Ubuntu'],
}

# Map Chinese / alternative tag aliases to canonical category keys above.
# Without this, sources tagged in Chinese (动漫, 电影, chinese, etc.) all
# fall through to the default 'Avengers' bait — which a Chinese-only site
# will never resolve, causing a false-positive PARSING_FAILED → yellow demotion.
TAG_ALIASES = {
    '动漫': 'anime', '新番': 'anime', 'acg': 'anime', '番剧': 'anime',
    '电影': 'movie', '影视': 'movie', '美剧': 'movie', '英剧': 'movie',
    '国产电影': 'cn', 'chinese': 'cn', '中文': 'cn',
    'av': 'xxx', 'jav': 'xxx', 'adult': 'xxx', '成人': 'xxx',
    '游戏': 'game', '音乐': 'music', '软件': 'software',
}

MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}', re.I)

# ── Result codes ──────────────────────────────────────────────────────
OK = 'ok'
HEALED = 'healed'       # was gray, now works
WAF = 'waf'             # got blocked by WAF/Cloudflare
NOT_FOUND = '404'
UNREACHABLE = 'unreachable'
PARSING_FAILED = 'parsing_failed'
EXPIRED = 'expired'


def pick_baits(rule):
    """Return ordered list of bait queries to try for this source.

    Strategy:
      1. Match canonical category from English tags (anime/xxx/cn/movie/...).
      2. Match Chinese / alternative tag aliases via TAG_ALIASES.
      3. If still nothing, use a category-mixed default list so that a
         Chinese-only site that wasn't tagged still gets a Chinese probe.

    Returns up to 3 bait words. probe_source() will retry with the next
    bait if magnets_found == 0, to avoid false-positive demotions caused
    by querying e.g. an anime site with "Avengers".
    """
    tags = [str(t).lower() for t in rule.get('quality', {}).get('tags', [])]
    matched = None
    for cat in ('anime', 'xxx', 'cn', 'movie', 'music', 'game', 'software'):
        if any(cat in t for t in tags):
            matched = cat
            break
    if not matched:
        for t in tags:
            if t in TAG_ALIASES:
                matched = TAG_ALIASES[t]
                break
    if matched:
        return BAIT_QUERIES[matched][:3]
    # No usable tag → mix EN + CN baits so Chinese-only sites still hit.
    return ['Avengers', '复仇者联盟', 'One Piece']


def pick_bait(rule):
    """Backwards-compatible single-bait picker (kept for any external import)."""
    return pick_baits(rule)[0]


def build_search_url(rule, query):
    """Build the full search URL from the rule template."""
    origin = rule['site']['origin'].rstrip('/')
    template = rule['search']['request_template']
    
    # Handle various template placeholders
    import base64
    q_encoded = quote(query)
    q_b64 = base64.b64encode(query.encode('utf-8')).decode('ascii')
    
    url = origin + template
    url = url.replace('{query}', q_encoded)
    url = url.replace('{query_raw}', query)
    url = url.replace('{query_b64}', q_b64)
    
    return url


def detect_waf(html, status_code):
    """Detect common WAF/challenge pages."""
    if status_code == 403:
        return True
    lower = html.lower()[:5000]
    waf_signals = [
        'cf-browser-verification', 'challenge-platform', '_cf_chl_opt',
        'just a moment', 'checking your browser', 'ddos-guard',
        'fingerprint', 'captcha', 'access denied',
    ]
    hits = sum(1 for s in waf_signals if s in lower)
    return hits >= 2


def _probe_once(rule, query):
    """Single probe attempt with one query. Returns same tuple as probe_source."""
    url = build_search_url(rule, query)
    start = time.time()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, verify=False)
        latency = int((time.time() - start) * 1000)
    except requests.exceptions.ConnectionError:
        return ('gray', UNREACHABLE, 0, '', 0, 'connection error')
    except requests.exceptions.Timeout:
        return ('gray', UNREACHABLE, 0, '', 0, 'timeout')
    except Exception as e:
        return ('gray', UNREACHABLE, 0, '', 0, str(e)[:80])
    
    if resp.status_code == 404:
        return ('gray', NOT_FOUND, 0, '', latency, f'HTTP 404')
    if resp.status_code == 403 or resp.status_code == 503:
        html = resp.text[:5000]
        if detect_waf(html, resp.status_code):
            return ('gray', WAF, 0, '', latency, f'WAF/Challenge detected (HTTP {resp.status_code})')
        return ('gray', WAF, 0, '', latency, f'HTTP {resp.status_code}')
    if resp.status_code >= 400:
        return ('gray', UNREACHABLE, 0, '', latency, f'HTTP {resp.status_code}')
    
    html = resp.text
    
    # Check for WAF in 200 response
    if detect_waf(html, resp.status_code):
        return ('gray', WAF, 0, '', latency, 'WAF in 200 response')
    
    # Check for redirect to parking/expired page
    if 'lander' in resp.url or 'parked' in html.lower()[:2000]:
        return ('gray', EXPIRED, 0, '', latency, 'domain parked/expired')
    
    # Parse with source selectors
    selectors = rule['search']['parse_metadata']['selectors']
    soup = BeautifulSoup(html, 'html.parser')
    
    # Method 1: Use selectors to find magnets
    magnets_found = 0
    sample_title = ''
    
    list_sel = selectors.get('list_item', '')
    magnet_sel = selectors.get('magnet', '')
    title_sel = selectors.get('title', '')
    
    if list_sel:
        items = soup.select(list_sel)
        for item in items[:20]:
            # Find magnet
            mag = None
            if magnet_sel:
                mag_el = item.select_one(magnet_sel)
                if mag_el:
                    href = mag_el.get('href', '')
                    if href.startswith('magnet:'):
                        mag = href
            if not mag:
                # Fallback: any magnet link in item
                for a in item.find_all('a', href=True):
                    if a['href'].startswith('magnet:'):
                        mag = a['href']
                        break
            if mag:
                magnets_found += 1
                if not sample_title and title_sel:
                    title_el = item.select_one(title_sel)
                    if title_el:
                        sample_title = title_el.get_text(strip=True)[:80]
    
    # Method 2: Fallback — count all magnet links on page
    if magnets_found == 0:
        all_magnets = MAGNET_RE.findall(html)
        magnets_found = len(set(all_magnets))
        if magnets_found > 0 and not sample_title:
            sample_title = '(magnet regex fallback)'
    
    if magnets_found > 0:
        return ('green', OK, magnets_found, sample_title, latency, None)
    else:
        # Page loaded but no magnets — might be selector mismatch or empty results
        # Check if we at least got meaningful content
        text_len = len(soup.get_text(strip=True))
        if text_len < 500:
            return ('gray', PARSING_FAILED, 0, '', latency, f'page too short ({text_len} chars)')
        
        # Check if there are any links at all that look like detail pages
        detail_sel = selectors.get('detail_link', '')
        if detail_sel:
            detail_links = soup.select(detail_sel)
            if detail_links:
                return ('green', OK, 0, '(detail-follow needed)', latency, 
                        f'{len(detail_links)} detail links found, magnets on detail pages')
        
        return ('yellow', PARSING_FAILED, 0, '', latency, 
                f'no magnets found (page has {text_len} chars, selectors may need update)')


def _probe_with_v3(rule, query):
    """Try probing via crawler_v3 orchestrator. Returns standard tuple or (None, ...) on skip."""
    name = rule['site']['name']
    try:
        from magnet.crawler_v3.orchestrator import search as v3_search
        start = time.time()
        results = v3_search(rule, query, limit=5)
        latency = int((time.time() - start) * 1000)
        if results:
            magnets = sum(1 for r in results if r.magnet)
            sample = results[0].title[:80] if results[0].title else ''
            return ('green', OK, magnets, sample, latency, None)
        return ('yellow', PARSING_FAILED, 0, '', latency, 'v3 orchestrator returned 0 results')
    except ImportError:
        return (None, None, 0, '', 0, 'crawler_v3 not installed, skipping v3 path')
    except Exception as e:
        return (None, None, 0, '', 0, f'v3 orchestrator error: {str(e)[:80]}')


def probe_source(rule):
    """Probe a source by trying up to 3 baits in order; returns first success.

    Multi-bait retry rationale: a source tagged "anime" probed with the only
    English bait "One Piece" may legitimately return 0 results on a Chinese
    anime site that only indexes 中文 titles. Without retry the source would
    be wrongly demoted to yellow / parsing_failed. Retry guards against this
    category-mismatch false-positive.

    Stops early on hard failures (unreachable / WAF / 404 / expired) — those
    are not bait-related so retrying with another bait wastes time.
    """
    name = rule['site']['name']
    handler = rule['search'].get('handler', '')
    if handler:
        return (None, None, 0, '', 0, f'skip: custom handler "{handler}"')

    # v3 orchestrator path: sources with tier_override (e.g. thatcdn) need
    # captcha-bypass handlers that plain requests can't handle.
    tier_override = rule.get('tier_override')
    if tier_override and tier_override.get('platform'):
        result = _probe_with_v3(rule, baits[0])
        if result[0] is not None:
            return result
        # v3 failed — fall through to plain requests probe below

    baits = pick_baits(rule)
    last = None
    all_attempts = []
    for i, q in enumerate(baits):
        result = _probe_once(rule, q)
        status, detail, magnets, sample, latency, error = result
        all_attempts.append(result)
        # Success — keep first bait that returns magnets.
        if status == 'green' and magnets > 0:
            return result
        # Hard network/WAF/expired failure — bait won't change outcome, stop.
        if detail in (UNREACHABLE, WAF, NOT_FOUND, EXPIRED):
            return result
        last = result
    # All baits exhausted; return the most recent (page-level) outcome,
    # with an annotation showing which baits were tried.
    if last:
        s, d, m, sa, lat, err = last
        tried = ','.join(baits)
        # Semantic suspect-dead-search signal: if every bait fetched a long
        # page yet found ZERO magnets on every try (selector AND regex
        # fallback), the search endpoint may be dead/hijacked — examples we
        # confirmed in v0.3.2: sobt21.top serves a GreatFire mirror,
        # laowangzo.top redirects /search to a 7KB stub homepage.
        #
        # BUT: we must NOT auto-demote to gray, because health_check uses
        # plain `requests` (no JS, no TLS impersonation) — sites like
        # knaben.org return 0 magnets to requests but full content to
        # StealthyFetcher. Auto-demoting them would silently break working
        # sources. So we just tag the error string with a 'suspect_dead'
        # prefix; an operator (or a future Stealthy-fetch verifier pass)
        # decides whether to actually flip to gray.
        all_zero_magnets = all(
            r[1] == PARSING_FAILED and r[2] == 0
            for r in all_attempts
        )
        if s == 'yellow' and all_zero_magnets and len(all_attempts) >= 2:
            err = (f'suspect_dead_search: all {len(all_attempts)} baits returned 0 '
                   f'page-level magnets via requests (verify with Stealthy/browser '
                   f'before demoting; could be requests-only anti-bot). '
                   f'orig: {err or "none"}')
        annotated = f'{err or ""} | tried baits: {tried}'.strip(' |')
        return (s, d, m, sa, lat, annotated)
    return ('gray', UNREACHABLE, 0, '', 0, 'no probe attempted')


def run_health_check(sources_file, write_back=False, name_filter=None, 
                     include_gray=False, max_workers=8):
    """Run health check on all qualifying sources."""
    with open(sources_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    rules = []
    for ruleset in data.get('rulesets', []):
        for rule in ruleset.get('rules', []):
            rules.append(rule)
    
    # Filter
    targets = []
    for rule in rules:
        name = rule['site']['name']
        status = rule.get('health', {}).get('status', 'gray')
        
        if name_filter and name_filter.lower() not in name.lower():
            continue
        if not include_gray and status == 'gray' and not name_filter:
            continue
        targets.append(rule)
    
    print(f"\n{'='*70}")
    print(f"  MagGoogo 源健康检查")
    print(f"  待检查: {len(targets)} 个源 (共 {len(rules)} 个)")
    print(f"  并发数: {max_workers}")
    print(f"{'='*70}\n")
    
    results = {}
    start_all = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(probe_source, r): r for r in targets}
        
        done_count = 0
        for future in concurrent.futures.as_completed(future_map):
            rule = future_map[future]
            name = rule['site']['name']
            old_status = rule.get('health', {}).get('status', 'gray')
            done_count += 1
            
            try:
                status, detail, magnets, sample, latency, error = future.result()
            except Exception as e:
                status, detail, magnets, sample, latency, error = (
                    'gray', UNREACHABLE, 0, '', 0, str(e)[:80])
            
            results[name] = {
                'old_status': old_status,
                'new_status': status,
                'detail': detail,
                'magnets': magnets,
                'sample': sample,
                'latency': latency,
                'error': error,
            }
            
            # Status emoji
            if status is None:
                icon = '⏭️'  # skipped
            elif status == 'green':
                icon = '🟢' if old_status == 'green' else '🔄'  # healed
            elif status == 'yellow':
                icon = '🟡'
            else:
                icon = '🔴'
            
            info = f"{magnets}m/{latency}ms" if status else (error or '')
            print(f"  [{done_count:3d}/{len(targets)}] {icon} {name:30s} {info}")
    
    elapsed = time.time() - start_all
    
    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  完成！耗时 {elapsed:.1f}s")
    print(f"{'='*70}\n")
    
    green_count = sum(1 for r in results.values() if r['new_status'] == 'green')
    yellow_count = sum(1 for r in results.values() if r['new_status'] == 'yellow')
    gray_count = sum(1 for r in results.values() if r['new_status'] == 'gray')
    skip_count = sum(1 for r in results.values() if r['new_status'] is None)
    healed = [n for n, r in results.items() 
              if r['old_status'] == 'gray' and r['new_status'] == 'green']
    degraded = [n for n, r in results.items() 
                if r['old_status'] == 'green' and r['new_status'] in ('gray', 'yellow')]
    
    print(f"  🟢 Green:  {green_count}")
    print(f"  🟡 Yellow: {yellow_count}")
    print(f"  🔴 Gray:   {gray_count}")
    print(f"  ⏭️  Skip:   {skip_count}")
    
    if healed:
        print(f"\n  🔄 恢复的源 ({len(healed)}):")
        for n in healed:
            print(f"     + {n}")
    
    if degraded:
        print(f"\n  ⚠️  降级的源 ({len(degraded)}):")
        for n in degraded:
            r = results[n]
            print(f"     - {n}: {r['detail']} — {r['error'] or ''}")
    
    # ── Problems detail ──
    problems = {n: r for n, r in results.items() 
                if r['new_status'] in ('gray', 'yellow') and r['new_status'] is not None}
    if problems:
        print(f"\n  📋 问题详情:")
        for n, r in sorted(problems.items()):
            print(f"     {n:30s} [{r['detail']:18s}] {r['error'] or ''}")
    
    # ── Write back ───────────────────────────────────────────────────
    if write_back:
        now = datetime.now(timezone.utc).isoformat()
        updated = 0
        for ruleset in data.get('rulesets', []):
            for rule in ruleset.get('rules', []):
                name = rule['site']['name']
                if name not in results:
                    continue
                r = results[name]
                if r['new_status'] is None:
                    continue  # skipped
                
                health = rule.setdefault('health', {})
                old = health.get('status', 'gray')
                new = r['new_status']
                
                # Determine new detail
                new_detail = r['detail']
                if old == 'gray' and new == 'green':
                    new_detail = HEALED
                
                health['status'] = new
                health['status_detail'] = new_detail
                health['last_checked_at'] = now
                health['magnets_found'] = r['magnets']
                if r['sample']:
                    health['sample_title'] = r['sample']
                
                if old != new:
                    updated += 1
        
        with open(sources_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n  ✅ 已写回 sources.json ({updated} 个状态变更)")
    else:
        print(f"\n  ℹ️  未写回。添加 --write 参数可写回 sources.json")
    
    return results


def main():
    parser = argparse.ArgumentParser(description='MagGoogo 源健康检查')
    parser.add_argument('--write', action='store_true', help='写回 sources.json')
    parser.add_argument('--name', type=str, help='只检查包含该名称的源')
    parser.add_argument('--include-gray', action='store_true', help='也检查 gray 源')
    parser.add_argument('--workers', type=int, default=8, help='并发线程数 (默认 8)')
    parser.add_argument('--sources', type=str, default=SOURCES_FILE, help='sources.json 路径')
    parser.add_argument('--report', type=str, default=None, help='把详细结果以 JSON 写入该路径')
    args = parser.parse_args()
    
    if not os.path.exists(args.sources):
        print(f"❌ 找不到 {args.sources}")
        sys.exit(1)
    
    # Suppress SSL warnings for sites with bad certs
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    results = run_health_check(
        sources_file=args.sources,
        write_back=args.write,
        name_filter=args.name,
        include_gray=args.include_gray,
        max_workers=args.workers,
    )

    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n  📄 详细 JSON 报告: {args.report}")


if __name__ == '__main__':
    main()
