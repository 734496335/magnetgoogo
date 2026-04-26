#!/usr/bin/env python3
"""
P1-CN: Discover + verify China-mainland accessible magnet search sources.
Sources extracted from Baidu search results (2026-04).
"""
import json
import os
import sys
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

CANDIDATES = [
    {'name': 'cilimao.biz', 'origin': 'https://cilimao.biz', 'search': '/search?q={query}'},
    {'name': 'cltt.me', 'origin': 'https://cltt.me', 'search': '/search?q={query}'},
    {'name': 'cilitiantang.vip', 'origin': 'https://www.cilitiantang.vip', 'search': '/search?q={query}'},
    {'name': 'cilijun.com', 'origin': 'https://cilijun.com', 'search': '/search/{query}/1/0/0.html'},
    {'name': 'soucili.org', 'origin': 'https://www.soucili.org', 'search': '/search?q={query}'},
    {'name': 'soucili.cc', 'origin': 'https://www.soucili.cc', 'search': '/search?q={query}'},
    {'name': 'cilihezi.com', 'origin': 'https://cilihezi.com', 'search': '/search?q={query}'},
    {'name': 'btcat.bid', 'origin': 'https://www.btcat.bid', 'search': '/search?q={query}'},
    {'name': 'souzhongzi.com', 'origin': 'https://souzhongzi.com', 'search': '/search?q={query}'},
    {'name': 'zhongziso.in', 'origin': 'https://www.zhongziso.in', 'search': '/search?q={query}'},
    {'name': 'cili5.net', 'origin': 'https://www.cili5.net', 'search': '/search?q={query}'},
    {'name': 'cilishenqi.me', 'origin': 'https://cilishenqi.me', 'search': '/search?q={query}'},
    {'name': 'wuqianaa.xyz', 'origin': 'https://wuqianaa.xyz', 'search': '/search?q={query}'},
    {'name': 'sbt2211.top', 'origin': 'https://sbt2211.top', 'search': '/search?q={query}'},
    {'name': 'cld53.buzz', 'origin': 'https://cld53.buzz', 'search': '/search?q={query}'},
    {'name': 'laowangbi.top', 'origin': 'https://laowangbi.top', 'search': '/search?q={query}'},
    {'name': 'clm281.buzz', 'origin': 'https://clm281.buzz', 'search': '/search?q={query}'},
    {'name': 'bt1207bi.top', 'origin': 'https://bt1207bi.top', 'search': '/search?q={query}'},
    {'name': 'bashi5.com', 'origin': 'https://bashi5.com', 'search': '/search?q={query}'},
    {'name': '12580.org', 'origin': 'https://12580.org', 'search': '/search?q={query}'},
    {'name': 'cldq.cc', 'origin': 'https://cldq.cc', 'search': '/search?q={query}'},
    {'name': 'cilisousuoyinqng.com.cn', 'origin': 'https://cilsousuoyinqng.com.cn', 'search': '/search?q={query}'},
    {'name': 'ezhentang.com', 'origin': 'https://ezhentang.com', 'search': '/search?q={query}'},
    {'name': 'cilimao.biz', 'origin': 'https://cilimao.biz', 'search': '/search?q={query}'},
    {'name': 'meilizixun.com', 'origin': 'https://meilizixun.com', 'search': '/search?q={query}'},
    {'name': 'btfox', 'origin': 'https://www.cili5.net', 'search': '/search?q={query}'},
    {'name': 'cilihezi.top', 'origin': 'https://www.cilihezi.top', 'search': '/search?q={query}'},
    {'name': 'so2.bz', 'origin': 'https://so2.bz', 'search': '/search?q={query}'},
    {'name': 'cilibra', 'origin': 'https://www.cilibra.com', 'search': '/search?q={query}'},
]

TEST_QUERIES = ['Inception', 'Big Buck Bunny', 'Interstellar']


def make_rule_id(origin):
    return hashlib.md5(origin.encode()).hexdigest()[:12]


def probe_candidate(cand):
    origin = cand['origin']
    search_path = cand['search']

    for query in TEST_QUERIES:
        url = origin.rstrip('/') + search_path.replace('{query}', query)
        try:
            resp = requests.get(url, timeout=12, headers=HEADERS, allow_redirects=True)
        except requests.exceptions.Timeout:
            return {'status': 'unreachable', 'error': 'Timeout'}
        except requests.exceptions.ConnectionError:
            return {'status': 'unreachable', 'error': 'DNS/Connection failed'}
        except Exception as e:
            return {'status': 'error', 'error': str(e)[:60]}

        if resp.status_code == 404:
            continue
        if resp.status_code >= 500:
            continue
        if resp.status_code != 200:
            continue

        html = resp.text
        final_url = resp.url

        if len(html) < 300:
            continue

        soup = BeautifulSoup(html, 'lxml')

        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        if magnets:
            sample_title = ''
            for m in magnets[:1]:
                parent = m.parent
                for _ in range(3):
                    if parent:
                        for a in parent.find_all('a', href=True):
                            txt = a.get_text(strip=True)
                            if txt and 'magnet:' not in a['href'] and len(txt) > 3:
                                sample_title = txt[:80]
                                break
                        if sample_title:
                            break
                        parent = parent.parent
            return {
                'status': 'ok',
                'magnets_found': len(magnets),
                'sample_magnet': magnets[0].get('href', '')[:80],
                'sample_title': sample_title,
                'query': query,
                'final_url': final_url,
                'html_len': len(html),
            }

        import re
        hash_re = re.compile(r'[0-9A-Fa-f]{40}')
        hashes_in_urls = set()
        for a in soup.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if m:
                hashes_in_urls.add(m.group(1))
        if len(hashes_in_urls) >= 3:
            titles = []
            for a in soup.find_all('a', href=True):
                m = hash_re.search(a['href'])
                if m:
                    titles.append(a.get_text(strip=True)[:60])
                    if len(titles) >= 1:
                        break
            return {
                'status': 'ok_hash',
                'magnets_found': len(hashes_in_urls),
                'sample_title': titles[0] if titles else '',
                'query': query,
                'final_url': final_url,
                'html_len': len(html),
            }

        title_text = soup.title.string[:60] if soup.title else ''
        if 'just a moment' in title_text.lower() or 'cloudflare' in html.lower()[:2000]:
            return {'status': 'waf', 'error': 'Cloudflare challenge'}

    return {'status': 'parsing_failed', 'error': 'No magnets in search results'}


def main():
    print("=" * 60)
    print("  P1-CN: Discover China-Accessible Magnet Sources")
    print("=" * 60)

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    existing = set()
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            existing.add(r['site']['origin'])

    print(f"\nExisting: {len(existing)}  Candidates: {len(CANDIDATES)}\n")

    ok_results = []
    for i, cand in enumerate(CANDIDATES):
        if cand['origin'] in existing:
            continue
        name = cand['name']
        print(f"[{i+1}/{len(CANDIDATES)}] {name} ({cand['origin']})")

        result = probe_candidate(cand)
        st = result['status']

        if st in ('ok', 'ok_hash'):
            ok_results.append((cand, result))
            print(f"  OK - {result['magnets_found']} magnets (query: {result.get('query', '')})")
            print(f"       sample: {result.get('sample_title', '')}")
        elif st == 'waf':
            print(f"  WAF - {result.get('error', '')}")
        elif st == 'unreachable':
            print(f"  {st.upper()} - {result.get('error', '')}")
        else:
            print(f"  {st.upper()} - {result.get('error', '')}")

        time.sleep(0.5)

    ruleset = data['rulesets'][0] if data.get('rulesets') else None
    if not ruleset:
        ruleset = {'ruleset_id': 'base', 'priority': 1, 'max_sources_per_search': 10, 'rules': []}
        data['rulesets'].append(ruleset)

    for cand, result in ok_results:
        rule = {
            'id': make_rule_id(cand['origin']),
            'site': {'name': cand['name'], 'origin': cand['origin']},
            'capabilities': {'supports_search': True, 'supports_detail': False},
            'search': {
                'request_template': cand['search'],
                'timeout_ms': 12000,
                'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                'requires_waf_bypass': False,
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
            'quality': {'score': 70, 'tags': ['追新极客']},
            'health': {
                'status': 'green',
                'status_detail': 'ok',
                'last_checked_at': datetime.now(timezone.utc).isoformat(),
                'magnets_found': result['magnets_found'],
                'sample_title': result.get('sample_title', ''),
            },
        }
        ruleset['rules'].append(rule)
        print(f"  Added to sources.json: {cand['name']}")

    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))

    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  CHINA SOURCE DISCOVERY REPORT")
    print(f"{'='*60}")
    print(f"  Candidates probed: {len(CANDIDATES)}")
    print(f"  NEW OK: {len(ok_results)}")
    for c, r in ok_results:
        print(f"    + {c['name']} ({r['magnets_found']} magnets)")
    print(f"  Total sources now: {data['meta']['total_rules']}")
    print("=" * 60)


if __name__ == '__main__':
    main()
