#!/usr/bin/env python3
"""
Deep Verify v2 — HTTP深度验证（无浏览器依赖）
===============================================
对每个 yellow 源：
  1. 用 cloudscraper 访问首页（跟随跳转、绕过WAF）
  2. 记录最终URL、页面标题、页面大小、关键词、链接
  3. 尝试多种搜索路径，提取磁力链接
  4. 输出判断依据供人工复核

用法：
  python magnet/deep_verify2.py                     # 验证全部 yellow
  python magnet/deep_verify2.py --start 10          # 从第11个开始
  python magnet/deep_verify2.py --count 5           # 只验证5个
  python magnet/deep_verify2.py --urls url1 url2    # 指定URL
  python magnet/deep_verify2.py --gray              # 也验证gray源
"""

import sys
import os
import re
import json
import time
import logging
import urllib.parse
from datetime import datetime, timezone
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
SOURCES_FILE = os.path.join(ROOT_DIR, 'sources.json')
REPORT_FILE = os.path.join(ROOT_DIR, 'deep_verify_report.json')

HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}', re.I)
INFO_HASH_RE = re.compile(r'[0-9A-Fa-f]{40}')

# 更全面的搜索路径组合
SEARCH_PATHS = [
    '/search/{query}',
    '/search?q={query}',
    '/search?keyword={query}',
    '/search?wd={query}',
    '/search?w={query}',
    '/?q={query}',
    '/?s={query}',
    '/?keyword={query}',
    '/?wd={query}',
    '/list?keyword={query}',
    '/search/{query}/1-0-0',
    '/search/{query}/1.html',
    '/s/{query}',
    '/so/{query}',
    '/find/{query}',
    '/hash/{query}',
]

SEARCH_QUERIES = ['Inception', 'Avatar']


def create_session():
    import cloudscraper
    sess = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
    )
    sess.headers.update({
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate',
    })
    return sess


def safe_get(session, url, timeout=15, allow_redirects=True):
    """安全GET请求，返回 (html, final_url, status_code, error)"""
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=allow_redirects)
        resp.encoding = resp.apparent_encoding or 'utf-8'
        return resp.text, resp.url, resp.status_code, None
    except Exception as e:
        return '', url, 0, str(e)[:200]


def extract_links(html, base_url):
    """从HTML中提取有意义链接"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    links = []
    for a in soup.find_all('a', href=True)[:50]:
        href = a['href']
        text = a.get_text(strip=True)[:60]
        if not text:
            continue
        # 转绝对URL
        if href.startswith('/'):
            parsed = urllib.parse.urlparse(base_url)
            href = f'{parsed.scheme}://{parsed.netloc}{href}'
        elif not href.startswith('http'):
            continue
        links.append({'text': text, 'href': href[:200]})
    return links


def extract_search_hints(html, base_url):
    """从首页HTML中提取搜索表单和可能的搜索路径"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    hints = []

    # 提取 <form> 的 action
    for form in soup.find_all('form'):
        action = form.get('action', '')
        method = form.get('method', 'get').lower()
        # 提取 input name
        inputs = [inp.get('name', '') for inp in form.find_all('input') if inp.get('name')]
        if action:
            if action.startswith('/'):
                parsed = urllib.parse.urlparse(base_url)
                action = f'{parsed.scheme}://{parsed.netloc}{action}'
            hints.append({'action': action, 'method': method, 'inputs': inputs})

    # 提取包含 search/so/find 关键词的链接
    for a in soup.find_all('a', href=True):
        href = a['href'].lower()
        if any(kw in href for kw in ['search', '/so/', '/find', '/s/']):
            if href.startswith('/'):
                parsed = urllib.parse.urlparse(base_url)
                href = f'{parsed.scheme}://{parsed.netloc}{href}'
            text = a.get_text(strip=True)[:40]
            hints.append({'link_text': text, 'link_href': href[:200]})

    return hints


def extract_magnets(html):
    """从HTML中提取所有磁力链接"""
    results = []
    seen = set()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')

    # 方式1: <a href="magnet:...">
    for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
        m = re.search(r'btih:([0-9A-Fa-f]{32,40})', a['href'], re.I)
        if m:
            hh = m.group(1).upper()
            if hh in seen:
                continue
            seen.add(hh)
            title = a.get_text(strip=True)[:80]
            results.append({'title': title, 'hash': hh[:16], 'magnet': a['href'][:150]})

    # 方式2: hash in <a href> path
    if not results:
        for a in soup.find_all('a', href=True):
            m = HASH_RE.search(a['href'])
            if m:
                hh = m.group(0).upper()
                if hh in seen:
                    continue
                seen.add(hh)
                title = a.get_text(strip=True)[:80]
                results.append({'title': title, 'hash': hh[:16], 'magnet': f'magnet:?xt=urn:btih:{hh}'})

    # 方式3: hash in plain text
    if not results:
        text = soup.get_text()
        for m in HASH_RE.finditer(text):
            hh = m.group(0).upper()
            if hh not in seen:
                seen.add(hh)
                results.append({'title': f'Hash {hh[:8]}...', 'hash': hh[:16], 'magnet': f'magnet:?xt=urn:btih:{hh}'})

    return results


def try_search(session, origin, homepage_hints=None):
    """尝试多种方式搜索并提取磁力"""
    parsed = urllib.parse.urlparse(origin.rstrip('/'))
    base = f'{parsed.scheme}://{parsed.netloc}'

    # 收集搜索路径：标准路径 + 从首页提取的路径
    paths = list(SEARCH_PATHS)

    # 如果首页form提取到action，加入优先尝试
    if homepage_hints:
        for hint in homepage_hints:
            if isinstance(hint, dict) and 'action' in hint:
                action = hint['action']
                inputs = hint.get('inputs', [])
                if inputs:
                    q_param = inputs[0]
                    if '?' in action:
                        paths.insert(0, action.replace(f'?{q_param}=', '') + f'?{q_param}={{query}}')
                    else:
                        paths.insert(0, action + f'?{q_param}={{query}}')

    seen_urls = set()
    for query in SEARCH_QUERIES:
        q = urllib.parse.quote(query)
        for path_tpl in paths:
            url = base + path_tpl.replace('{query}', q)
            # 去重
            url_norm = url.lower().rstrip('/')
            if url_norm in seen_urls:
                continue
            seen_urls.add(url_norm)

            html, final_url, status, err = safe_get(session, url, timeout=12)
            if err or status == 0:
                continue
            if status >= 400:
                continue
            if len(html) < 200:
                continue

            magnets = extract_magnets(html)
            if magnets:
                return {
                    'ok': True,
                    'magnets': len(magnets),
                    'samples': magnets[:5],
                    'path': path_tpl,
                    'query': query,
                    'search_url': url,
                }

    return None


def judge_source(info, search_result):
    """综合判断"""
    # 域名停放/出售
    parked = ['hugedomains', 'sedo', 'parking', 'domain is for sale', 'buy this domain',
              'afternic', 'dan.com', 'this domain', 'register4less']
    text_lower = info.get('text_sample', '').lower()
    title_lower = info.get('title', '').lower()
    for sig in parked:
        if sig in text_lower or sig in title_lower:
            return 'PARKED', f'域名停放/出售: {sig}'

    # 完全无法访问
    if info.get('error') and info['page_size'] == 0:
        return 'DEAD', f'无法访问: {info["error"][:80]}'

    # 页面过小
    if info['page_size'] < 300:
        return 'EMPTY', f'页面过小: {info["page_size"]} bytes'

    # 搜索成功！
    if search_result and search_result['ok']:
        return 'WORKING', f'搜索成功: {search_result["magnets"]} magnets (path={search_result["path"]} q={search_result["query"]})'

    # 有磁力关键词 + 搜索表单
    if info['has_magnet_keywords'] and info['has_search_form']:
        kws = ', '.join(info['keywords_found'][:5])
        return 'PROMISING', f'有磁力关键词[{kws}] + 搜索表单, 需要找到正确搜索路径'

    # 有磁力关键词但无搜索表单
    if info['has_magnet_keywords']:
        kws = ', '.join(info['keywords_found'][:5])
        return 'NEEDS_PATH', f'有磁力关键词[{kws}]但无标准搜索表单'

    # 跳转到其他域名
    if info['redirected']:
        rurl = info.get('final_url', '')
        # 如果跳转到的域名是已知的磁力源
        magnet_hints = ['magnet', 'torrent', 'bt', 'cili', '磁力', '种子']
        if any(kw in rurl.lower() for kw in magnet_hints):
            return 'REDIRECT_MAGNET', f'跳转到疑似磁力站: {rurl[:80]}'
        return 'REDIRECT', f'跳转到: {rurl[:100]}'

    # 有搜索表单但无磁力关键词
    if info['has_search_form']:
        return 'NAVIGATION', f'有搜索表单但无磁力关键词'

    if info.get('error'):
        return 'ERROR', f'部分错误: {info["error"][:80]}'

    return 'UNKNOWN', f'title={info["title"][:60]}, size={info["page_size"]}'


def main():
    import argparse
    parser = argparse.ArgumentParser(description='HTTP深度验证')
    parser.add_argument('--start', type=int, default=0, help='从第N个开始(0-based)')
    parser.add_argument('--count', type=int, default=0, help='验证N个(0=全部)')
    parser.add_argument('--urls', nargs='+', help='指定URL验证')
    parser.add_argument('--gray', action='store_true', help='也验证gray源')
    args = parser.parse_args()

    session = create_session()
    report = []

    try:
        if args.urls:
            targets = [{'name': urllib.parse.urlparse(u).netloc, 'origin': u, 'status': 'custom'} for u in args.urls]
        else:
            with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            targets = []
            for rs in data['rulesets']:
                for rule in rs['rules']:
                    h = rule['health']['status']
                    if h == 'yellow' or (args.gray and h == 'gray'):
                        targets.append({
                            'name': rule['site']['name'],
                            'origin': rule['site']['origin'],
                            'status': h,
                        })
            if args.start > 0:
                targets = targets[args.start:]
            if args.count > 0:
                targets = targets[:args.count]

        total = len(targets)
        log.info(f'待验证: {total} 个源')
        log.info('=' * 70)

        for idx, t in enumerate(targets):
            name = t['name']
            origin = t['origin'].rstrip('/')
            log.info(f'\n[{idx+1}/{total}] {name} ({origin})')

            # ---- Step 1: 访问首页 ----
            html, final_url, status, err = safe_get(session, origin, timeout=15)
            redirected = (final_url != origin)

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml') if html else None
            title = soup.title.string.strip()[:100] if soup and soup.title else ''

            info = {
                'origin': origin,
                'final_url': final_url,
                'redirected': redirected,
                'status_code': status,
                'error': err,
                'title': title,
                'page_size': len(html),
                'text_sample': soup.get_text()[:800] if soup else '',
            }

            # 关键词检测
            html_lower = html[:30000].lower() if html else ''
            magnet_kws = ['magnet:', 'btih', 'torrent', '磁力', '种子', '下载', 'bt下载', 'dht']
            found_kws = [kw for kw in magnet_kws if kw in html_lower]
            info['keywords_found'] = found_kws
            info['has_magnet_keywords'] = len(found_kws) >= 2

            # 搜索表单检测
            info['has_search_form'] = bool(
                html and re.search(r'<input[^>]*(?:type=["\']search|name=["\']*(?:q|search|keyword|wd|w))', html, re.I)
            )

            # 提取链接和搜索提示
            links = extract_links(html, origin) if html else []
            info['links_sample'] = links[:15]
            search_hints = extract_search_hints(html, origin) if html else []

            # 输出信息
            log.info(f'  状态码: {status}, 页面大小: {info["page_size"]} bytes')
            log.info(f'  标题: {title[:80]}')
            if redirected:
                log.info(f'  跳转: {final_url[:80]}')
            if err:
                log.info(f'  错误: {err[:80]}')
            if found_kws:
                log.info(f'  关键词: {found_kws}')
            if info['has_search_form']:
                log.info(f'  搜索表单: YES')
            if links[:5]:
                for lnk in links[:5]:
                    log.info(f'  链接: {lnk["text"][:40]} -> {lnk["href"][:60]}')
            if search_hints:
                for h in search_hints[:3]:
                    log.info(f'  搜索提示: {h}')

            # ---- Step 2: 尝试搜索 ----
            search_result = None
            if info['page_size'] > 300 and not err:
                search_result = try_search(session, origin, search_hints)
                if search_result:
                    log.info(f'  ★ 搜索成功: {search_result["magnets"]} magnets (path={search_result["path"]})')
                else:
                    log.info(f'  搜索未命中')
            else:
                log.info(f'  跳过搜索(页面不可用)')

            # ---- Step 3: 判断 ----
            verdict, reason = judge_source(info, search_result)
            log.info(f'  >>> 判定: {verdict} — {reason}')

            report.append({
                'name': name,
                'origin': origin,
                'original_status': t['status'],
                'verdict': verdict,
                'reason': reason,
                'title': title[:100],
                'page_size': info['page_size'],
                'status_code': status,
                'final_url': final_url,
                'redirected': redirected,
                'error': err,
                'keywords_found': found_kws,
                'has_magnet_keywords': info['has_magnet_keywords'],
                'has_search_form': info['has_search_form'],
                'search_result': search_result,
                'search_hints': search_hints[:5],
                'links_sample': links[:10],
                'text_sample': info['text_sample'][:300],
            })

            time.sleep(0.5)

    except KeyboardInterrupt:
        log.info('\n中断! 保存已收集的数据...')
    finally:
        pass

    # 保存报告
    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f'\n报告已保存到 {REPORT_FILE}')

    # 统计
    verdicts = Counter(r['verdict'] for r in report)
    log.info('\n' + '=' * 50)
    log.info('=== 判定统计 ===')
    for v, c in verdicts.most_common():
        log.info(f'  {v}: {c}')

    # 按分类输出
    log.info('\n=== 详细分类 ===')
    for v in ['WORKING', 'PROMISING', 'NEEDS_PATH', 'REDIRECT_MAGNET', 'REDIRECT',
              'NAVIGATION', 'PARKED', 'EMPTY', 'DEAD', 'ERROR', 'UNKNOWN']:
        items = [r for r in report if r['verdict'] == v]
        if items:
            log.info(f'\n--- {v} ({len(items)}) ---')
            for r in items:
                log.info(f'  {r["name"]} | {r["reason"][:80]}')


if __name__ == '__main__':
    main()
