"""Update notes for WAF-flagged sites to reflect actual DNS pollution + GFW."""
import json, os

SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources.json')

NOTE_UPDATES = {
    'btso.cc': 'DNS pollution (ww17.btso.cc) + GFW connection reset, not a WAF issue',
    'btdb.to': 'DNS pollution (ww38.btdb.to) + GFW ERR_CONNECTION_RESET',
    'extratorrent.ag': 'DNS pollution + GFW blocked, unreachable from China mainland',
    'btbtt12.com': 'GFW blocked, JS anti-bot redirect, sometimes redirects to google',
    'btcake.com': 'GFW blocked, JS anti-bot redirect (same infrastructure as btbtt12.com)',
}

with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

for rs in data.get('rulesets', []):
    for rule in rs.get('rules', []):
        name = rule['site']['name']
        if name in NOTE_UPDATES:
            rule['health']['note'] = NOTE_UPDATES[name]
            if name in ('btso.cc', 'btdb.to', 'extratorrent.ag'):
                rule['health']['status'] = 'gray'
                rule['health']['status_detail'] = 'unreachable'

with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Updated notes for:")
for name in NOTE_UPDATES:
    print(f"  {name}")
