"""Deep analyze torrentdownload.info page structure."""
import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

url = 'https://www.torrentdownload.info/search?q=Big+Buck+Bunny'
print(f"Fetching: {url}")
resp = requests.get(url, timeout=20, headers=HEADERS)
print(f"Status: {resp.status_code}  Len: {len(resp.text)}")

soup = BeautifulSoup(resp.text, 'lxml')

print("\n=== All links ===")
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)[:40]
    if href.startswith('http') or href.startswith('/'):
        print(f"  {href[:80]:80s} | {text}")

print("\n=== Tables ===")
for table in soup.find_all('table'):
    rows = table.find_all('tr')
    print(f"  Table with {len(rows)} rows")
    for row in rows[:5]:
        cells = row.find_all(['td', 'th'])
        cell_texts = [c.get_text(strip=True)[:30] for c in cells]
        print(f"    {cell_texts}")

print("\n=== Look for detail/torrent links ===")
for a in soup.find_all('a', href=True):
    href = a['href']
    if any(kw in href for kw in ['/torrent/', '/detail/', '/info/', '/download']):
        text = a.get_text(strip=True)[:60]
        print(f"  {href[:80]} | {text}")
