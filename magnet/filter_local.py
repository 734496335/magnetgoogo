import json
import re

def filter_local_sites():
    with open('magnet/all_candidates.json', 'r', encoding='utf-8') as f:
        all_cands = json.load(f)
    
    local_promising = []
    
    # Focus on common Chinese magnet/movie keywords
    local_keywords = [
        "6v", "dy", "bt", "cili", "clm", "clg", "hao", "nav", "dh", "movie", "film",
        "8k", "4k", "mp4", "pan", "yun", "so", "sou", "search", "magnet"
    ]
    
    # Exclude non-CN international sites that are likely blocked
    blocked_patterns = [
        "thepiratebay", "1337x", "rarbg", "kickass", "kat", "limetorrents", "torrentz", "yts", "eztv", "solidtorrents", "magnetdl"
    ]
    
    for domain, info in all_cands.items():
        url = info.get('url', f'https://{domain}')
        lower_domain = domain.lower()
        
        # Skip if it matches blocked international patterns (these are usually Stage 3 candidates)
        if any(bp in lower_domain for bp in blocked_patterns):
            continue
            
        # Prioritize .com, .net, .cn, .top, .vip, .xyz (common in China)
        if not any(lower_domain.endswith(ext) for ext in [".com", ".net", ".top", ".vip", ".xyz", ".cn", ".cc"]):
            continue
            
        if any(kw in lower_domain for kw in local_keywords):
            local_promising.append(url)
            
    print(f"Total candidates: {len(all_cands)}")
    print(f"Local promising candidates: {len(local_promising)}")
    
    with open('candidates_local.json', 'w', encoding='utf-8') as f:
        json.dump(local_promising, f, indent=2)

if __name__ == "__main__":
    filter_local_sites()
