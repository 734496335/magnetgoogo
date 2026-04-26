#!/usr/bin/env python3
"""
Human-in-the-Loop Source Verifier v2 — 人机协作源验证器
=======================================================
两阶段工作：
  Phase 1 (自动预筛): headless HTTP 快速检测每个候选
    - 连接失败/超时 → 自动跳过
    - 页面太小/parking → 自动跳过
    - 无任何磁力/种子关键词 → 自动跳过
    - 有磁力/种子关键词 → 进入 Phase 2
    - 品牌匹配 → 优先级提升（即使无关键词也进 Phase 2）
  Phase 2 (人工确认): 弹出真实浏览器，逐个验证预筛通过的候选
    - 用户手动过 Cloudflare/验证码
    - 脚本自动尝试搜索 + 提取 magnet/hash
    - 找不到时用户可手动搜索后让脚本提取

用法:
  python magnet/human_verify.py                       # 自动预筛+人工确认
  python magnet/human_verify.py --urls url1 url2      # 指定URL（跳过预筛）
  python magnet/human_verify.py --candidates          # 只从 candidates.json
  python magnet/human_verify.py --retry-failed        # 重试之前失败的
  python magnet/human_verify.py --start-from 50       # 从第50个开始
  python magnet/human_verify.py --no-prescreen        # 跳过预筛，全部人工
"""

import sys, os, re, json, time, hashlib, logging, urllib.parse, argparse
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
    handlers=[logging.FileHandler('run.log', encoding='utf-8', mode='a'), logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')
CANDIDATES_FILE = os.path.join(BASE_DIR, '..', 'mega_hunter_candidates.json')
RESULTS_FILE = os.path.join(BASE_DIR, '..', 'human_verify_results.json')

HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')
BAIT_WORDS = ['Big Buck Bunny', 'Inception', 'One Piece']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

TORRENT_POSITIVE = [
    'magnet:', 'magnet link', 'magnet link', 'torrent', 'bittorrent', 'bit torrent',
    'btih', '种子', '磁力', '磁力搜索', '磁力链接', '磁力下载',
    'bt下载', 'bt搜索', '种子下载', '种子搜索', 'seeders', 'leechers', 'peers',
    'torrent search', 'torrent download', 'torrent site',
    'hash:', 'info_hash', 'tracker',
]

TORRENT_MAYBE = [
    'download', '下载', '影视', 'anime', 'manga', 'doujin', 'hentai',
    'warez', 'release', 'dvdrip', 'brrip', 'webrip', '1080p', '720p', '4k',
    'x264', 'x265', 'hevc', 'h264', 'h265', 'mkv', 'mp4',
    '游戏下载', 'movie download', 'free download',
]

TORRENT_NEGATIVE = [
    'wordpress', 'blog', 'news', 'casino', 'porn tube', 'adult dating',
    'escort', 'pharmacy', 'viagra', 'loan', 'mortgage', 'insurance',
    'cooking', 'recipe', 'travel', 'hotel booking', 'real estate',
    '域名出售', '域名交易', 'domain for sale', 'domain parking',
    'hugedomains', 'sedo', 'godaddy', 'namecheap',
    '京华', '环球网', '人民网', '新华网', '央视', '中国青年报',
]

SKIP_DOMAIN_PATTERNS = [
    r'\.gov\.cn$', r'\.edu\.cn$', r'\.org\.cn$',
    r'^(dxzhgl|beian)\.', r'news\.', r'blog\.', r'baike\.',
    r'baike\.baidu', r'zhidao\.baidu', r'jingyan\.baidu',
    r'health\.baidu', r'agents\.baidu',
    r'zhihu\.com', r'csdn\.net', r'jianshu\.com',
    r'\.cambridge\.org$', r'\.oxford$', r'dictionary\.',
    r'etymonline', r'wikiwand', r'collinsdictionary', r'iciba',
]


def extract_from_html(html, url=''):
    from bs4 import BeautifulSoup
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
            d = urllib.parse.urlparse(r['site']['origin']).netloc.lower().replace('www.', '')
            existing.add(d)
    return existing, data


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


def prompt_choice(msg, choices='ynsq'):
    while True:
        ans = input(msg).strip().lower()
        if ans in choices: return ans


def prescreen(site):
    import requests
    url = site.get('url', f"https://{site.get('domain', '')}")
    domain = site.get('domain', normalize_domain(url))
    brand = site.get('brand', '')

    for pat in SKIP_DOMAIN_PATTERNS:
        if re.search(pat, domain):
            return {'pass': False, 'reason': '非磁力站域名（政府/教育/百科/新闻）'}

    resp = None
    try:
        resp = requests.get(url, timeout=8, headers=HEADERS, allow_redirects=True)
    except requests.exceptions.Timeout:
        return {'pass': False, 'reason': '连接超时（可能被GFW阻断）'}
    except requests.exceptions.ConnectionError:
        return {'pass': False, 'reason': '连接失败'}
    except Exception as e:
        return {'pass': False, 'reason': f'异常: {str(e)[:50]}'}

    if resp.status_code == 403:
        lower = resp.text[:3000].lower()
        if 'cloudflare' in lower or 'cf-browser' in lower:
            if brand or any(kw in lower for kw in ['torrent', 'magnet']):
                return {'pass': True, 'reason': 'Cloudflare 403 + 有磁力关键词/品牌匹配，需人工过验证'}
            return {'pass': False, 'reason': 'HTTP 403 + Cloudflare，无磁力关键词'}
        return {'pass': False, 'reason': f'HTTP {resp.status_code}'}

    if resp.status_code >= 400:
        return {'pass': False, 'reason': f'HTTP {resp.status_code}'}

    if len(resp.text) < 300:
        return {'pass': False, 'reason': f'页面过小 ({len(resp.text)} bytes)'}

    orig_domain = normalize_domain(url)
    final_domain = normalize_domain(resp.url)
    if orig_domain != final_domain and final_domain:
        lower = resp.text[:5000].lower()
        if not any(kw in lower for kw in TORRENT_POSITIVE):
            return {'pass': False, 'reason': f'重定向到 {final_domain}（非磁力站）'}

    lower = resp.text[:15000].lower()
    title = ''
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, 'lxml')
    if soup.title and soup.title.string:
        title = soup.title.string.strip()[:60]

    has_positive = any(kw in lower for kw in TORRENT_POSITIVE)
    has_maybe = any(kw in lower for kw in TORRENT_MAYBE)
    has_negative = any(kw in lower for kw in TORRENT_NEGATIVE)

    if has_positive:
        magnets = extract_from_html(resp.text, url)
        if magnets:
            return {
                'pass': True, 'reason': f'HTTP直接提取到 {len(magnets)} 个磁力链接',
                'magnets': len(magnets), 'samples': magnets[:3],
                'title': title, 'auto_ok': True,
            }
        return {'pass': True, 'reason': f'含磁力关键词（需浏览器确认），title: {title}', 'title': title}

    if brand:
        brand_lower = brand.lower()
        if has_positive:
            return {'pass': True, 'reason': f'品牌[{brand}]+磁力关键词，title: {title}', 'title': title}
        if has_maybe and not has_negative:
            brand_torrent_kws = ['bt', 'torrent', 'magnet', 'seed', 'peer', 'leech',
                                  'nyaa', 'dmhy', 'mikan', 'acg', 'jav', 'anime',
                                  'pirate', 'limetorrent', 'torlock', 'kickass', 'eztv',
                                  'solidtorrent', 'torrentgalaxy', 'extratorrent', 'idope',
                                  'magnetdl', 'snowfl', 'btsow', 'btdigg', 'bt4g',
                                  'ciligou', 'cilimao', 'btant', 'zhongzi', '磁力', '种子']
            if any(kw in brand_lower for kw in brand_torrent_kws):
                return {'pass': True, 'reason': f'BT相关品牌[{brand}]，title: {title}', 'title': title}
        return {'pass': False, 'reason': f'品牌[{brand}]但页面无关，title: {title}'}

    if has_maybe and not has_negative:
        return {'pass': True, 'reason': f'可能相关（含下载/影视关键词），title: {title}', 'title': title}

    if has_negative and not has_positive and not has_maybe:
        return {'pass': False, 'reason': f'非磁力站，title: {title}'}

    return {'pass': False, 'reason': f'无磁力相关内容，title: {title}'}


def verify_site(driver, url, brand='', prescreen_info=None):
    domain = normalize_domain(url)
    result = {
        'domain': domain, 'url': url, 'brand': brand,
        'status': 'unknown', 'magnets_found': 0, 'samples': [], 'countries': [],
    }

    if prescreen_info and prescreen_info.get('auto_ok'):
        result['status'] = 'ok'
        result['magnets_found'] = prescreen_info.get('magnets', 0)
        result['samples'] = prescreen_info.get('samples', [])
        result['countries'] = ['china']
        result['working_path'] = '/auto'
        print(f"  >>> HTTP 直接提取到 {result['magnets_found']} 个磁力链接，无需浏览器验证 <<<")
        return result

    print(f"\n  {'='*55}")
    print(f"  打开浏览器: {url}")
    if prescreen_info:
        print(f"  预筛信息: {prescreen_info.get('reason', '')}")
    print(f"  {'='*55}")

    try:
        driver.get(url)
    except Exception as e:
        print(f"  浏览器加载失败: {e}")
        result['status'] = 'unreachable'
        return result

    print(f"\n  [浏览器已打开]")
    print(f"  操作: 过验证=等完成后按Enter | 不是磁力站=s | 退出=q")
    ans = prompt_choice("  >>> ", 'sq\n')

    if ans == 'q':
        result['status'] = 'skipped_quit'
        return result
    if ans == 's':
        result['status'] = 'not_torrent_site'
        return result

    html = driver.page_source
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    title = soup.title.string.strip()[:60] if soup.title and soup.title.string else ''
    result['homepage_title'] = title
    print(f"  页面: {title}")

    magnets = extract_from_html(html, url)
    if magnets:
        result['status'] = 'ok'
        result['magnets_found'] = len(magnets)
        result['samples'] = magnets[:5]
        result['countries'] = ['china']
        print(f"  首页直接提取到 {len(magnets)} 个磁力链接!")
        return result

    for bait in BAIT_WORDS:
        for sp in [f'/search/{urllib.parse.quote(bait)}', f'/search?q={urllib.parse.quote(bait)}',
                    f'/?q={urllib.parse.quote(bait)}', f'/?s={urllib.parse.quote(bait)}',
                    f'/search?query={urllib.parse.quote(bait)}']:
            search_url = url.rstrip('/') + sp
            print(f"\n  搜索: {search_url}")
            try:
                driver.get(search_url)
            except Exception:
                continue
            print(f"  [搜索页已打开] 过验证后按Enter | 跳过=s | 下个路径=n | 退出=q")
            ans = prompt_choice("  >>> ", 'snq\n')
            if ans == 'q': return result
            if ans == 's': break
            if ans == 'n': continue

            html = driver.page_source
            magnets = extract_from_html(html, url)
            if magnets:
                result['status'] = 'ok'
                result['magnets_found'] = len(magnets)
                result['samples'] = magnets[:5]
                result['working_path'] = sp
                result['working_bait'] = bait
                result['countries'] = ['china']
                print(f"\n  >>> 找到 {len(magnets)} 个磁力链接 <<<")
                for m in magnets[:3]:
                    print(f"      {m['title'][:50]}")
                return result
        if result.get('status') == 'skipped_quit':
            return result

    print(f"\n  自动搜索未找到。可以手动在浏览器里搜索，找到后按Enter提取")
    ans = prompt_choice("  Enter=提取当前页 / s=跳过 / f=标记可达需手动: ", 'sfq\n')
    if ans == 'q': return result
    if ans == 'f':
        result['status'] = 'reachable_manual'
        result['countries'] = ['china']
        return result
    if ans == 's':
        result['status'] = 'no_magnets'
        return result

    html = driver.page_source
    magnets = extract_from_html(html, url)
    if magnets:
        result['status'] = 'ok'
        result['magnets_found'] = len(magnets)
        result['samples'] = magnets[:5]
        result['countries'] = ['china']
        print(f"  找到 {len(magnets)} 个磁力链接!")
    else:
        result['status'] = 'no_magnets'
    return result


def add_verified_to_sources(results):
    ok = [r for r in results if r['status'] == 'ok']
    if not ok: return 0
    existing, data = load_existing()
    ruleset = data['rulesets'][0]
    added = 0
    for r in ok:
        d = r['domain']
        if d in existing: continue
        existing.add(d)
        rule_id = hashlib.md5(r['url'].encode()).hexdigest()[:12]
        countries = r.get('countries', ['china'])
        rule = {
            'id': rule_id,
            'site': {'name': d, 'origin': r['url'].rstrip('/'), 'countries': countries},
            'capabilities': {'supports_search': True, 'supports_detail': False},
            'search': {
                'request_template': r.get('working_path', '/search?q={query}'),
                'timeout_ms': 15000,
                'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                'requires_waf_bypass': False,
                'requires_browser': True,
                'parse_metadata': {'selectors': {
                    'list_item': 'div.item', 'title': 'a[href^="magnet:"]',
                    'magnet': 'a[href^="magnet:"]', 'size': 'span.size', 'date': 'span.date',
                }}
            },
            'quality': {'score': 70, 'tags': ['追新极客']},
            'health': {
                'status': 'green', 'status_detail': 'ok',
                'last_checked_at': datetime.now(timezone.utc).isoformat(),
                'magnets_found': r['magnets_found'],
                'sample_title': r['samples'][0].get('title', '')[:80] if r.get('samples') else '',
            },
        }
        if r.get('brand'): rule['site']['brand'] = r['brand']
        ruleset['rules'].append(rule)
        added += 1
        log.info(f"  Added: {d} ({r['magnets_found']} magnets)")
    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
    data['generated_at'] = datetime.now(timezone.utc).isoformat()
    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return added


def main():
    parser = argparse.ArgumentParser(description='Human-in-the-Loop Source Verifier v2')
    parser.add_argument('--urls', nargs='*', help='URLs to verify')
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--candidates', action='store_true')
    parser.add_argument('--start-from', type=int, default=0)
    parser.add_argument('--no-prescreen', action='store_true', help='Skip prescreen, verify all manually')
    args = parser.parse_args()

    print("=" * 60)
    print("  人机协作源验证器 v2 (预筛+人工确认)")
    print("=" * 60)

    import requests
    existing, _ = load_existing()

    sites = []
    if args.urls:
        for u in args.urls:
            d = normalize_domain(u)
            if d and d not in existing:
                sites.append({'url': u if u.startswith('http') else f'https://{u}', 'brand': '', 'domain': d})
    elif args.candidates or (not args.urls and not args.retry_failed):
        try:
            with open(CANDIDATES_FILE, 'r', encoding='utf-8') as f:
                cdata = json.load(f)
            for c in cdata.get('candidates', []):
                d = c.get('domain', '')
                if d and d not in existing:
                    sites.append({'url': c.get('url', f'https://{d}'), 'brand': c.get('brand', ''), 'domain': d})
        except FileNotFoundError:
            print("  candidates.json 不存在")
    elif args.retry_failed:
        try:
            with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                rdata = json.load(f)
            for r in rdata.get('results', []):
                if r.get('status') in ('no_magnets', 'unreachable', 'reachable_manual', 'not_torrent_site'):
                    d = r.get('domain', '')
                    if d and d not in existing:
                        sites.append({'url': r.get('url', f'https://{d}'), 'brand': r.get('brand', ''), 'domain': d})
        except FileNotFoundError:
            print("  results 文件不存在")

    if args.start_from:
        sites = sites[args.start_from:]

    print(f"  候选总数: {len(sites)}")

    # Phase 1: Prescreen
    if not args.no_prescreen:
        print(f"\n{'='*60}")
        print(f"  Phase 1: 自动预筛 (HTTP headless)")
        print(f"{'='*60}")

        passed = []
        auto_ok = []
        failed = []

        for i, site in enumerate(sites):
            domain = site.get('domain', '')
            url = site.get('url', '')
            brand = site.get('brand', '')
            print(f"  [{i+1}/{len(sites)}] {domain:35s}", end='', flush=True)

            r = prescreen(site)
            site['prescreen'] = r

            if r['pass']:
                if r.get('auto_ok'):
                    auto_ok.append(site)
                    print(f" AUTO-OK ({r.get('magnets', 0)} magnets)")
                else:
                    passed.append(site)
                    print(f" PASS ({r['reason'][:50]})")
            else:
                failed.append(site)
                print(f" SKIP ({r['reason'][:50]})")
            time.sleep(0.2)

        print(f"\n  预筛结果:")
        print(f"    自动通过(HTTP直接提取): {len(auto_ok)}")
        print(f"    需人工确认: {len(passed)}")
        print(f"    自动跳过: {len(failed)}")

        for s in auto_ok:
            print(f"    + {s['domain']:30s} {s['prescreen'].get('magnets', 0)} magnets (HTTP)")

        print(f"\n  需人工确认的站点:")
        for s in passed:
            print(f"    ? {s['domain']:30s} {s['prescreen'].get('reason', '')[:50]}")

        if not passed and not auto_ok:
            print(f"\n  没有通过预筛的候选。")
            if failed:
                print(f"\n  失败原因分布:")
                reasons = {}
                for s in failed:
                    r = s.get('prescreen', {}).get('reason', 'unknown')
                    key = r.split('（')[0].split('(')[0].strip()
                    reasons[key] = reasons.get(key, 0) + 1
                for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
                    print(f"      {v:3d}x {k}")
            return

        # Save auto_ok results immediately
        auto_results = []
        for s in auto_ok:
            ps = s['prescreen']
            auto_results.append({
                'domain': s['domain'], 'url': s['url'], 'brand': s.get('brand', ''),
                'status': 'ok', 'magnets_found': ps.get('magnets', 0),
                'samples': ps.get('samples', []),
                'working_path': '/auto', 'countries': ['china'],
            })
        if auto_results:
            added = add_verified_to_sources(auto_results)
            print(f"\n  已自动添加 {added} 个源到 sources.json (HTTP直接验证通过)")

        if not passed:
            print(f"\n  无需人工确认的站点。完成!")
            return

        # Phase 2: Human verification
        print(f"\n{'='*60}")
        print(f"  Phase 2: 人工确认 ({len(passed)} 个站点)")
        print(f"{'='*60}")
        print(f"  操作: 弹出浏览器 → 过验证 → 按Enter → 脚本提取")
        print(f"  s=跳过 q=退出\n")

        sites = passed

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1280,900')
    print("  启动浏览器...")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)

    results = []
    for i, site in enumerate(sites):
        print(f"\n[{i+1}/{len(sites)}] {site['url']}")
        r = verify_site(driver, site['url'], site.get('brand', ''), site.get('prescreen'))
        results.append(r)
        if r.get('status') == 'skipped_quit':
            break

    driver.quit()

    # Summary
    print(f"\n{'='*60}")
    print(f"  验证结果")
    print(f"{'='*60}")
    ok = [r for r in results if r['status'] == 'ok']
    manual = [r for r in results if r['status'] == 'reachable_manual']
    not_torrent = [r for r in results if r['status'] == 'not_torrent_site']
    no_magnets = [r for r in results if r['status'] == 'no_magnets']

    print(f"\n  可用: {len(ok)}")
    for r in ok: print(f"    + {r['domain']:25s} {r['magnets_found']:3d} magnets")
    print(f"  需手动搜索: {len(manual)}")
    for r in manual: print(f"    ? {r['domain']:25s}")
    print(f"  不是磁力站: {len(not_torrent)}")
    print(f"  无磁力: {len(no_magnets)}")

    # Save
    all_results = auto_results if not args.no_prescreen else []
    all_results.extend(results)
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total': len(all_results), 'ok': len([r for r in all_results if r['status'] == 'ok']),
            'results': all_results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  结果: {RESULTS_FILE}")

    if ok:
        added = add_verified_to_sources(results)
        print(f"  新增 {added} 个源到 sources.json")

    print(f"{'='*60}")


if __name__ == '__main__':
    main()
