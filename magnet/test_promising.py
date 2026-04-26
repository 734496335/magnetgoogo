"""Deep test mag.net and torrentdownload.info"""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

SITES = [
    ('mag.net', 'https://mag.net/search?q=Ubuntu'),
    ('mag.net', 'https://mag.net/search?q=Big+Buck+Bunny'),
    ('mag.net', 'https://mag.net/search?q=Interstellar'),
    ('torrentdownload.info', 'https://www.torrentdownload.info/search?q=Ubuntu'),
    ('torrentdownload.info', 'https://www.torrentdownload.info/search?q=Big+Buck+Bunny'),
    ('torrentdownload.info', 'https://www.torrentdownload.info/search?q=Interstellar'),
    ('torrentdownload.info', 'https://www.torrentdownload.info/search?q=One+Piece'),
]

for name, url in SITES:
    print(f"\n{'='*50}")
    print(f"{name}: {url}")
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        print(f"Status: {resp.status_code}  Final: {resp.url[:80]}  Len: {len(resp.text)}")
        soup = BeautifulSoup(resp.text, 'lxml')
        title = soup.title.string if soup.title else 'N/A'
        print(f"Title: {title[:80]}")
        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        print(f"Magnet links: {len(magnets)}")
        for m in magnets[:3]:
            href = m.get('href', '')
            print(f"  magnet: {href[:80]}...")

        text = soup.get_text(separator=' ', strip=True)
        print(f"Text preview: {text[:300]}")

        if resp.status_code == 200 and len(resp.text) > 500:
            print(f"\nHTML sample: {resp.text[:500]}")
    except Exception as e:
        print(f"ERROR: {e}")
