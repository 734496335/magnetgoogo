"""Try API endpoints for China magnet sites."""
import requests
from bs4 import BeautifulSoup
import json, re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

SITES = [
    ('cilihezi.com/api', 'https://cilihezi.com/api/search?q=Ubuntu'),
    ('cilihezi.com/ajax', 'https://cilihezi.com/search.php?keywords=Ubuntu&ajax=1'),
    ('btfox/api', 'https://btfox12.top/api?wd=Ubuntu'),
    ('btfox/search', 'https://btfox.xyz/search?wd=Ubuntu'),
    ('cilibra', 'https://www.cilibra.com/search?q=Ubuntu'),
    ('cilibra/api', 'https://www.cilibra.com/api/search?q=Ubuntu'),
    ('cilitiantang/api', 'https://www.cilitiantang.vip/api/search?q=Ubuntu'),
    ('btdigg', 'http://btdigg.org/search?q=Ubuntu'),
    ('btdigg', 'https://btdigg.org/search?q=Ubuntu'),
    ('megnet', 'https://megnet.net/search?q=Ubuntu'),
    ('cili123', 'https://www.cili123.com/search?q=Ubuntu'),
    ('ciliword', 'https://ciliword.com/search?q=Ubuntu'),
    ('btav', 'https://btav.xyz/search?q=Ubuntu'),
]

for name, url in SITES:
    print(f"\n{name}: {url}")
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
        ct = resp.headers.get('content-type', '')[:40]
        print(f"  Status: {resp.status_code}  Len: {len(resp.text)}  CT: {ct}  Final: {resp.url[:50]}")
        if resp.status_code == 200 and len(resp.text) > 100:
            if 'json' in ct:
                print(f"  JSON: {resp.text[:200]}")
            else:
                soup = BeautifulSoup(resp.text, 'lxml')
                magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
                hash_re = re.compile(r'[0-9A-Fa-f]{40}')
                hashes = set()
                for a in soup.find_all('a', href=True):
                    m = hash_re.search(a['href'])
                    if m:
                        hashes.add(m.group(1))
                print(f"  Magnets: {len(magnets)}  Hashes: {len(hashes)}")
                if magnets:
                    for m in magnets[:2]:
                        print(f"    {m.get('href', '')[:80]}")
                text = soup.get_text(strip=True)[:100].encode('ascii', 'replace').decode('ascii')
                print(f"  Text: {text}")
    except Exception as e:
        print(f"  ERROR: {str(e)[:60]}")
