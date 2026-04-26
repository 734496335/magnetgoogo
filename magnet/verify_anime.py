import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawler.extractor import MagnetExtractor
import json

with open('../sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for rs in data['rulesets']:
    for r in rs['rules']:
        if r['site']['name'] == 'animetosho.org':
            e = MagnetExtractor(r)
            for q in ['One Piece', 'Naruto', 'Bleach']:
                results = e.search(q, limit=5)
                print(f'{q}: {len(results)} results')
                for r2 in results[:2]:
                    t = r2.get('title', '')[:50]
                    m = r2.get('magnet', '')[:60]
                    print(f'  {t} -> {m}')
            break
