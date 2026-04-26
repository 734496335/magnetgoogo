import json
import hashlib
from datetime import datetime, timezone

src = r'D:\lpproduct\magnet\sources.json'
rep = r'D:\lpproduct\magnet\nav_site_crawler_report.json'

def norm(url: str) -> str:
    value = url.split('://', 1)[-1].split('/', 1)[0].lower()
    return value.removeprefix('www.')

with open(src, 'r', encoding='utf-8') as f:
    data = json.load(f)
with open(rep, 'r', encoding='utf-8') as f:
    report = json.load(f)

rules = data['rulesets'][0]['rules']
existing = {norm(rule['site']['origin']): rule for rule in rules}
country = report.get('country', 'korea')
now = datetime.now(timezone.utc).isoformat()
skip = set()
added = 0
updated = 0

for item in report.get('real_candidates', []):
    domain = norm(item['url'])
    if domain in skip:
        continue
    if domain in existing:
        rule = existing[domain]
        countries = rule['site'].setdefault('countries', [])
        if country not in countries:
            countries.append(country)
            updated += 1
        brand = item.get('brand', '')
        if brand and not rule['site'].get('brand'):
            rule['site']['brand'] = brand
        continue

    rule = {
        'id': hashlib.md5(item['url'].encode()).hexdigest()[:12],
        'site': {
            'name': domain,
            'origin': item['url'].rstrip('/'),
            'countries': [country],
            'brand': item.get('brand', ''),
        },
        'capabilities': {'supports_search': True, 'supports_detail': False},
        'search': {
            'request_template': '/?q={query}',
            'timeout_ms': 15000,
            'retries': {'max_attempts': 3, 'backoff_ms': 1000},
            'requires_waf_bypass': False,
            'requires_browser': False,
            'parse_metadata': {
                'selectors': {
                    'list_item': 'div.item',
                    'title': 'a[href]',
                    'magnet': 'a[href^="magnet:"]',
                    'size': 'span.size',
                    'date': 'span.date',
                }
            },
        },
        'quality': {'score': 55, 'tags': ['导航发现', '待验证']},
        'health': {
            'status': 'yellow',
            'status_detail': 'parsing_failed',
            'last_checked_at': now,
            'magnets_found': 0,
            'sample_title': item.get('title', '')[:80],
            'diagnosis': '导航站发现候选，待自动验证',
        },
    }
    rules.append(rule)
    existing[domain] = rule
    added += 1

data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
data['generated_at'] = now
with open(src, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'added={added} updated={updated}')
