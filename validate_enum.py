import json
VALID = {'ok', 'healed', 'waf', '404', 'expired', 'unreachable', 'parsing_failed'}
with open('sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
all_ok = True
brand_warnings = 0
for rs in data['rulesets']:
    for r in rs['rules']:
        sd = r['health'].get('status_detail', '')
        st = r['health'].get('status', '')
        ok = sd in VALID
        tag = 'OK' if ok else 'INVALID'
        if not ok:
            all_ok = False
        print(f"{r['site']['name']:25s} status={st:6s} detail={sd:20s} {tag}")
        brand = r.get('site', {}).get('brand', '')
        if not brand:
            brand_warnings += 1
            print(f"  WARNING: missing brand")
print()
if brand_warnings:
    print(f"Brand warnings: {brand_warnings} source(s) without brand")
print("ALL VALID" if all_ok else "SOME INVALID")
