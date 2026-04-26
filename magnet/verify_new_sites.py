"""Verify 6v520.com and seedhub.cc extraction."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from crawler.extractor import MagnetExtractor
import json

with open('../sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for rs in data['rulesets']:
    for r in rs['rules']:
        name = r['site']['name']
        if name not in ('6v520.com', 'seedhub.cc'):
            continue

        print(f"\n{'='*60}")
        print(f"Testing: {name}")
        print(f"Origin: {r['site']['origin']}")

        extractor = MagnetExtractor(r)

        queries = ['Avatar', 'Interstellar'] if name == '6v520.com' else []
        for q in queries:
            print(f"\n  Search: {q}")
            results = extractor.search(q, limit=5)
            print(f"  Results: {len(results)}")
            for r2 in results[:2]:
                t = r2.get('title', '')[:50]
                m = r2.get('magnet', '')[:80]
                print(f"    {t}")
                print(f"    {m}")

        if name == 'seedhub.cc':
            print(f"\n  Browse: {r['site']['origin']}/categories/1/movies/")
            extractor.search_path = '/categories/1/movies/'
            extractor.search_method = 'GET'
            extractor.search_body = None
            results = extractor.search('', limit=10)
            print(f"  Results: {len(results)}")
            for r2 in results[:3]:
                t = r2.get('title', '')[:50]
                m = r2.get('magnet', '')[:80]
                print(f"    {t}")
                print(f"    {m}")

        time.sleep(1)

print(f"\nTotal rules: {data['meta']['total_rules']}")
