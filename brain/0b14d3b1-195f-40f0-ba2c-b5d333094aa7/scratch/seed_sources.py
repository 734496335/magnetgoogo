import sys
import os
import json
sys.path.append(os.path.join(os.getcwd(), 'magnet'))

from ai_parser.ai_parser import AIParser
from utils.sources_manager import SourcesManager

def harvest_real_sources():
    print("=== Harvesting Real Sources from Default Rules ===")
    parser = AIParser()
    sm = SourcesManager()
    
    # AIParser.default_rules is what we want
    default_rules = parser.default_rules
    
    processed = []
    for origin, rule in default_rules.items():
        entry = {
            'url': origin,
            'site': {'name': origin.split('//')[-1].split('.')[0], 'origin': origin},
            'search': rule['search'],
            'quality': {'score': 70, 'tags': ['经典老库']},
            'health': {'status': 'green'}
        }
        processed.append(entry)
    
    print(f"Adding {len(processed)} real sources to sources.json")
    sm.update_sources_json(processed)

if __name__ == "__main__":
    harvest_real_sources()
