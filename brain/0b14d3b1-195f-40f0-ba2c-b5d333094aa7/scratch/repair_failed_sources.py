import sys
import os
import json
sys.path.append(os.path.join(os.getcwd(), 'magnet'))

from crawler.healer import Healer
from utils.sources_manager import SourcesManager

def repair_campaign():
    print("=== Project Nebula - Source Repair Campaign ===")
    
    sources_path = 'sources.json'
    if not os.path.exists(sources_path):
        print(f"Error: {sources_path} not found.")
        return
    
    with open(sources_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    rules = []
    # Collect all rules from all rulesets
    for rs in data.get('rulesets', []):
        rules.extend(rs.get('rules', []))
    
    if not rules:
        print("No rules to repair.")
        return

    healer = Healer()
    sm = SourcesManager()
    
    final_rules = []
    healed_count = 0
    ok_count = 0
    failed_count = 0
    
    for rule in rules:
        site_name = rule.get('site', {}).get('name', 'Unknown')
        print(f"\n--- Healing Site: {site_name} ---")
        
        # Check for WAF - healer currently uses requests, so WAF sites will fail fetch
        if rule.get('search', {}).get('requires_waf_bypass'):
            print("  [SKIP] Site requires WAF bypass.")
            final_rules.append(rule)
            continue
            
        result = healer.heal_and_retry(rule)
        status = result.get('status')
        
        if status == 'ok':
            print(f"  [OK] Site is working fine.")
            ok_count += 1
            final_rules.append(rule)
        elif status == 'healed':
            print(f"  [HEALED] Found new selectors! Magnets found: {result.get('magnets_found')}")
            healed_count += 1
            # Update the rule with healed selectors
            new_selectors = result.get('healed_selectors')
            if 'search' not in rule:
                rule['search'] = {'parse_metadata': {'selectors': {}}}
            rule['search']['parse_metadata']['selectors'] = new_selectors
            rule['health']['status'] = 'green'
            final_rules.append(rule)
        else:
            print(f"  [FAILED] Could not heal: {result.get('error') or 'no results'}")
            failed_count += 1
            rule['health']['status'] = 'gray'
            final_rules.append(rule)

    # Save results back to sources.json using SourcesManager
    # sources_manager expects a flat list of 'processed_sources' and handles the ruleset grouping
    # But since we already have the full structure, we'll just save it directly or use update_sources_json with the list
    
    print("\nSaving campaign results...")
    sm.update_sources_json(final_rules)
    
    print("\n=== Campaign Summary ===")
    print(f"Total Rules processed: {len(rules)}")
    print(f"Working (OK): {ok_count}")
    print(f"Healed (Fixed): {healed_count}")
    print(f"Failed (Dead/Unsupported): {failed_count}")

if __name__ == "__main__":
    repair_campaign()
