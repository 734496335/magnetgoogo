import sys
import os
import json
sys.path.append(os.path.join(os.getcwd(), 'magnet'))

from crawler.healer import Healer
from utils.sources_manager import SourcesManager

def repair_v2_campaign():
    print("=== Project Nebula - Healer V2 Campaign (Target 90%+) ===")
    
    sources_path = 'sources.json'
    if not os.path.exists(sources_path):
        print(f"Error: {sources_path} not found.")
        return
    
    with open(sources_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    rules = []
    for rs in data.get('rulesets', []):
        rules.extend(rs.get('rules', []))
    
    if not rules:
        print("No rules to process.")
        return

    healer = Healer()
    sm = SourcesManager()
    
    final_rules = []
    results = {
        'ok': 0,
        'healed': 0,
        'waf': 0,
        '404': 0,
        'expired': 0,
        'unreachable': 0,
        'parsing_failed': 0,
        'error': 0
    }
    
    for rule in rules:
        site_name = rule.get('site', {}).get('name', 'Unknown')
        print(f"\n--- Site: {site_name} ---")
            
        result = healer.heal_and_retry(rule)
        status = result.get('status')
        results[status] = results.get(status, 0) + 1
        
        # Mapping granular status to health object
        if status in ['ok', 'healed']:
            print(f"  [SUCCESS] {status.upper()}. Bait used: {result.get('bait_used')}")
            rule['health']['status'] = 'green'
        elif status == 'waf':
            print(f"  [WAF] Cloudflare/Shield detected.")
            rule['health']['status'] = 'yellow'
        elif status in ['404', 'expired']:
            print(f"  [OFFLINE] Status: {status.upper()}")
            rule['health']['status'] = 'gray'
        elif status == 'unreachable':
            print(f"  [NETWORK] Timeout or Connection Failure.")
            rule['health']['status'] = 'gray'
        else:
            print(f"  [PARSE_FAIL] Page accessible but no magnets found.")
            rule['health']['status'] = 'yellow'

        rule['health']['status_detail'] = status
        final_rules.append(rule)

    print("\nSaving Healer V2 results...")
    sm.update_sources_json(final_rules)
    
    total = len(rules)
    accessible = results['ok'] + results['healed'] + results['parsing_failed']
    parsing_success = results['ok'] + results['healed']
    
    print("\n=== Healer V2 Intelligent Summary ===")
    print(f"Total Rules: {total}")
    print(f"Successful: {parsing_success} (OK: {results['ok']}, HEALED: {results['healed']})")
    print(f"WAF/Shield: {results['waf']}")
    print(f"Offline (404/Expired): {results['404'] + results['expired']}")
    print(f"Network Blocked: {results['unreachable']}")
    print(f"Parsing Gaps: {results['parsing_failed']}")
    
    if accessible > 0:
        parsing_fail_rate = (results['parsing_failed'] / accessible) * 100
        print(f"\n[KPI] Accessible Page Parsing Failure Rate: {parsing_fail_rate:.1f}%")
        if parsing_fail_rate < 8:
            print("  >>> KPI STATUS: PASSED (< 8%) <<<")
        else:
            print("  >>> KPI STATUS: FAILED (>= 8%) <<<")

if __name__ == "__main__":
    repair_v2_campaign()
