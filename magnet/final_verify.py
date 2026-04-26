"""Final verification of 6v520.com and seedhub.cc."""
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
        if name != '6v520.com':
            continue

        print(f"Testing: {name}")
        extractor = MagnetExtractor(r)

        for q in ['Avatar', 'Inception', 'Thor']:
            print(f"\n  Search: {q}")
            results = extractor.search(q, limit=5)
            print(f"  Results: {len(results)}")
            for r2 in results[:3]:
                t = r2.get('title', '')[:50]
                m = r2.get('magnet', '')[:80]
                print(f"    {t}")
                print(f"    {m}")
            time.sleep(1)
