"""Browser test China sites with JS rendering."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_parser.ai_parser import LocalHeuristicParser
from bs4 import BeautifulSoup
import re

SITES = [
    ('cilihezi.com', 'https://cilihezi.com/search.php?keywords=Ubuntu'),
    ('btfox', 'https://btfox12.top/?wd=Ubuntu'),
    ('cilihezi.top', 'https://www.cilihezi.top/?s=Ubuntu'),
    ('cilijun.com', 'https://cilijun.com/search/Ubuntu/1/0/0.html'),
    ('cilitiantang.vip', 'https://www.cilitiantang.vip'),
    ('cilimao.biz', 'https://cilimao.biz/search?q=Ubuntu'),
]

parser = LocalHeuristicParser('')
hash_re = re.compile(r'[0-9A-Fa-f]{40}')

for name, url in SITES:
    print(f"\n{'='*50}")
    print(f"{name}: {url}")
    html = parser.get_browser_dom(url)
    if not html:
        print("  FAILED - no HTML")
        continue
    soup = BeautifulSoup(html, 'lxml')
    title = soup.title.string[:60] if soup.title else 'N/A'
    magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
    hash_urls = [a for a in soup.find_all('a', href=True) if hash_re.search(a['href'])]
    text = soup.get_text(strip=True)[:150].encode('ascii', 'replace').decode('ascii')
    print(f"  Title: {title}")
    print(f"  HTML: {len(html)}  Magnets: {len(magnets)}  HashURLs: {len(hash_urls)}")
    print(f"  Text: {text}")
    if magnets:
        for m in magnets[:3]:
            print(f"    magnet: {m.get('href', '')[:80]}")
    if hash_urls:
        for a in hash_urls[:3]:
            print(f"    hash: {a['href'][:60]} | {a.get_text(strip=True)[:40]}")
    time.sleep(1)
