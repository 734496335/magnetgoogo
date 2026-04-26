"""Analyze animetosho.org and torrentdownload.info actual HTML."""
import requests
from bs4 import BeautifulSoup
import re

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

for name, url in [
    ('animetosho', 'https://animetosho.org/search?q=Inception'),
    ('torrentdownload', 'https://www.torrentdownload.info/search?q=Inception'),
]:
    print(f"\n{'='*50}")
    print(f"{name}: {url}")
    resp = requests.get(url, timeout=15, headers=HEADERS)
    print(f"Status: {resp.status_code}  Len: {len(resp.text)}")

    soup = BeautifulSoup(resp.text, 'lxml')

    magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
    print(f"Direct magnets: {len(magnets)}")
    for m in magnets[:3]:
        print(f"  {m.get('href', '')[:80]}")

    torrent_links = [a for a in soup.find_all('a', href=True) if '/torrent/' in a['href'] or '.torrent' in a['href']]
    print(f"Torrent links: {len(torrent_links)}")
    for a in torrent_links[:3]:
        print(f"  {a['href'][:60]} | {a.get_text(strip=True)[:40]}")

    print(f"\nAll links with significant href:")
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)[:30]
        if len(href) > 10 and text:
            print(f"  {href[:60]:60s} | {text}")

    print(f"\nHTML sample: {resp.text[:600]}")
