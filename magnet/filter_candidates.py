import json
import re

def filter_promising():
    try:
        with open('magnet/all_candidates.json', 'r', encoding='utf-8') as f:
            all_cands = json.load(f)
    except FileNotFoundError:
        with open('all_candidates.json', 'r', encoding='utf-8') as f:
            all_cands = json.load(f)
    
    promising = []
    
    # Negative patterns (exclude gov, edu, big tech hubs, etc.)
    exclude_re = re.compile(
        r'\.(gov|edu|org)\.cn$|'  # Chinese govt/edu
        r'^(beian|news|qq|bilibili|douban|iq|wetv|cctv|docuchina|itingwa|kuwo|taihe|163|cdbao|dengshe|kamigami|subscene|assrt|iiilab|jijidown|bqrdh|motrix|xdown|freedownloadmanager|kinh|imdb|rottentomatoes|mtime|yixi|yiketalks|icourses|xuetangx|nlc|chaoxing|ted|crashcourse|toutiao|huoshanzhibo)\.',
        re.I
    )
    
    # Positive keywords for magnet sites
    positive_keywords = [
        "cili", "bt", "magnet", "torrent", "seed", "digg", "kitty", "dog", "nyaa", 
        "bus", "pirate", "limet", "rarbg", "kickass", "kat", "btt", "clm", "clg"
    ]
    
    for domain, info in all_cands.items():
        url = info.get('url', f'https://{domain}')
        
        # Skip excluded domains
        if exclude_re.search(domain):
            continue
            
        # Check for positive keywords
        lower_domain = domain.lower()
        if any(kw in lower_domain for kw in positive_keywords):
            promising.append(url)
            continue
            
        # Check source tags if any
        sources = info.get('sources', [])
        if any('curated' in str(s).lower() or 'magnet' in str(s).lower() for s in sources):
            promising.append(url)
            
    # Deduplicate and sort
    promising = sorted(list(set(promising)))
    
    print(f"Total candidates: {len(all_cands)}")
    print(f"Promising candidates: {len(promising)}")
    
    # Write as a simple list for the funnel pipeline
    with open('candidates_promising.json', 'w', encoding='utf-8') as f:
        json.dump(promising, f, indent=2)

if __name__ == "__main__":
    filter_promising()
