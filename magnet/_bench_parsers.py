"""
Parser Bake-off — 实证比较多个候选 HTML 解析器在真实 magnet 站上的表现。

候选：
  A. 当前 v1: LocalHeuristicParser (启发式 selector 回退)
  B. AutoScraper (alirezamika) — 样本驱动 wrapper 归纳
  C. Trafilatura — 主体内容提取（作为参考基线）
  D. 纯正则兜底：HASH_RE on full text

测试方法：
  1. 拿一组 green 源（已知 sample_title + sample.magnet 存在）
  2. 用 Scrapling Fetcher 拉首页 + 拉一次搜索结果页
  3. 让每个候选尝试提取 magnet 列表
  4. 看：
     - 找到的 magnet/hash 数量
     - 是否包含已知 sample.magnet
     - 与 BeautifulSoup baseline 的差距

Usage:
  python magnet/_bench_parsers.py --limit 5            # 只测 5 个 green 源
  python magnet/_bench_parsers.py --query Inception    # 用这个关键词测搜索页
"""
import sys
import os
import re
import json
import time
import argparse
import logging
from urllib.parse import quote

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SOURCES = os.path.join(ROOT, 'sources.json')
HASH_RE = re.compile(r'\b[0-9a-fA-F]{40}\b')

# ── Parser A: current v1 heuristic ──────────────────────────────────
def parse_v1_heuristic(html, base_url=''):
    """Mimic crawler/extractor.py's hash-URL fallback (the part that actually works most)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    found = set()
    # magnet anchors
    for a in soup.find_all('a', href=True):
        h = a['href']
        if h.startswith('magnet:'):
            m = re.search(r'btih:([0-9a-fA-F]{32,40})', h, re.I)
            if m:
                found.add(m.group(1).upper())
    # hash-bearing URLs
    for a in soup.find_all('a', href=True):
        m = HASH_RE.search(a['href'])
        if m:
            found.add(m.group(0).upper())
    return {'method': 'v1_heuristic', 'count': len(found), 'hashes': list(found)[:5]}


# ── Parser B: AutoScraper ────────────────────────────────────────────
def parse_autoscraper(html, wanted_list, base_url=''):
    """Train AutoScraper on this single HTML with wanted_list (a known sample) and see what it extracts."""
    try:
        from autoscraper import AutoScraper
    except ImportError:
        return {'method': 'autoscraper', 'error': 'not installed'}
    try:
        scraper = AutoScraper()
        result = scraper.build(html=html, wanted_list=wanted_list)
        # Filter to magnet-like results: full magnet URIs or 40-char hashes
        magnets = set()
        hashes = set()
        for r in result or []:
            if not isinstance(r, str):
                continue
            if r.startswith('magnet:'):
                magnets.add(r[:120])
                m = re.search(r'btih:([0-9a-fA-F]{32,40})', r, re.I)
                if m:
                    hashes.add(m.group(1).upper())
            m = HASH_RE.search(r)
            if m:
                hashes.add(m.group(0).upper())
        return {
            'method': 'autoscraper',
            'count': len(hashes),
            'hashes': list(hashes)[:5],
            'magnets_full': len(magnets),
            'raw_total_results': len(result or []),
        }
    except Exception as e:
        return {'method': 'autoscraper', 'error': str(e)[:120]}


# ── Parser C: Trafilatura ────────────────────────────────────────────
def parse_trafilatura(html, base_url=''):
    """Trafilatura extracts main text; we then regex for hashes/magnets in that text."""
    try:
        import trafilatura
    except ImportError:
        return {'method': 'trafilatura', 'error': 'not installed'}
    try:
        text = trafilatura.extract(html, include_links=True, include_comments=False, output_format='txt') or ''
        # Trafilatura focuses on body content; we check for magnet/hash signals
        found_hashes = set(HASH_RE.findall(text))
        magnet_urls = re.findall(r'magnet:\?xt=urn:btih:[0-9a-fA-F]{32,40}[^\s]*', text)
        return {
            'method': 'trafilatura',
            'count': len(found_hashes),
            'hashes': [h.upper() for h in list(found_hashes)[:5]],
            'magnets_in_text': len(magnet_urls),
            'extracted_text_len': len(text),
        }
    except Exception as e:
        return {'method': 'trafilatura', 'error': str(e)[:120]}


# ── Parser D: full-text regex (lower bound) ─────────────────────────
def parse_regex_only(html, base_url=''):
    found_hashes = set(HASH_RE.findall(html))
    magnet_urls = re.findall(r'magnet:\?xt=urn:btih:[0-9a-fA-F]{32,40}', html)
    return {
        'method': 'regex_only',
        'count': len(found_hashes),
        'hashes': [h.upper() for h in list(found_hashes)[:5]],
        'magnets_in_html': len(magnet_urls),
    }


# ── Sample-driven harness ────────────────────────────────────────────
def fetch_html(url, timeout=15):
    """Use Scrapling Fetcher for TLS impersonation."""
    try:
        from scrapling.fetchers import Fetcher
        r = Fetcher.get(url, impersonate='chrome', timeout=timeout, retries=1, retry_delay=1)
        if r.status == 200:
            return str(r.html_content) if r.html_content else r.body.decode('utf-8', errors='replace')
    except Exception as e:
        log.info(f'  fetch err: {str(e)[:80]}')
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=8)
    ap.add_argument('--query', default='Inception', help='Search query to fetch')
    args = ap.parse_args()

    data = json.load(open(SOURCES, encoding='utf-8'))
    targets = []
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            h = r.get('health', {})
            if h.get('status') != 'green':
                continue
            sample_title = h.get('sample_title') or ''
            # Try to find an example magnet from sample field
            sample_magnet = ''
            sample = h.get('sample') or {}
            if isinstance(sample, dict):
                sample_magnet = sample.get('magnet') or ''
            if not sample_magnet:
                # Some rules may store last_magnet on the rule itself
                sample_magnet = r.get('sample', {}).get('magnet', '') if isinstance(r.get('sample'), dict) else ''
            search_path = (r.get('search', {}).get('request_template') or '/search?q={query}')
            origin = r.get('site', {}).get('origin', '')
            if not origin:
                continue
            targets.append({
                'origin': origin,
                'brand': r.get('site', {}).get('brand') or r.get('site', {}).get('name', '?'),
                'sample_title': sample_title,
                'sample_magnet': sample_magnet,
                'search_path': search_path,
            })
            if len(targets) >= args.limit:
                break
        if len(targets) >= args.limit:
            break

    log.info(f'\n{"=" * 100}')
    log.info(f'  Parser Bake-off — {len(targets)} green sources, query="{args.query}"')
    log.info(f'{"=" * 100}\n')

    rows = []
    for i, t in enumerate(targets, 1):
        url = t['origin'].rstrip('/') + t['search_path'].replace('{query}', quote(args.query))
        log.info(f'[{i}/{len(targets)}] {t["brand"]} | {url[:80]}')
        log.info(f'    sample_title="{t["sample_title"][:50]}"')
        log.info(f'    sample_magnet={"yes" if t["sample_magnet"] else "no"}')

        html = fetch_html(url)
        if not html:
            log.info('    SKIP: fetch failed')
            continue

        log.info(f'    HTML size: {len(html)} bytes')

        # Run all parsers
        wanted = [x for x in [t['sample_title'], t['sample_magnet']] if x]
        r_v1 = parse_v1_heuristic(html, base_url=url)
        r_as = parse_autoscraper(html, wanted_list=wanted, base_url=url) if wanted else {'method': 'autoscraper', 'error': 'no wanted_list (missing sample_title)'}
        r_tr = parse_trafilatura(html, base_url=url)
        r_re = parse_regex_only(html, base_url=url)

        for r in (r_v1, r_as, r_tr, r_re):
            err = r.get('error', '')
            cnt = r.get('count', 0)
            extra = ''
            if r['method'] == 'autoscraper':
                extra = f' (raw_results={r.get("raw_total_results", 0)})'
            elif r['method'] == 'trafilatura':
                extra = f' (text={r.get("extracted_text_len", 0)}b)'
            log.info(f'    {r["method"]:<14}: count={cnt}{extra}  {err[:60]}')

        rows.append({
            'brand': t['brand'],
            'origin': t['origin'],
            'url': url,
            'html_size': len(html),
            'sample_title': t['sample_title'],
            'had_sample_magnet': bool(t['sample_magnet']),
            'v1_heuristic': r_v1,
            'autoscraper': r_as,
            'trafilatura': r_tr,
            'regex_only': r_re,
        })
        time.sleep(0.3)

    # ── Final tally ──
    log.info(f'\n{"=" * 100}')
    log.info('  Aggregate (count = unique 40-char hashes found per page)')
    log.info(f'{"=" * 100}')
    log.info(f'{"brand":<25} {"v1":>4} {"autoscr":>8} {"trafil":>8} {"regex":>6}')
    log.info('-' * 60)
    for r in rows:
        log.info(f'{r["brand"][:25]:<25} '
                 f'{r["v1_heuristic"].get("count", 0):>4} '
                 f'{r["autoscraper"].get("count", "-"):>8} '
                 f'{r["trafilatura"].get("count", "-"):>8} '
                 f'{r["regex_only"].get("count", "-"):>6}')

    # Save report
    rf = os.path.join(os.path.dirname(__file__), '_bench_parsers_report.json')
    with open(rf, 'w', encoding='utf-8') as f:
        json.dump({'rows': rows, 'query': args.query, 'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S')}, f, indent=2, ensure_ascii=False)
    log.info(f'\nReport saved: {rf}')


if __name__ == '__main__':
    main()
