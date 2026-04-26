#!/usr/bin/env python3
"""
Clean & Verify — 清理非磁力源 + 验证黄灯源
============================================
步骤：
  1. 用 AI 启发式规则移除明确非磁力搜索源的条目
  2. 更新诱饵词：去掉 Ubuntu，换为更典型的英文电影名
  3. 对所有 yellow 源进行 HTTP 搜索验证
  4. 能搜到磁力的升级为 green

用法：
  python magnet/clean_and_verify.py                # 全部执行
  python magnet/clean_and_verify.py --clean-only   # 仅清理
  python magnet/clean_and_verify.py --verify-only  # 仅验证
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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')

# 替换 Ubuntu 的更典型电影名
SEARCH_QUERIES = [
    ('Inception', '/search/{query}'),
    ('Inception', '/search?q={query}'),
    ('Inception', '/?q={query}'),
    ('Inception', '/?s={query}'),
    ('Inception', '/search?keyword={query}'),
    ('Big Buck Bunny', '/search/{query}'),
    ('Big Buck Bunny', '/search?q={query}'),
    ('Big Buck Bunny', '/?q={query}'),
    ('Big Buck Bunny', '/?s={query}'),
    ('The Dark Knight', '/search?q={query}'),
    ('The Dark Knight', '/?q={query}'),
    ('Interstellar', '/search?q={query}'),
    ('Interstellar', '/?q={query}'),
    ('Avatar', '/search?q={query}'),
    ('Avatar', '/?q={query}'),
    ('mp4', '/search?q={query}'),
    ('mp4', '/?q={query}'),
]

import requests
from bs4 import BeautifulSoup


# ============================================================
# Step 1: AI 启发式分类 — 明确非磁力搜索引擎的域名/品牌
# ============================================================
NON_MAGNET_PATTERNS = {
    # 测试/占位
    'dummy-site.com': '测试占位站，非真实磁力源',

    # 已确认非搜索引擎的知名站点
    'verycd.com': 'VeryCD电驴，已关闭公开搜索API（HTTP 405）',
    'bitport.io': '云端BT下载工具，非公开磁力搜索引擎',

    # 导航站 — URL 指向具体收藏页/站点页，非搜索入口
    'swnav.cn': '导航站，URL指向收藏页（/favorites/6744.html），非搜索入口',
    'eeenav.com': '导航站，URL指向站点详情页（/sites/2905.html），非搜索入口',

    # 影视资讯/论坛站
    'yingyin.org': '影音论坛/资讯站，非磁力搜索引擎',
    'dianyingtiantang.me': '电影天堂，影视资讯站，非磁力搜索引擎',
    'lingfengyun.com': '凌风云搜索聚合，非磁力专用搜索引擎',
    'xiongmaokv.top': '熊猫KV，视频播放站，非磁力搜索引擎',
}


def clean_non_magnet_sources(data):
    """移除明确非磁力源的条目"""
    removed = []
    for rs in data.get('rulesets', []):
        rules = rs.get('rules', [])
        new_rules = []
        for rule in rules:
            name = rule['site']['name']
            if name in NON_MAGNET_PATTERNS:
                reason = NON_MAGNET_PATTERNS[name]
                removed.append((name, reason))
                log.info(f'  REMOVE: {name} — {reason}')
            else:
                new_rules.append(rule)
        rs['rules'] = new_rules
    return removed


# ============================================================
# Step 2: 诱饵词更新 — 去掉 Ubuntu，改为典型电影名
# ============================================================
def update_bait_words():
    """更新各文件中的诱饵词，去掉 Ubuntu"""
    files_updated = []

    # Healer BAIT_REGISTRY
    healer_path = os.path.join(BASE_DIR, 'crawler', 'healer.py')
    if os.path.exists(healer_path):
        with open(healer_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content

        # 更新 BAIT_REGISTRY
        content = content.replace(
            "'CHINESE': ['Ubuntu', 'Inception', 'Avatar', 'Big Buck Bunny']",
            "'CHINESE': ['Inception', 'Avatar', 'Big Buck Bunny', 'The Dark Knight']"
        )
        content = content.replace(
            "'TECH': ['Ubuntu', 'Windows 11', 'Python', 'VS Code', 'Debian']",
            "'TECH': ['Windows 11', 'Python', 'VS Code', 'Debian', 'Fedora']"
        )
        content = content.replace(
            "'GENERAL': ['Inception', 'Interstellar', 'Batman', 'Dune', 'Avatar', 'Ubuntu']",
            "'GENERAL': ['Inception', 'Interstellar', 'The Dark Knight', 'Dune', 'Avatar', 'Big Buck Bunny']"
        )
        content = content.replace(
            "'DEFAULT': ['Ubuntu', 'Interstellar', 'Big Buck Bunny']",
            "'DEFAULT': ['Inception', 'Interstellar', 'Big Buck Bunny']"
        )

        if content != original:
            with open(healer_path, 'w', encoding='utf-8') as f:
                f.write(content)
            files_updated.append(healer_path)
            log.info(f'  UPDATED: {healer_path} — BAIT_REGISTRY')

    # Validation test_query
    validation_path = os.path.join(BASE_DIR, 'validation', 'validation.py')
    if os.path.exists(validation_path):
        with open(validation_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content
        content = content.replace(
            "self.test_query = 'Ubuntu'",
            "self.test_query = 'Inception'"
        )
        # 也更新 test_queries 列表中的 Ubuntu
        content = content.replace(
            "test_queries = ['Ubuntu', 'Movie', 'Game', 'Anime', '磁力', 'torrent']",
            "test_queries = ['Inception', 'Movie', 'Game', 'Anime', '磁力', 'torrent']"
        )

        if content != original:
            with open(validation_path, 'w', encoding='utf-8') as f:
                f.write(content)
            files_updated.append(validation_path)
            log.info(f'  UPDATED: {validation_path} — test_query & test_queries')

    return files_updated


# ============================================================
# Step 3: HTTP 搜索验证
# ============================================================
def extract_magnets(html):
    soup = BeautifulSoup(html, 'lxml')
    results = []
    seen = set()
    for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
        info_h = re.search(r'btih:([0-9A-Fa-f]{32,40})', a['href'], re.I)
        if info_h:
            hh = info_h.group(1).upper()
            if hh in seen:
                continue
            seen.add(hh)
            title = a.get_text(strip=True)[:80]
            results.append({'title': title, 'magnet': a['href'][:150]})
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
    if not results:
        for m in HASH_RE.finditer(soup.get_text()):
            hh = m.group(0).upper()
            if hh not in seen:
                seen.add(hh)
                results.append({'title': f'Hash {hh[:8]}...', 'magnet': f'magnet:?xt=urn:btih:{hh}'})
    return results


def try_http_search(origin, max_seconds=30):
    base = origin.rstrip('/')
    # 去掉 URL 中的路径部分（如 /?go, /sites/2905.html 等）
    from urllib.parse import urlparse
    parsed = urlparse(base)
    base = f'{parsed.scheme}://{parsed.netloc}'

    t0 = time.time()
    for query, path_tpl in SEARCH_QUERIES:
        if time.time() - t0 > max_seconds:
            break
        q = urllib.parse.quote(query)
        url = base + path_tpl.replace('{query}', q)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=6, allow_redirects=True)
            if resp.status_code >= 400:
                continue
            if len(resp.text) < 300:
                continue
            magnets = extract_magnets(resp.text)
            if magnets:
                return {
                    'ok': True,
                    'magnets': len(magnets),
                    'samples': magnets[:3],
                    'path': path_tpl,
                    'query': query,
                    'requires_browser': False,
                }
        except requests.RequestException:
            continue
    return None


def try_selenium_search(origin):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException

    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1366,900')
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(20)
    driver.implicitly_wait(2)

    try:
        from urllib.parse import urlparse
        parsed = urlparse(origin.rstrip('/'))
        base = f'{parsed.scheme}://{parsed.netloc}'

        for query, path_tpl in SEARCH_QUERIES[:6]:
            q = urllib.parse.quote(query)
            url = base + path_tpl.replace('{query}', q)
            try:
                driver.get(url)
                time.sleep(4)
            except (TimeoutException, Exception):
                continue
            magnets = extract_magnets(driver.page_source)
            if magnets:
                return {
                    'ok': True,
                    'magnets': len(magnets),
                    'samples': magnets[:3],
                    'path': path_tpl,
                    'query': query,
                    'requires_browser': True,
                }
        return None
    finally:
        driver.quit()


def verify_yellow_sources(data, use_selenium=False):
    """验证所有 yellow 源"""
    promoted = 0
    updated = 0

    yellow_rules = []
    for rs in data.get('rulesets', []):
        for rule in rs.get('rules', []):
            h = rule.get('health', {})
            if h.get('status') == 'yellow':
                yellow_rules.append(rule)

    log.info(f'Yellow 源总数: {len(yellow_rules)}')
    log.info('=' * 70)

    for idx, rule in enumerate(yellow_rules):
        origin = rule['site']['origin']
        name = rule['site']['name']
        log.info(f'[{idx+1}/{len(yellow_rules)}] {name} ({origin})')

        t0 = time.time()
        result = try_http_search(origin)
        dt = time.time() - t0
        log.info(f'  HTTP耗时 {dt:.1f}s')

        if result and result['ok']:
            magnets = result['magnets']
            log.info(f'  HTTP OK: {magnets} magnets (path={result["path"]} q={result["query"]})')
            for s in result['samples'][:2]:
                log.info(f'    {s["magnet"][:80]}')
            rule['health']['status'] = 'green'
            rule['health']['status_detail'] = 'ok'
            rule['health']['magnets_found'] = magnets
            rule['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()
            rule['health']['sample_title'] = result['samples'][0]['title'][:80] if result['samples'] else ''
            rule['health']['diagnosis'] = ''
            rule['search']['request_template'] = result['path']
            rule['search']['requires_browser'] = result.get('requires_browser', False)
            rule['quality']['score'] = 70
            promoted += 1
            updated += 1
        elif use_selenium:
            log.info('  HTTP 未命中，尝试 Selenium...')
            result = try_selenium_search(origin)
            if result and result['ok']:
                magnets = result['magnets']
                log.info(f'  Selenium OK: {magnets} magnets')
                rule['health']['status'] = 'green'
                rule['health']['status_detail'] = 'ok'
                rule['health']['magnets_found'] = magnets
                rule['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()
                rule['health']['sample_title'] = result['samples'][0]['title'][:80] if result['samples'] else ''
                rule['health']['diagnosis'] = ''
                rule['search']['request_template'] = result['path']
                rule['search']['requires_browser'] = True
                rule['quality']['score'] = 70
                promoted += 1
                updated += 1
            else:
                log.info('  Selenium 也未命中')
        else:
            log.info(f'  未命中')

        time.sleep(0.5)

    log.info(f'\n验证完成: {updated} 个源更新, {promoted} 个升级为 green')
    return promoted, updated


# ============================================================
# Main
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description='清理非磁力源 + 验证黄灯源')
    parser.add_argument('--clean-only', action='store_true', help='仅清理非磁力源')
    parser.add_argument('--verify-only', action='store_true', help='仅验证黄灯源')
    parser.add_argument('--selenium', action='store_true', help='HTTP未命中时也尝试Selenium')
    args = parser.parse_args()

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_before = sum(len(rs['rules']) for rs in data['rulesets'])
    log.info(f'当前源总数: {total_before}')

    # Step 1: 清理非磁力源
    if not args.verify_only:
        log.info('\n=== Step 1: 清理非磁力源 ===')
        removed = clean_non_magnet_sources(data)
        log.info(f'移除 {len(removed)} 个非磁力源')
        for name, reason in removed:
            log.info(f'  - {name}: {reason}')

    # Step 2: 更新诱饵词
    if not args.verify_only:
        log.info('\n=== Step 2: 更新诱饵词 (去掉Ubuntu) ===')
        files = update_bait_words()
        log.info(f'更新了 {len(files)} 个文件')

    # Step 3: 验证黄灯源
    if not args.clean_only:
        log.info('\n=== Step 3: 验证黄灯源 ===')
        promoted, updated = verify_yellow_sources(data, use_selenium=args.selenium)

    # 保存
    now = datetime.now(timezone.utc).isoformat()
    data['generated_at'] = now
    total_after = sum(len(rs['rules']) for rs in data['rulesets'])

    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    log.info(f'\n=== 完成 ===')
    log.info(f'清理前: {total_before} 源 → 清理后: {total_after} 源')
    if not args.clean_only:
        log.info(f'升级为 green: {promoted} 个')

    # 统计最终状态
    from collections import Counter
    statuses = Counter()
    for rs in data['rulesets']:
        for r in rs['rules']:
            statuses[r['health']['status']] += 1
    for s, c in statuses.most_common():
        log.info(f'  {s}: {c}')


if __name__ == '__main__':
    main()
