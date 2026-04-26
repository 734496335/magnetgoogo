#!/usr/bin/env python3
"""
Deep Verify — 浏览器逐源深度验证
==================================
对每个 yellow/gray 源：
  1. 用 Selenium 打开首页（非headless），等待真实渲染+跳转
  2. 记录最终URL、页面标题、页面大小、关键词
  3. 尝试搜索 Inception，提取磁力链接
  4. 输出判断依据

用法：
  python magnet/deep_verify.py                     # 验证全部 yellow
  python magnet/deep_verify.py --start 10          # 从第11个开始
  python magnet/deep_verify.py --urls url1 url2    # 指定URL
  python magnet/deep_verify.py --headless          # 无头模式
"""

import sys
import os
import re
import json
import time
import logging
import urllib.parse
from datetime import datetime, timezone

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
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')

# 搜索关键词和路径组合
SEARCH_TESTS = [
    ('Inception', '/search/{query}'),
    ('Inception', '/search?q={query}'),
    ('Inception', '/?q={query}'),
    ('Inception', '/?s={query}'),
    ('Inception', '/search?keyword={query}'),
    ('Big Buck Bunny', '/search/{query}'),
    ('Big Buck Bunny', '/search?q={query}'),
]


def create_driver(headless=False):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if headless:
        opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1366,900')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(25)
    driver.implicitly_wait(3)
    return driver


def extract_magnets_from_html(html):
    """从HTML中提取所有磁力链接"""
    results = []
    seen = set()

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')

    # 方式1: <a href="magnet:...">
    for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
        info_h = re.search(r'btih:([0-9A-Fa-f]{32,40})', a['href'], re.I)
        if info_h:
            hh = info_h.group(1).upper()
            if hh in seen:
                continue
            seen.add(hh)
            title = a.get_text(strip=True)[:80]
            results.append({'title': title, 'magnet': a['href'][:150]})

    # 方式2: hash in URL path
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

    # 方式3: hash in text
    if not results:
        for m in HASH_RE.finditer(soup.get_text()):
            hh = m.group(0).upper()
            if hh not in seen:
                seen.add(hh)
                results.append({'title': f'Hash {hh[:8]}...', 'magnet': f'magnet:?xt=urn:btih:{hh}'})

    return results


def analyze_page(driver, url, label=''):
    """访问页面，分析内容"""
    info = {
        'url': url,
        'final_url': url,
        'title': '',
        'page_size': 0,
        'redirected': False,
        'redirect_url': None,
        'has_magnet_keywords': False,
        'has_search_form': False,
        'has_torrent_links': False,
        'keywords_found': [],
        'links_sample': [],
        'page_text_sample': '',
    }

    try:
        driver.get(url)
        time.sleep(4)  # 等待JS渲染
    except Exception as e:
        info['error'] = str(e)[:200]
        return info

    info['final_url'] = driver.current_url
    info['title'] = driver.title[:200]
    info['redirected'] = (driver.current_url != url)
    info['redirect_url'] = driver.current_url if info['redirected'] else None

    html = driver.page_source
    info['page_size'] = len(html)

    # 文本内容
    text = driver.find_element('tag name', 'body').text[:2000] if driver.find_elements('tag name', 'body') else ''
    info['page_text_sample'] = text[:500]

    # 关键词检测
    magnet_kws = ['magnet:', 'btih', 'torrent', '磁力', '种子', '下载', 'BT', 'DHT']
    found_kws = [kw for kw in magnet_kws if kw.lower() in html[:20000].lower()]
    info['keywords_found'] = found_kws
    info['has_magnet_keywords'] = len(found_kws) >= 2

    # 搜索表单检测
    info['has_search_form'] = bool(
        driver.find_elements('css selector', 'input[type="search"], input[name*="search"], input[name*="q"], input[name*="keyword"], form[action*="search"]')
    )

    # 提取链接样本
    links = driver.find_elements('tag name', 'a')[:30]
    for a in links:
        try:
            href = a.get_attribute('href')
            txt = a.text.strip()[:60]
            if href and txt:
                info['links_sample'].append({'text': txt, 'href': href[:150]})
        except Exception:
            pass

    return info


def try_search(driver, origin, max_tries=5):
    """尝试搜索并提取磁力"""
    parsed = urllib.parse.urlparse(origin.rstrip('/'))
    base = f'{parsed.scheme}://{parsed.netloc}'

    for query, path_tpl in SEARCH_TESTS[:max_tries]:
        q = urllib.parse.quote(query)
        url = base + path_tpl.replace('{query}', q)
        try:
            driver.get(url)
            time.sleep(3)
            magnets = extract_magnets_from_html(driver.page_source)
            if magnets:
                return {
                    'ok': True,
                    'magnets': len(magnets),
                    'samples': magnets[:5],
                    'path': path_tpl,
                    'query': query,
                    'search_url': url,
                }
        except Exception:
            continue
    return None


def judge_source(homepage_info, search_result):
    """AI启发式判断源类型"""
    info = homepage_info

    # 判断1: 域名已出售/停放
    parked_signals = ['hugedomains', 'sedo', 'parking', 'domain is for sale', 'buy this domain', 'afternic']
    page_lower = info.get('page_text_sample', '').lower()
    title_lower = info.get('title', '').lower()
    for sig in parked_signals:
        if sig in page_lower or sig in title_lower:
            return 'PARKED', f'域名停放/出售: {sig}'

    # 判断2: 页面过小（<500字节通常意味着空壳）
    if info['page_size'] < 500 and not info.get('error'):
        return 'EMPTY', f'页面过小: {info["page_size"]} bytes'

    # 判断3: 搜索成功
    if search_result and search_result['ok']:
        return 'WORKING', f'搜索成功: {search_result["magnets"]} magnets (path={search_result["path"]} q={search_result["query"]})'

    # 判断4: 有磁力关键词 + 搜索表单 = 可能可用
    if info['has_magnet_keywords'] and info['has_search_form']:
        kws = ', '.join(info['keywords_found'][:5])
        return 'PROMISING', f'有磁力关键词[{kws}] + 搜索表单, 搜索路径可能不标准'

    # 判断5: 有搜索表单但无磁力关键词 = 可能是跳转/导航站
    if info['has_search_form'] and not info['has_magnet_keywords']:
        return 'NAVIGATION', f'有搜索表单但无磁力关键词, 可能是导航/跳转站'

    # 判断6: 有磁力关键词但无搜索表单 = 可能需要特殊路径
    if info['has_magnet_keywords'] and not info['has_search_form']:
        return 'NEEDS_PATH', f'有磁力关键词但无标准搜索表单, 需要找到正确搜索路径'

    # 判断7: 跳转到其他域名
    if info['redirected'] and info['redirect_url']:
        return 'REDIRECT', f'跳转到: {info["redirect_url"][:100]}'

    # 判断8: 什么都没有
    if info.get('error'):
        return 'ERROR', f'访问错误: {info["error"][:100]}'

    return 'UNKNOWN', f'无法判断: title={info["title"][:60]}, size={info["page_size"]}'


def main():
    import argparse
    parser = argparse.ArgumentParser(description='深度浏览器验证')
    parser.add_argument('--start', type=int, default=0, help='从第N个开始(0-based)')
    parser.add_argument('--count', type=int, default=0, help='验证N个(0=全部)')
    parser.add_argument('--urls', nargs='+', help='指定URL验证')
    parser.add_argument('--headless', action='store_true', help='无头模式')
    parser.add_argument('--gray', action='store_true', help='也验证gray源')
    parser.add_argument('--json-only', action='store_true', help='只输出JSON报告')
    args = parser.parse_args()

    driver = create_driver(headless=args.headless)
    report = []

    try:
        if args.urls:
            # 指定URL模式
            targets = []
            for url in args.urls:
                targets.append({
                    'name': urllib.parse.urlparse(url).netloc,
                    'origin': url,
                    'status': 'custom',
                })
        else:
            # 从 sources.json 加载
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

        log.info(f'待验证: {len(targets)} 个源')
        log.info('=' * 70)

        for idx, t in enumerate(targets):
            name = t['name']
            origin = t['origin']
            log.info(f'\n[{idx+1}/{len(targets)}] {name} ({origin})')

            # Step 1: 分析首页
            homepage_info = analyze_page(driver, origin, name)
            log.info(f'  标题: {homepage_info["title"][:80]}')
            log.info(f'  页面大小: {homepage_info["page_size"]} bytes')
            if homepage_info['redirected']:
                log.info(f'  跳转: {homepage_info["redirect_url"][:80]}')
            if homepage_info.get('error'):
                log.info(f'  错误: {homepage_info["error"][:80]}')
            if homepage_info['keywords_found']:
                log.info(f'  关键词: {homepage_info["keywords_found"]}')
            if homepage_info['has_search_form']:
                log.info(f'  搜索表单: YES')
            if homepage_info['links_sample'][:5]:
                for lnk in homepage_info['links_sample'][:5]:
                    log.info(f'  链接: {lnk["text"][:40]} -> {lnk["href"][:60]}')

            # Step 2: 尝试搜索
            search_result = None
            if homepage_info['page_size'] > 500 and not homepage_info.get('error'):
                search_result = try_search(driver, origin)
                if search_result:
                    log.info(f'  搜索成功: {search_result["magnets"]} magnets (path={search_result["path"]})')
                else:
                    log.info(f'  搜索未命中')

            # Step 3: 判断
            verdict, reason = judge_source(homepage_info, search_result)
            log.info(f'  >>> 判定: {verdict} — {reason}')

            report.append({
                'name': name,
                'origin': origin,
                'original_status': t['status'],
                'verdict': verdict,
                'reason': reason,
                'title': homepage_info['title'][:100],
                'page_size': homepage_info['page_size'],
                'final_url': homepage_info['final_url'],
                'redirected': homepage_info['redirected'],
                'keywords_found': homepage_info['keywords_found'],
                'has_search_form': homepage_info['has_search_form'],
                'search_result': search_result,
                'links_sample': homepage_info['links_sample'][:10],
                'page_text_sample': homepage_info['page_text_sample'][:300],
            })

            time.sleep(1)

    finally:
        driver.quit()

    # 保存报告
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f'\n报告已保存到 {REPORT_FILE}')

    # 统计
    from collections import Counter
    verdicts = Counter(r['verdict'] for r in report)
    log.info('\n=== 判定统计 ===')
    for v, c in verdicts.most_common():
        log.info(f'  {v}: {c}')


if __name__ == '__main__':
    main()
