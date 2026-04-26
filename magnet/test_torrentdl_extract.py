"""Test torrentdownload.info extraction with new hash-based extractor."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler.extractor import MagnetExtractor
import json

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)

for rs in data['rulesets']:
    for r in rs['rules']:
        if r['site']['name'] == 'torrentdownload.info':
            extractor = MagnetExtractor(r)
            for query in ['Ubuntu', 'Big Buck Bunny', 'Interstellar']:
                print(f'\nQuery: {query}')
                print(f'URL: {extractor.build_search_url(query)}')
                results = extractor.search(query, limit=5)
                print(f'Results: {len(results)}')
                for r in results[:3]:
                    print(f'  title: {r["title"][:60]}')
                    print(f'  magnet: {r["magnet"][:80]}')
                    print()
            break
