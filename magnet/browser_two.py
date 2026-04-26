"""Browser test 6v520 and seedhub detail pages."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from ai_parser.ai_parser import LocalHeuristicParser
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

hash_re = re.compile(r'[0-9A-Fa-f]{40}')
parser = LocalHeuristicParser('')

print("=" * 60)
print("6v520.com - browser test")
print("=" * 60)

resp = parser.session if hasattr(parser, 'session') else None
import requests
http_resp = requests.get('https://www.6v520.com/', timeout=15, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})
soup = BeautifulSoup(http_resp.text, 'lxml')

detail_links = []
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if text and len(text) > 5 and '.html' in href and '/e/' not in href:
        full = urljoin('https://www.6v520.com', href)
        if full not in [d[0] for d in detail_links]:
            detail_links.append((full, text[:40]))

print(f"Found {len(detail_links)} detail links, testing first 3 with browser...")

for url, text in detail_links[:3]:
    print(f"\n  Browser: {text}")
    print(f"  URL: {url}")
    html = parser.get_browser_dom(url)
    if not html:
        print("  FAILED")
        continue
    bs = BeautifulSoup(html, 'lxml')
    magnets = bs.find_all('a', href=lambda h: h and h.startswith('magnet:'))
    hashes = set()
    for a in bs.find_all('a', href=True):
        m = hash_re.search(a['href'])
        if m:
            hashes.add(m.group(1))
    ed2k = [a for a in bs.find_all('a', href=True) if a['href'].startswith('ed2k://')]
    thunder = [a for a in bs.find_all('a', href=True) if a['href'].startswith('thunder://')]
    print(f"  HTML: {len(html)}  Magnets: {len(magnets)}  Hashes: {len(hashes)}  ed2k: {len(ed2k)}  thunder: {len(thunder)}")
    if magnets:
        for m in magnets[:2]:
            print(f"    magnet: {m.get('href', '')[:100]}")
    if hashes:
        for h in list(hashes)[:2]:
            print(f"    hash: {h}")
    if ed2k:
        for e in ed2k[:1]:
            print(f"    ed2k: {e.get('href', '')[:80]}")
    if thunder:
        for t in thunder[:1]:
            print(f"    thunder: {t.get('href', '')[:80]}")

    download_area = bs.find_all(['div', 'table'], class_=re.compile(r'download|down|torrent|magnet|ed2k|resource', re.I))
    if download_area:
        for d in download_area[:2]:
            print(f"    download area: {d.get('class', '')} -> {d.get_text(strip=True)[:100]}")

    all_links = [(a['href'][:50], a.get_text(strip=True)[:30]) for a in bs.find_all('a', href=True) if a.get_text(strip=True) and not a['href'].startswith('#')][:10]
    print(f"    top links: {all_links}")
    time.sleep(1)

print("\n" + "=" * 60)
print("seedhub.cc - browser test")
print("=" * 60)

html = parser.get_browser_dom('https://www.seedhub.cc/')
if html:
    bs = BeautifulSoup(html, 'lxml')
    movie_links = []
    for a in bs.find_all('a', href=True):
        href = a['href']
        if '/movies/' in href:
            mid = href.rstrip('/').split('/')[-1]
            if mid.isdigit():
                full = urljoin('https://www.seedhub.cc', href)
                movie_links.append(full)
    movie_links = list(dict.fromkeys(movie_links))[:3]
    print(f"Found {len(movie_links)} movie links, testing first 3...")

    for url in movie_links:
        print(f"\n  Browser: {url}")
        mhtml = parser.get_browser_dom(url)
        if not mhtml:
            print("    FAILED")
            continue
        mbs = BeautifulSoup(mhtml, 'lxml')
        magnets = mbs.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hashes = set()
        for a in mbs.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if m:
                hashes.add(m.group(1))
        title = mbs.title.string[:40] if mbs.title and mbs.title.string else ''
        print(f"    Title: {title}  HTML: {len(mhtml)}  Magnets: {len(magnets)}  Hashes: {len(hashes)}")
        if magnets:
            for m in magnets[:2]:
                print(f"    magnet: {m.get('href', '')[:100]}")
        if hashes:
            for h in list(hashes)[:2]:
                print(f"    hash: {h}")
        time.sleep(1)
else:
    print("  FAILED to render seedhub.cc homepage")
