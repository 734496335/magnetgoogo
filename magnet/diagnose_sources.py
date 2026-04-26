#!/usr/bin/env python3
"""
Diagnose Sources — 深度诊断每个源的失败原因
============================================
对每个源做 4 级诊断：
  L0  DNS/TCP 连通性（requests）
  L1  HTTP 状态码 + 页面大小 + 重定向目标
  L2  页面内容分析（是否有 torrent/magnet 关键词、是否是 parking 页、是否 404、是否已变成其他站）
  L3  Selenium 渲染后尝试提取 magnet/hash（对 SPA 站）

输出诊断结论分类：
  - unreachable: DNS 失败或 TCP 超时
  - 404: 页面返回 404
  - expired: 域名已过期/停放/出售
  - redirect: 已重定向到其他站（非磁力站）
  - waf: 有 WAF/Cloudflare 防护，无法绕过
  - parsing_failed: 页面可达但无法提取 magnet（可能是解析问题）
  - ok: 可以提取 magnet（升级为 green）
"""

import sys, os, re, json, time, logging, urllib.parse
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
    handlers=[logging.FileHandler('run.log', encoding='utf-8', mode='w'), logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')

PARKING_KW = ['domain for sale', 'domain parking', 'buy this domain', 'this domain is for sale',
              'sedo', 'lander', 'parking page', '域名出售', '域名交易', '此域名正在出售',
              'this domain has expired', 'domain expired', 'expired domain']

TORRENT_KW = ['magnet:', 'torrent', '种子', '磁力', 'btih', 'peer', 'seeder', 'leecher',
              'bit torrent', 'bittorrent', '下载', ' Download ', '.torrent']

NOT_TORRENT_KW = ['wordpress', 'blog', 'news', 'casino', 'porn tube', 'adult dating',
                  'escort', 'pharmacy', 'viagra', 'loan', 'mortgage', 'insurance']

BAIT_WORDS = ['Big Buck Bunny', 'Inception', 'Avengers', 'One Piece', 'sdde']


def get_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    d = webdriver.Chrome(options=opts)
    d.set_page_load_timeout(20)
    return d


def extract_hashes_from_text(text):
    hashes = set()
    for m in HASH_RE.finditer(text):
        hashes.add(m.group(0).upper())
    return hashes


def extract_magnets_from_html(html):
    from bs4 import BeautifulSoup
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


def diagnose(url, driver=None, current_status='unknown'):
    from bs4 import BeautifulSoup
    result = {
        'url': url,
        'status': 'unknown',
        'status_detail': 'unknown',
        'verdict': '',
        'checks': {},
    }

    # L0 + L1: HTTP probe
    html = None
    final_url = url
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
        result['checks']['http_status'] = resp.status_code
        result['checks']['final_url'] = resp.url
        result['checks']['html_len'] = len(resp.text)
        final_url = resp.url
        html = resp.text

        if resp.status_code == 404:
            result['status'] = 'gray'
            result['status_detail'] = '404'
            result['verdict'] = 'HTTP 404 — 页面不存在'
            return result

        if resp.status_code == 403:
            result['checks']['body_preview'] = html[:500]
            if 'cloudflare' in html[:2000].lower() or 'cf-browser' in html[:2000].lower():
                result['status'] = 'yellow'
                result['status_detail'] = 'waf'
                result['verdict'] = 'HTTP 403 + Cloudflare WAF'
                return result
            result['status'] = 'yellow'
            result['status_detail'] = 'waf'
            result['verdict'] = f'HTTP 403 — 服务器拒绝访问'
            return result

        if resp.status_code >= 400:
            result['status'] = 'gray'
            result['status_detail'] = 'unreachable'
            result['verdict'] = f'HTTP {resp.status_code}'
            return result

        if len(html) < 200:
            result['status'] = 'gray'
            result['status_detail'] = 'expired'
            result['verdict'] = f'页面内容过短 ({len(html)} bytes)'
            return result

    except requests.exceptions.Timeout:
        result['status'] = 'gray'
        result['status_detail'] = 'unreachable'
        result['verdict'] = '连接超时'
        return result
    except requests.exceptions.ConnectionError as e:
        err = str(e)[:200]
        if 'nodename nor servname' in err.lower() or 'getaddrinfo' in err.lower() or 'dns' in err.lower():
            result['status'] = 'gray'
            result['status_detail'] = 'unreachable'
            result['verdict'] = 'DNS 解析失败 — 域名可能已过期/不存在'
        elif 'connection refused' in err.lower():
            result['status'] = 'gray'
            result['status_detail'] = 'unreachable'
            result['verdict'] = '连接被拒绝 — 服务器未运行'
        else:
            result['status'] = 'gray'
            result['status_detail'] = 'unreachable'
            result['verdict'] = f'连接失败: {err[:60]}'
        return result
    except Exception as e:
        result['status'] = 'gray'
        result['status_detail'] = 'unreachable'
        result['verdict'] = f'异常: {str(e)[:60]}'
        return result

    # L1b: redirect check
    orig_domain = urllib.parse.urlparse(url).netloc.lower().replace('www.', '')
    final_domain = urllib.parse.urlparse(final_url).netloc.lower().replace('www.', '')
    if orig_domain != final_domain and final_domain:
        result['checks']['redirected_to'] = final_url
        lower = html[:5000].lower()
        has_torrent = any(kw in lower for kw in TORRENT_KW)
        if has_torrent:
            result['verdict'] = f'重定向到 {final_domain}（含磁力关键词，可能是镜像）'
            result['status'] = 'yellow'
            result['status_detail'] = 'parsing_failed'
        else:
            result['status'] = 'gray'
            result['status_detail'] = 'expired'
            result['verdict'] = f'重定向到 {final_domain}（非磁力站）'
            return result

    # L2: content analysis
    lower = html[:10000].lower()
    title = ''
    soup = BeautifulSoup(html, 'lxml')
    if soup.title and soup.title.string:
        title = soup.title.string.strip()[:80]
    result['checks']['title'] = title

    is_parking = any(kw in lower for kw in PARKING_KW)
    if is_parking:
        result['status'] = 'gray'
        result['status_detail'] = 'expired'
        result['verdict'] = f'域名停放/出售页 — title: {title}'
        return result

    has_torrent_kw = any(kw.lower() in lower for kw in TORRENT_KW)
    has_not_torrent_kw = any(kw.lower() in lower for kw in NOT_TORRENT_KW)
    result['checks']['has_torrent_kw'] = has_torrent_kw
    result['checks']['has_not_torrent_kw'] = has_not_torrent_kw

    if not has_torrent_kw and has_not_torrent_kw:
        result['status'] = 'gray'
        result['status_detail'] = 'expired'
        result['verdict'] = f'已变为非磁力站 — title: {title}'
        return result

    # L2b: try HTTP search
    for bait in BAIT_WORDS[:2]:
        for sp in ['/search?q={q}', '/search/{q}', '/?q={q}', '/?s={q}',
                    '/search.php?q={q}', '/torrents.php?search={q}',
                    '/search?query={q}', '/search/{q}/1/']:
            test_url = url.rstrip('/') + sp.replace('{q}', urllib.parse.quote(bait))
            try:
                r2 = requests.get(test_url, timeout=8, headers=HEADERS, allow_redirects=True)
                if r2.status_code == 200 and len(r2.text) > 200:
                    magnets = extract_magnets_from_html(r2.text)
                    if magnets:
                        result['status'] = 'green'
                        result['status_detail'] = 'ok'
                        result['verdict'] = f'HTTP 搜索可用 — {len(magnets)} magnets (path={sp}, bait={bait})'
                        result['checks']['magnets_found'] = len(magnets)
                        result['checks']['working_path'] = sp
                        result['checks']['working_bait'] = bait
                        return result
            except Exception:
                pass
        time.sleep(0.2)

    # L3: Selenium deep probe (only if driver provided and has torrent keywords)
    if driver and has_torrent_kw:
        for bait in BAIT_WORDS[:2]:
            for sp in ['/search/{q}', '/search?q={q}', '/?q={q}']:
                test_url = url.rstrip('/') + sp.replace('{q}', urllib.parse.quote(bait))
                try:
                    driver.get(test_url)
                    time.sleep(5)
                    rendered = driver.page_source

                    magnets = extract_magnets_from_html(rendered)
                    if magnets:
                        result['status'] = 'green'
                        result['status_detail'] = 'ok'
                        result['verdict'] = f'Selenium 搜索可用 — {len(magnets)} magnets (path={sp}, bait={bait})'
                        result['checks']['magnets_found'] = len(magnets)
                        result['checks']['working_path'] = sp
                        result['checks']['working_bait'] = bait
                        result['checks']['requires_browser'] = True
                        return result

                    hashes = extract_hashes_from_text(BeautifulSoup(rendered, 'lxml').get_text())
                    if len(hashes) >= 2:
                        result['status'] = 'green'
                        result['status_detail'] = 'ok'
                        result['verdict'] = f'Selenium hash提取 — {len(hashes)} hashes (path={sp}, bait={bait})'
                        result['checks']['magnets_found'] = len(hashes)
                        result['checks']['working_path'] = sp
                        result['checks']['working_bait'] = bait
                        result['checks']['requires_browser'] = True
                        return result
                except Exception:
                    pass
            time.sleep(0.5)

    # Final verdict: reachable but parsing failed
    if has_torrent_kw:
        result['status'] = 'yellow'
        result['status_detail'] = 'parsing_failed'
        result['verdict'] = f'可达+含磁力关键词但无法提取 — title: {title}'
    else:
        result['status'] = 'gray'
        result['status_detail'] = 'expired'
        result['verdict'] = f'可达但无磁力内容 — title: {title}'

    return result


def main():
    import requests

    log.info("=" * 70)
    log.info("  DIAGNOSE SOURCES v1")
    log.info("=" * 70)

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Collect sources to diagnose
    to_diagnose = []
    seen_domains = set()

    # A) Existing gray/yellow sources
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            st = r['health']['status']
            if st in ('gray', 'yellow'):
                origin = r['site']['origin']
                d = urllib.parse.urlparse(origin).netloc.lower().replace('www.', '')
                if d not in seen_domains:
                    seen_domains.add(d)
                    to_diagnose.append({
                        'name': r['site']['name'],
                        'url': origin,
                        'current_status': st,
                        'current_detail': r['health']['status_detail'],
                        'rule_id': r.get('id', ''),
                        'source': 'existing',
                    })

    # B) Previously "reachable but no magnets" from batch_probe
    batch_reachable = [
        {'name': 'btsow.pics (batch)', 'url': 'https://btsow.pics', 'source': 'batch'},
        {'name': '0magnet.co (batch)', 'url': 'https://0magnet.co', 'source': 'batch'},
        {'name': 'magnetsearch.org', 'url': 'https://magnetsearch.org', 'source': 'batch'},
        {'name': 'isohunt.to', 'url': 'https://isohunt.to', 'source': 'batch'},
        {'name': 'bitru.org', 'url': 'https://bitru.org', 'source': 'batch'},
        {'name': 'anilibria.tv', 'url': 'https://www.anilibria.tv', 'source': 'batch'},
        {'name': 'blueroms.com', 'url': 'https://blueroms.com', 'source': 'batch'},
        {'name': 'animetime.xyz', 'url': 'https://animetime.xyz', 'source': 'batch'},
        {'name': 'btdigg.org', 'url': 'https://btdigg.org', 'source': 'batch'},
        {'name': 'blueRoms.com', 'url': 'https://blueroms.com', 'source': 'batch'},
        {'name': '0magnet.cc', 'url': 'https://0magnet.cc', 'source': 'batch'},
        {'name': '1337x.gd', 'url': 'https://1337x.gd', 'source': 'batch'},
        {'name': 'x1337x.se', 'url': 'https://x1337x.se', 'source': 'batch'},
        {'name': '1337x.to', 'url': 'https://1337x.to', 'source': 'batch'},
        {'name': '1337x.st', 'url': 'https://1337x.st', 'source': 'batch'},
        {'name': 'btsow.one', 'url': 'https://btsow.one', 'source': 'batch'},
        {'name': 'dontorrent.xxx', 'url': 'https://dontorrent.xxx', 'source': 'batch'},
        {'name': 'btdirectory.org', 'url': 'https://btdirectory.org', 'source': 'batch'},
        {'name': 'kickasstorrents.bz', 'url': 'https://kickasstorrents.bz', 'source': 'batch'},
    ]
    for s in batch_reachable:
        d = urllib.parse.urlparse(s['url']).netloc.lower().replace('www.', '')
        if d not in seen_domains:
            seen_domains.add(d)
            to_diagnose.append({
                'name': s['name'],
                'url': s['url'],
                'current_status': 'unknown',
                'current_detail': '',
                'source': s['source'],
            })

    log.info(f"  Total to diagnose: {len(to_diagnose)}")

    # Phase 1: HTTP-only diagnosis
    log.info("\n" + "=" * 70)
    log.info("  PHASE 1: HTTP Diagnosis (all sources)")
    log.info("=" * 70)

    results = []
    for i, src in enumerate(to_diagnose):
        log.info(f"\n[{i+1}/{len(to_diagnose)}] {src['name']}: {src['url']}")
        r = diagnose(src['url'], driver=None, current_status=src.get('current_status', ''))
        r['name'] = src['name']
        r['source'] = src.get('source', '')
        r['current_status'] = src.get('current_status', '')
        r['current_detail'] = src.get('current_detail', '')
        r['rule_id'] = src.get('rule_id', '')
        results.append(r)
        verdict_short = r['verdict'][:80]
        log.info(f"  → {r['status']}/{r['status_detail']}: {verdict_short}")
        time.sleep(0.3)

    # Phase 2: Selenium deep diagnosis for "parsing_failed" or sites with torrent keywords
    needs_selenium = [r for r in results if r['status'] == 'yellow' and r['status_detail'] == 'parsing_failed']
    needs_selenium += [r for r in results if r['checks'].get('has_torrent_kw') and r['status'] != 'green']

    if needs_selenium:
        log.info("\n" + "=" * 70)
        log.info(f"  PHASE 2: Selenium Deep Diagnosis ({len(needs_selenium)} sources)")
        log.info("=" * 70)

        driver = get_driver()
        for i, prev in enumerate(needs_selenium):
            log.info(f"\n[{i+1}/{len(needs_selenium)}] {prev['name']}: {prev['url']}")
            r = diagnose(prev['url'], driver=driver, current_status=prev.get('current_status', ''))
            r['name'] = prev['name']
            r['source'] = prev.get('source', '')
            r['current_status'] = prev.get('current_status', '')
            r['rule_id'] = prev.get('rule_id', '')

            # Update in results list
            for j, old in enumerate(results):
                if old['url'] == prev['url']:
                    results[j] = r
                    break

            verdict_short = r['verdict'][:80]
            log.info(f"  → {r['status']}/{r['status_detail']}: {verdict_short}")

        driver.quit()

    # Summary
    log.info("\n" + "=" * 70)
    log.info("  DIAGNOSIS SUMMARY")
    log.info("=" * 70)

    by_verdict = {}
    for r in results:
        key = f"{r['status']}/{r['status_detail']}"
        by_verdict.setdefault(key, []).append(r)

    for key, items in sorted(by_verdict.items()):
        log.info(f"\n  [{key}] ({len(items)} sources)")
        for r in items:
            log.info(f"    {r['name']:25s} {r['url']:45s}")
            log.info(f"    {'':25s} {r['verdict'][:80]}")

    # Update sources.json for existing rules
    updated = 0
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            rule_id = r.get('id', '')
            for diag in results:
                if diag.get('rule_id') == rule_id and diag['source'] == 'existing':
                    old_status = r['health']['status']
                    old_detail = r['health']['status_detail']
                    new_status = diag['status']
                    new_detail = diag['status_detail']

                    if new_status != old_status or new_detail != old_detail:
                        r['health']['status'] = new_status
                        r['health']['status_detail'] = new_detail
                        r['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()
                        r['health']['diagnosis'] = diag['verdict']
                        updated += 1
                        log.info(f"  Updated {r['site']['name']}: {old_status}/{old_detail} → {new_status}/{new_detail}")

    if updated:
        data['generated_at'] = datetime.now(timezone.utc).isoformat()
        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"\n  Updated {updated} rules in sources.json")

    # Save full diagnosis report
    report_file = os.path.join(BASE_DIR, '..', 'diagnosis_report.json')
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_diagnosed': len(results),
            'summary': {k: len(v) for k, v in by_verdict.items()},
            'results': results,
        }, f, indent=2, ensure_ascii=False)
    log.info(f"  Report saved to {report_file}")
    log.info("=" * 70)


if __name__ == '__main__':
    import requests
    main()
