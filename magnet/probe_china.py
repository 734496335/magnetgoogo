"""Browser test for rarbg/limetorrents + probe Chinese-friendly sites."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_parser.ai_parser import LocalHeuristicParser
from crawler.extractor import MagnetExtractor
from bs4 import BeautifulSoup
import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

CHINA_SITES = [
    ('clmao.cc', 'https://clmao.cc', '/search?q=Ubuntu'),
    ('clmao.xyz', 'https://clmao.xyz', '/search?q=Ubuntu'),
    ('btdig.com', 'https://btdig.com', '/search?q=Ubuntu'),
    ('btdig.org', 'https://btdig.org', '/search?q=Ubuntu'),
    ('moerats.com', 'https://www.moerats.com', '/search?q=magnet'),
    ('cili.one', 'https://cili.one', '/search?q=Ubuntu'),
    ('cili.city', 'https://cili.city', '/search?q=Ubuntu'),
    ('ciliwall.com', 'https://ciliwall.com', '/search?q=Ubuntu'),
    ('btsearch.club', 'https://btsearch.club', '/search?q=Ubuntu'),
    ('mag.net', 'https://mag.net', '/search?q=Ubuntu'),
    ('cilido.gq', 'https://cilido.gq', '/search?q=Ubuntu'),
    ('mag.fun', 'https://mag.fun', '/search?q=Ubuntu'),
    ('fcili.com', 'https://fcili.com', '/search?q=Ubuntu'),
    ('torrent.isFetcher.com', 'https://isFetcher.com', '/search?q=Ubuntu'),
    ('kimcartoon.li', 'https://kimcartoon.li', '/Search/Cartoon?q=One+Piece'),
    ('nyaa.land', 'https://nyaa.land', '/search?q=One+Piece'),
    ('nyaa.iss.one', 'https://nyaa.iss.one', '/?f=0&q=One+Piece'),
    ('www.torrentdownload.info', 'https://www.torrentdownload.info', '/search?q=Ubuntu'),
    ('torrentfunk.com', 'https://torrentfunk.com', '/torrent/Ubuntu.html'),
    ('zooqle.com', 'https://zooqle.com', '/search?q=Ubuntu'),
    ('torrentz2.is', 'https://torrentz2.is', '/search?q=Ubuntu'),
    ('btdb.eu', 'https://btdb.eu', '/search?q=Ubuntu'),
    ('btkitty.pet', 'https://btkitty.pet', '/search?q=Ubuntu'),
    ('easou.com', 'https://www.easou.com', '/search?q=magnet'),
    ('aiyuba.com', 'https://www.aiyuba.com', '/search?q=magnet'),
    ('magazinelib.com', 'https://magazinelib.com', '/?s=magazine'),
]

BROWSER_SITES = [
    ('rarbg.to', 'https://rarbg.to/torrents.php?search=Ubuntu'),
    ('limetorrents.pro', 'https://limetorrents.pro/search/all/Ubuntu/'),
]

SEP = '=' * 50
print("=== Quick HTTP probe for China-friendly sites ===")
for name, origin, path in CHINA_SITES:
    url = origin.rstrip('/') + path
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
        soup = BeautifulSoup(resp.text, 'lxml')
        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        title = soup.title.string[:60] if soup.title else 'N/A'
        status = f"OK({len(magnets)}magnets)" if magnets else f"HTTP{resp.status_code}"
        print(f"  {name:35s} {status:20s} {title}")
        if magnets:
            print(f"    first magnet: {magnets[0].get('href', '')[:60]}")
    except requests.exceptions.Timeout:
        print(f"  {name:35s} TIMEOUT")
    except requests.exceptions.ConnectionError:
        print(f"  {name:35s} DNS FAIL")
    except Exception as e:
        print(f"  {name:35s} ERROR: {str(e)[:40]}")
    time.sleep(0.3)

print()
print("=== Browser test for JS-gate sites ===")
parser = LocalHeuristicParser('')
for name, url in BROWSER_SITES:
    print(f"\n{name}: {url}")
    html = parser.get_browser_dom(url)
    if not html:
        print("  FAILED - no HTML")
        continue
    soup = BeautifulSoup(html, 'lxml')
    title = soup.title.string[:60] if soup.title else 'N/A'
    magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
    text = soup.get_text(strip=True)[:200]
    print(f"  Title: {title}")
    print(f"  Magnets: {len(magnets)}")
    print(f"  Text: {text}")
