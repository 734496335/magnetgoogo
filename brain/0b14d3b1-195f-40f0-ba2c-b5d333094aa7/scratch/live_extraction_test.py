import sys
import os
import json
sys.path.append(os.path.join(os.getcwd(), 'magnet'))

from crawler.extractor import MagnetExtractor

def live_test(query="Ubuntu"):
    print(f"=== Project Nebula Live Search Test (Query: {query}) ===")
    
    # Load the latest sources.json
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
        print("No rules found in sources.json.")
        return

    print(f"Found {len(rules)} rules to test.")
    
    # Limit test to top 10 rules for speed
    test_rules = rules[:10]
    
    results = []
    
    for rule in test_rules:
        site_name = rule.get('site', {}).get('name', 'Unknown')
        origin = rule.get('site', {}).get('origin', 'Unknown')
        print(f"\n--- Testing Site: {site_name} ({origin}) ---")
        
        extractor = MagnetExtractor(rule)
        
        # Check if WAF bypass is needed
        if extractor.requires_waf_bypass:
            print("  [WAF] Site requires WAF bypass. Skipping live request in headless test mode.")
            results.append({'site': site_name, 'status': 'skipped', 'reason': 'WAF required'})
            continue
            
        try:
            magnets = extractor.search(query, limit=5)
            if magnets:
                print(f"  [SUCCESS] Found {len(magnets)} magnets:")
                for m in magnets[:2]:
                    print(f"    - Title: {m.get('title')[:50]}...")
                    print(f"      Magnet: {m.get('magnet')[:40]}...")
                    print(f"      Size: {m.get('size')} | Date: {m.get('date')}")
                results.append({'site': site_name, 'status': 'ok', 'count': len(magnets)})
            else:
                print("  [FAILED] No magnets found.")
                results.append({'site': site_name, 'status': 'failed', 'reason': 'No results'})
        except Exception as e:
            print(f"  [ERROR] Search failed: {e}")
            results.append({'site': site_name, 'status': 'error', 'reason': str(e)})

    print("\n=== Test Summary ===")
    for res in results:
        status = res['status'].upper()
        site = res['site']
        info = f"({res.get('count', 0)} found)" if 'count' in res else f"({res.get('reason')})"
        print(f"[{status}] {site} {info}")

if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "One Piece"
    live_test(query)
