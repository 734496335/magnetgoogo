import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'magnet'))

from utils.sources_manager import SourcesManager
import json

def test_restructuring():
    sm = SourcesManager()
    
    # Mock processed_sources with new fields from validation and ai_parser
    dummy_processed = [
        {
            'url': 'https://dummy-site.com',
            'site': {'name': 'Dummy Site', 'origin': 'https://dummy-site.com'},
            'quality': {
                'score': 85,
                'tags': ['追新极客', '垂直专精']
            },
            'health': {
                'status': 'green',
                'last_checked_at': '2026-04-16T20:50:00Z',
                'fail_count_30d': 0
            },
            'search': {
                'request_template': '/search?q={query}',
                'timeout_ms': 5000,
                'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                'requires_waf_bypass': True,
                'parse_metadata': {
                    'selectors': {
                        'list_item': 'div.item',
                        'title': 'a.title'
                    }
                }
            }
        }
    ]
    
    # Also test legacy structure (backward compatibility support)
    dummy_legacy = [
        {
            'url': 'https://legacy-site.pw',
            'search_path': '/s/{query}',
            'selectors': {'list_item': 'tr'},
            'weight': 40,
            'tags': ['经典老库']
        }
    ]
    
    print("Testing generate_sources_json with mixed data...")
    payload = sm.generate_sources_json(dummy_processed + dummy_legacy)
    
    print("\nResulting Structure:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    
    # Save it
    print("\nSaving to sources.json...")
    sm.save_sources_json(payload)
    
    # Verify file
    with open('sources.json', 'r', encoding='utf-8') as f:
        saved = json.load(f)
        if 'rulesets' in saved and 'schema_version' in saved:
            print("\nSUCCESS: sources.json follows Project Nebula architecture!")
        else:
            print("\nFAILURE: sources.json structure is incorrect.")

if __name__ == "__main__":
    test_restructuring()
