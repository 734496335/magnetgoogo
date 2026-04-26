"""Update health status_detail based on probe analysis."""
import json, os

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')

UPDATES = {
    'btso.cc':           {'status_detail': 'waf', 'note': 'FingerprintJS browser fingerprint gate, headless Chrome cannot pass (ww17.btso.cc)'},
    'btdb.to':           {'status_detail': 'waf', 'note': 'FingerprintJS browser fingerprint gate (ww16.btdb.to)'},
    'extratorrent.ag':   {'status_detail': 'waf', 'note': 'FingerprintJS browser fingerprint gate (ww16.extratorrent.ag)'},
    'btbtt12.com':       {'status_detail': 'waf', 'note': 'JS anti-bot redirect chain, sometimes redirects to google'},
    'btcake.com':        {'status_detail': 'waf', 'note': 'JS anti-bot redirect chain (same infrastructure as btbtt12.com)'},
    'cilimao.com':       {'status_detail': 'expired', 'note': 'JS redirect to /lander page, likely parked/expired domain'},
    'verycd.com':        {'status_detail': 'parsing_failed', 'note': 'Search API returns 405 Method Not Allowed (Aliyun CDN blocked)'},
    'bitport.io':        {'status_detail': 'parsing_failed', 'note': 'Cloud torrent downloader, not a magnet search engine'},
    'dummy-site.com':    {'status_detail': '404', 'note': 'Placeholder/test entry, not a real site'},
}

with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

for ruleset in data.get('rulesets', []):
    for rule in ruleset.get('rules', []):
        name = rule['site']['name']
        if name in UPDATES:
            update = UPDATES[name]
            rule['health']['status_detail'] = update['status_detail']
            rule['health']['note'] = update['note']

with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Updated health status_detail for:")
for name, upd in UPDATES.items():
    print(f"  {name}: {upd['status_detail']}")
