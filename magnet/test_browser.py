"""Test browser rendering on JS-challenge sites."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_parser.ai_parser import LocalHeuristicParser
from crawler.extractor import MagnetExtractor
from bs4 import BeautifulSoup

SITES = [
    {
        'site': {'origin': 'https://btso.cc', 'name': 'btso.cc'},
        'search': {'request_template': '/search?q={query}', 'parse_metadata': {'selectors': {}}},
    },
    {
        'site': {'origin': 'https://btdb.to', 'name': 'btdb.to'},
        'search': {'request_template': '/search?q={query}', 'parse_metadata': {'selectors': {}}},
    },
    {
        'site': {'origin': 'https://extratorrent.ag', 'name': 'extratorrent.ag'},
        'search': {'request_template': '/search?q={query}', 'parse_metadata': {'selectors': {}}},
    },
    {
        'site': {'origin': 'https://btbtt12.com', 'name': 'btbtt12.com'},
        'search': {'request_template': '/search?q={query}', 'parse_metadata': {'selectors': {}}},
    },
]

BAITS = ['Ubuntu', 'Interstellar', 'Big Buck Bunny']

for source in SITES:
    url = source['site']['origin']
    search_path = source['search']['request_template']
    print(f"\n{'='*60}")
    print(f"Testing: {url}")

    parser = LocalHeuristicParser(url)
    for bait in BAITS:
        test_url = url.rstrip('/') + search_path.replace('{query}', bait)
        print(f"  Browser rendering: {test_url}")
        html = parser.get_browser_dom(test_url)
        if not html:
            print(f"  FAILED - no HTML returned")
            continue

        soup = BeautifulSoup(html, 'lxml')
        title = soup.title.string if soup.title else 'N/A'
        text_len = len(soup.get_text(strip=True))
        magnets = soup.find_all('a', href=lambda h: h and 'magnet:' in h)
        print(f"  Title: {title[:80]}")
        print(f"  HTML length: {len(html)}, text length: {text_len}")
        print(f"  Magnet links found: {len(magnets)}")

        if magnets:
            for m in magnets[:3]:
                href = m.get('href', '')
                magnet_text = m.get_text(strip=True)[:50]
                print(f"    magnet: {href[:80]}...")
                print(f"    text: {magnet_text}")
        else:
            parser._soup = soup
            rules = parser.parse(html)
            sels = rules.get('selectors', {})
            print(f"  Heuristic selectors: {sels}")

            extractor = MagnetExtractor({**source, 'search': {**source['search'], 'parse_metadata': {'selectors': sels}}})
            results = extractor.extract_magnets(html, base_url=url)
            print(f"  Extracted magnets: {len(results)}")
            if results:
                for r in results[:3]:
                    print(f"    {r.get('title', '')[:60]} -> {r.get('magnet', '')[:60]}")

        if magnets or (text_len > 1000):
            break

    time.sleep(2)
