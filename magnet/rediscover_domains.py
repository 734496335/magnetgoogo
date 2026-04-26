#!/usr/bin/env python3
"""
P2: Domain Rediscovery Tool.
For each gray/unreachable source, probe common domain variations
to find if the site has moved to a new address.
"""

import json
import os
import sys
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

GRAY_BRANDS = [
    {
        'name': 'btsow.com',
        'brand': 'btsow',
        'alternatives': [
            'https://btsow.com',
            'https://www.btsow.com',
            'https://btsow.one',
            'https://btsow.xyz',
            'https://btsow.cc',
            'https://btsow.fun',
            'https://btosow.online',
        ],
    },
    {
        'name': 'limetorrents.cc',
        'brand': 'limetorrents',
        'alternatives': [
            'https://limetorrents.cc',
            'https://www.limetorrents.cc',
            'https://limetorrents.info',
            'https://www.limetorrents.info',
            'https://limetorrents.lol',
            'https://limetorrents.pro',
            'https://limetorrents.fun',
            'https://www.limetorrents.fun',
        ],
    },
    {
        'name': 'kickasstorrents.bz',
        'brand': 'kickasstorrents',
        'alternatives': [
            'https://kickasstorrents.bz',
            'https://kickasstorrents.to',
            'https://kickasstorrents.cr',
            'https://katcr.co',
            'https://kat.sx',
            'https://kickass.to',
            'https://kat.am',
            'https://kickasstorrents.id',
            'https://kickass.cd',
        ],
    },
    {
        'name': 'cilimao.com',
        'brand': 'cilimao',
        'alternatives': [
            'https://cilimao.com',
            'https://www.cilimao.com',
            'https://cilimao.one',
            'https://cilimao.xyz',
            'https://cilimao.cc',
            'https://cilimao.me',
            'https://cili.ma',
        ],
    },
    {
        'name': 'btfans.com',
        'brand': 'btfans',
        'alternatives': [
            'https://btfans.com',
            'https://www.btfans.com',
            'https://btbtfans.com',
            'https://ebtfans.com',
        ],
    },
    {
        'name': 'legacy-site.pw',
        'brand': 'legacy-site',
        'alternatives': [],
    },
]

SEARCH_TEST_QUERIES = {
    'btsow': '/search/Inception',
    'limetorrents': '/search/all/Inception/',
    'kickasstorrents': '/usearch/Inception/',
    'cilimao': '/search?q=Inception',
    'btfans': '/search?q=Inception',
}


def probe_url(url, timeout=10):
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        return resp.status_code, resp.url, len(resp.text), resp.text
    except requests.exceptions.Timeout:
        return None, None, 0, ''
    except requests.exceptions.ConnectionError:
        return None, None, 0, ''
    except Exception:
        return None, None, 0, ''


def main():
    print("=" * 60)
    print("  P2: Domain Rediscovery for Gray Sources")
    print("=" * 60)

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    existing_rules = {}
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            existing_rules[r['site']['name']] = r

    found = []

    for brand_info in GRAY_BRANDS:
        brand = brand_info['brand']
        name = brand_info['name']
        alternatives = brand_info['alternatives']
        search_path = SEARCH_TEST_QUERIES.get(brand, '/search?q=Inception')

        print(f"\n{'='*50}")
        print(f"Brand: {brand} (original: {name})")
        print(f"Probing {len(alternatives)} alternative domains...")

        for alt_url in alternatives:
            print(f"  {alt_url}: ", end='')
            status, final_url, html_len, html = probe_url(alt_url, timeout=10)

            if status is None:
                print("UNREACHABLE")
                continue

            print(f"HTTP {status}  len={html_len}  final={final_url[:40] if final_url else 'N/A'}")

            if status == 200 and html_len > 500:
                soup = BeautifulSoup(html, 'lxml')
                title = soup.title.string[:60] if soup.title else 'N/A'
                magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))

                is_torrent_site = bool(magnets) or any(kw in html.lower() for kw in ['torrent', 'magnet', '种子', '磁力'])
                is_parking = any(kw in html.lower() for kw in ['domain for sale', 'parking', 'buy this domain'])

                print(f"    title: {title}")
                print(f"    magnets: {len(magnets)}  torrent_kw: {is_torrent_site}  parking: {is_parking}")

                if is_torrent_site and not is_parking:
                    test_url = alt_url.rstrip('/') + search_path
                    print(f"    testing search: {test_url}")
                    s_status, _, s_len, s_html = probe_url(test_url, timeout=10)
                    if s_status == 200 and s_len > 200:
                        s_soup = BeautifulSoup(s_html, 'lxml')
                        s_magnets = s_soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
                        hash_in_urls = len([a for a in s_soup.find_all('a', href=True) if '/search' not in a['href'] and len(a['href']) > 20])
                        print(f"    search OK: HTTP {s_status}  magnets={len(s_magnets)}  links={hash_in_urls}")
                        if s_magnets or hash_in_urls > 3:
                            found.append({
                                'original_name': name,
                                'brand': brand,
                                'new_origin': alt_url,
                                'search_path': search_path,
                                'magnets_on_search': len(s_magnets),
                            })
                            print(f"    >>> FOUND NEW DOMAIN: {alt_url}")
            time.sleep(0.3)

    print(f"\n{'='*60}")
    print(f"  DOMAIN REDISCOVERY RESULTS")
    print(f"{'='*60}")
    print(f"  Found {len(found)} new domains:")
    for f in found:
        print(f"    {f['original_name']} -> {f['new_origin']} ({f['magnets_on_search']} magnets)")
        if f['original_name'] in existing_rules:
            rule = existing_rules[f['original_name']]
            old_origin = rule['site']['origin']
            rule['site']['origin'] = f['new_origin']
            rule['health']['status'] = 'yellow'
            rule['health']['status_detail'] = 'ok'
            rule['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()
            rule['health']['note'] = f'Domain rediscovered: {old_origin} -> {f["new_origin"]}'
            print(f"    Updated sources.json")

    if found:
        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n  Sources saved to {SOURCES_FILE}")
    else:
        print("  No new domains found for any gray sources.")

    print("=" * 60)


if __name__ == '__main__':
    main()
