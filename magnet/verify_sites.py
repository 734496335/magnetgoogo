"""Follow seedhub link_start redirects to get actual magnet links."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from ai_parser.ai_parser import LocalHeuristicParser
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re, requests

parser = LocalHeuristicParser('')

print("=" * 60)
print("seedhub.cc - follow link_start redirects")
print("=" * 60)

html = parser.get_browser_dom('https://www.seedhub.cc/movies/124272/')
bs = BeautifulSoup(html, 'lxml')

seed_links = []
for a in bs.find_all('a', href=True):
    href = a['href']
    if '/link_start/' in href and 'seed_id' in href:
        full = urljoin('https://www.seedhub.cc', href)
        title = a.get('title', a.get_text(strip=True))[:60]
        seed_links.append((full, title))

print(f"Found {len(seed_links)} seed links")
print("Following first 3 to get actual magnet URLs...\n")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

for url, title in seed_links[:3]:
    print(f"  Link: {title}")
    print(f"  URL: {url}")
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=False)
        print(f"  Status: {resp.status_code}")
        if resp.status_code in (301, 302, 303, 307):
            location = resp.headers.get('Location', '')
            print(f"  Redirect -> {location[:120]}")
        elif resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'lxml')
            magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
            text = soup.get_text(strip=True)[:200]
            print(f"  Body len: {len(resp.text)}  Magnets: {len(magnets)}")
            if magnets:
                for m in magnets[:1]:
                    print(f"  Magnet: {m.get('href', '')[:120]}")
            print(f"  Text: {text}")
        else:
            print(f"  Headers: {dict(resp.headers)}")
            print(f"  Body: {resp.text[:200]}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()
    time.sleep(1)

print("\n" + "=" * 60)
print("6v520.com - verify more movie pages have magnets")
print("=" * 60)

resp = requests.get('https://www.6v520.com/', timeout=15, headers=HEADERS)
soup = BeautifulSoup(resp.text, 'lxml')

movie_links = []
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if '/dy/' in href and '.html' in href and text and len(text) > 5:
        if any(yr in text for yr in ['2026', '2025', '2024']):
            full = urljoin('https://www.6v520.com', href)
            movie_links.append((full, text[:40]))

movie_links = list(dict.fromkeys(movie_links))
print(f"Found {len(movie_links)} recent movie links, testing 5...")

for url, text in movie_links[:5]:
    mhtml = parser.get_browser_dom(url)
    if not mhtml:
        continue
    mbs = BeautifulSoup(mhtml, 'lxml')
    magnets = mbs.find_all('a', href=lambda h: h and h.startswith('magnet:'))
    ed2k = [a for a in mbs.find_all('a', href=True) if a['href'].startswith('ed2k://')]
    thunder = [a for a in mbs.find_all('a', href=True) if a['href'].startswith('thunder://')]
    total = len(magnets) + len(ed2k) + len(thunder)
    if total > 0:
        print(f"  {text}: magnet={len(magnets)} ed2k={len(ed2k)} thunder={len(thunder)}")
        for m in magnets[:1]:
            print(f"    magnet: {m.get('href', '')[:80]}")
    else:
        print(f"  {text}: no download links")
    time.sleep(0.5)
