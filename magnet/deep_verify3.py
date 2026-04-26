#!/usr/bin/env python3
"""
Deep Verify v3 — 针对性二次验证
==================================
针对 PROMISING/NEEDS_PATH/REDIRECT_MAGNET/UNKNOWN 的源，
用从首页提取的实际搜索路径重试搜索。

同时用从报告中发现的真实搜索路径进行二次尝试。
"""

import sys
import os
import re
import json
import time
import logging
import urllib.parse
from collections import Counter
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
REPORT2_FILE = os.path.join(ROOT_DIR, 'deep_verify_report2.json')

HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')


def create_session():
    import cloudscraper
    sess = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
    )
    sess.headers.update({
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
    })
    return sess


def safe_get(session, url, timeout=15):
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        resp.encoding = resp.apparent_encoding or 'utf-8'
        return resp.text, resp.url, resp.status_code, None
    except Exception as e:
        return '', url, 0, str(e)[:200]


def extract_magnets(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    results = []
    seen = set()

    for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
        m = re.search(r'btih:([0-9A-Fa-f]{32,40})', a['href'], re.I)
        if m:
            hh = m.group(1).upper()
            if hh in seen:
                continue
            seen.add(hh)
            title = a.get_text(strip=True)[:80]
            results.append({'title': title, 'hash': hh[:16], 'magnet': a['href'][:150]})

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

    if not results:
        text = soup.get_text()
        for m in HASH_RE.finditer(text):
            hh = m.group(0).upper()
            if hh not in seen:
                seen.add(hh)
                results.append({'title': f'Hash {hh[:8]}...', 'hash': hh[:16], 'magnet': f'magnet:?xt=urn:btih:{hh}'})

    return results


# 从第一轮报告中提取的真实搜索路径模式
REAL_PATTERNS = [
    # clb12.xyz: /s/{base64_query}  → 需要base64编码
    ('clb12.xyz', lambda q, base: base + '/s/' + __import__('base64').b64encode(q.encode()).decode()),
    # ciliri.shop/jzcilifa1.shop: /list.html?key={query}
    ('ciliri.shop', lambda q, base: base + '/list.html?key=' + __import__('urllib.parse').quote(q)),
    ('jzcilifa1.shop', lambda q, base: base + '/list.html?key=' + __import__('urllib.parse').quote(q)),
    # clg.im: /search?word={query}&sort=time
    ('clg.im', lambda q, base: base + '/search?word=' + __import__('urllib.parse').quote(q) + '&sort=time'),
    # 0cili.nl / wuji.me: /search?q={query}  (已测但可能需跟base)
    ('0cili.nl', lambda q, base: base + '/search?q=' + __import__('urllib.parse').quote(q)),
    ('wuji.me', lambda q, base: base + '/search?q=' + __import__('urllib.parse').quote(q)),
    # torrentkitty.de: 典型路径 /search/text/{query}
    ('torrentkitty.de', lambda q, base: base + '/search/text/' + __import__('urllib.parse').quote(q)),
    # torrent2.top / cilitiantang.club / cilishenqi.me: WordPress站点 /?s={query}
    ('torrent2.top', lambda q, base: base + '/?s=' + __import__('urllib.parse').quote(q)),
    ('cilitiantang.club', lambda q, base: base + '/?s=' + __import__('urllib.parse').quote(q)),
    ('cilishenqi.me', lambda q, base: base + '/?s=' + __import__('urllib.parse').quote(q)),
    # btmayi.top: 可能有 /search?q=
    ('btmayi.top', lambda q, base: base + '/search?q=' + __import__('urllib.parse').quote(q)),
    # cilimao.de / cilimao.lol: 磁力猫系列
    ('cilimao.de', lambda q, base: base + '/search?word=' + __import__('urllib.parse').quote(q)),
    # btfox.cyou / bt43.foxs.vip: 磁力狐
    ('btfox.cyou', lambda q, base: base + '/search?word=' + __import__('urllib.parse').quote(q)),
    ('bt43.foxs.vip', lambda q, base: base + '/search?word=' + __import__('urllib.parse').quote(q)),
    # cilihezi.cn: 磁力盒子
    ('cilihezi.cn', lambda q, base: base + '/search?keyword=' + __import__('urllib.parse').quote(q)),
    # so5.xingqiu.icu: 磁力星球
    ('so5.xingqiu.icu', lambda q, base: base + '/search?keyword=' + __import__('urllib.parse').quote(q)),
    # ru.cilido.top: BT搜索
    ('cilido.top', lambda q, base: base + '/search?keyword=' + __import__('urllib.parse').quote(q)),
    # btsow.icu: BTSOW
    ('btsow.icu', lambda q, base: base + '/search?q=' + __import__('urllib.parse').quote(q)),
    # btbtt10.com: BT之家
    ('btbtt10.com', lambda q, base: base + '/search?keyword=' + __import__('urllib.parse').quote(q)),
]


def get_base_url(origin):
    parsed = urllib.parse.urlparse(origin.rstrip('/'))
    return f'{parsed.scheme}://{parsed.netloc}'


def try_targeted_search(session, origin, query='Inception'):
    """根据域名特征尝试搜索"""
    import base64
    base = get_base_url(origin)
    domain = urllib.parse.urlparse(origin).netloc.replace('www.', '').replace('http://', '').replace('https://', '')

    # 构建URL列表
    q = query
    q_enc = urllib.parse.quote(q)
    q_b64 = base64.b64encode(q.encode()).decode().rstrip('=')

    urls = []
    for pattern_domain, url_fn in REAL_PATTERNS:
        if pattern_domain in domain:
            try:
                urls.append(url_fn(q, base))
            except Exception:
                pass

    # 如果没有匹配到特定模式，用通用路径
    if not urls:
        urls = [
            base + '/search?word=' + q_enc,
            base + '/search?keyword=' + q_enc,
            base + '/search?q=' + q_enc,
            base + '/s/' + q_enc,
            base + '/s/' + q_b64,
            base + '/list.html?key=' + q_enc,
            base + '/?s=' + q_enc,
            base + '/search/' + q_enc,
            base + '/so/' + q_enc,
        ]

    for url in urls:
        log.info(f'    尝试: {url[:80]}')
        html, final_url, status, err = safe_get(session, url, timeout=12)
        if err or status == 0 or status >= 400:
            log.info(f'      失败: status={status}, err={err[:50] if err else ""}')
            continue
        if len(html) < 200:
            log.info(f'      页面太小: {len(html)} bytes')
            continue

        magnets = extract_magnets(html)
        if magnets:
            log.info(f'      ★ 命中: {len(magnets)} magnets')
            return {
                'ok': True,
                'magnets': len(magnets),
                'samples': magnets[:5],
                'search_url': url,
                'final_url': final_url,
            }
        else:
            log.info(f'      未提取到磁力 ({len(html)} bytes)')

    return None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--targets', nargs='*', help='指定域名进行验证')
    parser.add_argument('--verdicts', nargs='*', default=['PROMISING', 'NEEDS_PATH', 'UNKNOWN'],
                        help='验证哪些判定类型的源')
    args = parser.parse_args()

    session = create_session()
    report = []

    # 加载第一轮报告
    with open(REPORT_FILE, 'r', encoding='utf-8') as f:
        first_report = json.load(f)

    # 筛选目标
    targets = []
    for r in first_report:
        if args.targets:
            if any(t in r['name'] or t in r['origin'] for t in args.targets):
                targets.append(r)
        elif r['verdict'] in args.verdicts:
            targets.append(r)

    total = len(targets)
    log.info(f'二轮验证: {total} 个源 (verdicts={args.verdicts})')
    log.info('=' * 70)

    for idx, t in enumerate(targets):
        name = t['name']
        origin = t['origin']
        log.info(f'\n[{idx+1}/{total}] {name} ({origin})')
        log.info(f'  前次判定: {t["verdict"]} — {t["reason"]}')

        if t.get('search_hints'):
            log.info(f'  搜索提示: {t["search_hints"]}')
        if t.get('links_sample'):
            for lnk in t['links_sample'][:5]:
                log.info(f'  链接: {lnk["text"][:40]} -> {lnk["href"][:60]}')

        # 尝试搜索
        result = try_targeted_search(session, origin, 'Inception')
        if not result:
            result = try_targeted_search(session, origin, 'Avatar')

        if result:
            log.info(f'  >>> 最终: WORKING — {result["magnets"]} magnets via {result["search_url"][:60]}')
            report.append({
                'name': name,
                'origin': origin,
                'first_verdict': t['verdict'],
                'second_verdict': 'WORKING',
                'magnets_found': result['magnets'],
                'search_url': result['search_url'],
                'samples': result['samples'],
            })
        else:
            log.info(f'  >>> 最终: {t["verdict"]} — 二轮搜索仍未命中')
            report.append({
                'name': name,
                'origin': origin,
                'first_verdict': t['verdict'],
                'second_verdict': t['verdict'],
                'magnets_found': 0,
            })

        time.sleep(0.5)

    # 保存报告
    with open(REPORT2_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    log.info(f'\n报告已保存到 {REPORT2_FILE}')

    # 统计
    working = [r for r in report if r['second_verdict'] == 'WORKING']
    still_yellow = [r for r in report if r['second_verdict'] != 'WORKING']

    log.info(f'\n=== 二轮验证结果 ===')
    log.info(f'  WORKING: {len(working)}')
    log.info(f'  仍待验证: {len(still_yellow)}')

    if working:
        log.info('\n  --- 新确认可用 ---')
        for r in working:
            log.info(f'    {r["name"]}: {r["magnets_found"]} magnets ({r["search_url"][:60]})')

    if still_yellow:
        log.info('\n  --- 仍待验证 ---')
        for r in still_yellow:
            log.info(f'    {r["name"]}: {r["first_verdict"]}')


if __name__ == '__main__':
    main()
