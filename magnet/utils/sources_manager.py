import json
import os
import hashlib
from datetime import datetime
from urllib.parse import urlparse

class SourcesManager:
    def __init__(self):
        self.sources_file = 'sources.json'
        self.schema_version = '0.1'
        self.app_config = {
            'latest_version': '1.0.5',
            'force_update_url': 'https://your-seo-website.com/download'
        }
    
    def generate_rule_id(self, origin):
        """Generate a stable unique ID for a source based on its origin."""
        return hashlib.md5(origin.encode('utf-8')).hexdigest()[:12]

    def generate_sources_json(self, processed_sources):
        """Generate sources.json from processed sources using Project Nebula schema"""
        rules = []
        
        for source in processed_sources:
            origin = source.get('site', {}).get('origin') or source.get('url')
            rule_id = source.get('id') or self.generate_rule_id(origin)
            
            # Map quality and health (with defaults if missing)
            quality = source.get('quality', {
                "score": source.get('weight', source.get('quality_score', 0)),
                "tags": source.get('tags', [])
            })
            
            health = source.get('health', {
                "status": "green" if quality['score'] > 50 else "yellow",
                "last_checked_at": datetime.utcnow().isoformat() + "Z",
                "fail_count_30d": 0
            })

            source_rule = {
                "id": rule_id,
                "site": {
                    "name": source.get('site', {}).get('name') or urlparse(origin).netloc if 'urlparse' in globals() else origin.split('//')[-1].split('/')[0],
                    "origin": origin
                },
                "capabilities": {
                    "supports_search": True,
                    "supports_detail": source.get('supports_detail', False)
                },
                "search": {
                    "request_template": source.get('search', {}).get('request_template') or source.get('search_url_template') or source.get('search_path', ''),
                    "timeout_ms": source.get('timeout_ms', 5000),
                    "retries": source.get('retries', {"max_attempts": 3, "backoff_ms": 1000}),
                    "requires_waf_bypass": source.get('search', {}).get('requires_waf_bypass') or source.get('requires_waf_bypass', False),
                    "parse_metadata": {
                        "selectors": source.get('search', {}).get('parse_metadata', {}).get('selectors') or source.get('selectors', {})
                    }
                },
                "quality": quality,
                "health": health
            }
            rules.append(source_rule)
        
        # Group into a ruleset
        ruleset = {
            "ruleset_id": "base",
            "priority": 1,
            "max_sources_per_search": 10,
            "rules": rules
        }

        # Create the complete Project Nebula structure
        sources_json = {
            "schema_version": self.schema_version,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "rulesets": [ruleset],
            "meta": {
                "app_config": self.app_config,
                "total_rules": len(rules)
            }
        }
        
        return sources_json
    
    def save_sources_json(self, sources_json):
        """Save sources.json and optional mobile-facing magnet_sources.json mirror."""
        try:
            with open(self.sources_file, 'w', encoding='utf-8') as f:
                json.dump(sources_json, f, indent=2, ensure_ascii=False)
            mirror = os.getenv('MAGNET_SOURCES_FILE', 'magnet_sources.json')
            if mirror and mirror != self.sources_file:
                with open(mirror, 'w', encoding='utf-8') as mf:
                    json.dump(sources_json, mf, indent=2, ensure_ascii=False)
                print(f"Also wrote {mirror}")
            
            total_rules = sum(len(rs.get('rules', [])) for rs in sources_json.get('rulesets', []))
            print(f"Successfully saved sources.json with {total_rules} rules")
            return True
        except Exception as e:
            print(f"Error saving sources.json: {e}")
            return False
    
    def load_existing_sources(self):
        """Load existing sources.json if it exists"""
        if os.path.exists(self.sources_file):
            try:
                with open(self.sources_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading existing sources.json: {e}")
        return None
    
    def update_sources_json(self, processed_sources):
        """Update existing sources.json or create new one. Handles migration from legacy format."""
        existing_data = self.load_existing_sources()
        
        # If existing data is legacy format, treat as No Existing Data and overwrite
        is_legacy = existing_data and 'sources' in existing_data and 'rulesets' not in existing_data
        
        if existing_data and not is_legacy:
            # Simple merge: for now, replace rules in 'base' ruleset if origin matches, or add new
            # In a real system, this would be more complex (versioning, etc.)
            
            # Extract existing rules from 'base' ruleset
            base_ruleset = next((rs for rs in existing_data['rulesets'] if rs['ruleset_id'] == 'base'), None)
            if not base_ruleset:
                base_ruleset = {"ruleset_id": "base", "priority": 1, "max_sources_per_search": 10, "rules": []}
                existing_data['rulesets'].append(base_ruleset)
            
            existing_rules_map = {r['site']['origin']: r for r in base_ruleset['rules']}
            
            # New structure build for merging
            new_payload = self.generate_sources_json(processed_sources)
            new_rules = new_payload['rulesets'][0]['rules']
            
            for nr in new_rules:
                existing_rules_map[nr['site']['origin']] = nr
            
            # Combine and sort by score
            updated_rules = list(existing_rules_map.values())
            updated_rules.sort(key=lambda x: x['quality']['score'], reverse=True)
            
            # Limit
            max_sources = int(os.getenv('MAX_SOURCES', 50))
            base_ruleset['rules'] = updated_rules[:max_sources]
            
            existing_data['generated_at'] = datetime.utcnow().isoformat() + "Z"
            existing_data['meta']['total_rules'] = len(base_ruleset['rules'])
            updated_data = existing_data
        else:
            # Create new structure
            updated_data = self.generate_sources_json(processed_sources)
        
        return self.save_sources_json(updated_data)
