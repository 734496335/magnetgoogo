import json, hashlib, sys
from datetime import datetime, timezone
from collections import OrderedDict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

src = r'D:\lpproduct\magnet\sources.json'
with open(src, 'r', encoding='utf-8') as f:
    data = json.load(f)

rules = data['rulesets'][0]['rules']
existing = {}
for rule in rules:
    origin = rule['site']['origin'].split('://', 1)[-1].split('/', 1)[0].lower().removeprefix('www.')
    existing[origin] = rule

now = datetime.now(timezone.utc).isoformat()
added = 0

dh0_items = [
    {'brand': '磁力狗', 'url': 'https://clg.im', 'title': '磁力狗'},
    {'brand': '老王磁力', 'url': 'https://laowangso.com', 'title': '老王磁力'},
    {'brand': '磁力狐', 'url': 'https://bt43.foxs.vip', 'title': '磁力狐'},
    {'brand': '磁力星球', 'url': 'https://www.cilixingqiu.net', 'title': '磁力星球'},
    {'brand': '磁力猫', 'url': 'https://www.cilimao.lol', 'title': '磁力猫'},
    {'brand': '磁力熊猫', 'url': 'https://soxiongmao.top', 'title': '磁力熊猫'},
    {'brand': '磁力链', 'url': 'https://cililian.one', 'title': '磁力链'},
    {'brand': '天堂磁力', 'url': 'https://www.tiantangcili.net', 'title': '天堂磁力'},
    {'brand': '无极磁链', 'url': 'https://0cili.nl', 'title': '无极磁链'},
]

for item in dh0_items:
    domain = item['url'].split('://', 1)[-1].split('/', 1)[0].lower().removeprefix('www.')
    if domain in existing:
        continue
    rule = {
        'id': hashlib.md5(item['url'].encode()).hexdigest()[:12],
        'site': {
            'name': domain,
            'origin': item['url'].rstrip('/'),
            'countries': ['korea'],
            'brand': item['brand'],
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
            'diagnosis': '导航站dh0.cn发现候选，待自动验证',
        },
    }
    rules.append(rule)
    existing[domain] = rule
    added += 1
    print(f'  + {domain} ({item["brand"]})')

data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
data['generated_at'] = now
with open(src, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'added={added}')
