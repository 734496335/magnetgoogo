"""Focus on seedhub #download area and 6v520 real movie pages."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from ai_parser.ai_parser import LocalHeuristicParser
from bs4 import BeautifulSoup
import re

parser = LocalHeuristicParser('')

print("=" * 60)
print("seedhub.cc - analyze download area")
print("=" * 60)

html = parser.get_browser_dom('https://www.seedhub.cc/movies/124272/')
bs = BeautifulSoup(html, 'lxml')

download_section = bs.find(id='download')
if download_section:
    print("Found #download section!")
    print(f"Tag: {download_section.name}")
    print(f"Classes: {download_section.get('class', '')}")
    content = download_section.get_text(separator=' ', strip=True)[:1000]
    print(f"Content:\n{content}")
    print(f"\nLinks in download section:")
    for a in download_section.find_all('a', href=True):
        print(f"  {a['href'][:100]} | {a.get_text(strip=True)[:40]}")
    print(f"\nHTML of download section:")
    print(str(download_section)[:2000])
else:
    print("No #download section found, searching by text...")
    for tag in bs.find_all(['div', 'section', 'table', 'ul', 'ol']):
        text = tag.get_text(strip=True)
        if 'magnet' in text.lower() or 'ed2k' in text.lower() or 'torrent' in text.lower():
            if len(text) < 2000:
                print(f"\n  Found in <{tag.name}> class={tag.get('class', '')} id={tag.get('id', '')}:")
                print(f"  {text[:500]}")

    for a in bs.find_all('a', href=True):
        href = a['href']
        if 'magnet' in href.lower() or 'ed2k' in href.lower() or '.torrent' in href.lower():
            print(f"\n  DIRECT LINK: {href[:100]}")

    input_fields = bs.find_all('input', value=True)
    for inp in input_fields:
        val = inp.get('value', '')
        if 'magnet' in val.lower() or 'ed2k' in val.lower() or len(val) > 30:
            print(f"\n  INPUT: {inp.get('name', '')} = {val[:100]}")

print("\n" + "=" * 60)
print("6v520.com - find a REAL movie detail page")
print("=" * 60)

import requests
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

http_resp = requests.get('https://www.6v520.com/s/gf250/', timeout=15, headers=HEADERS)
soup = BeautifulSoup(http_resp.text, 'lxml')

real_movie_links = []
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if '/dy/' in href and '.html' in href and text and len(text) > 5:
        full = 'https://www.6v520.com' + href if href.startswith('/') else href
        real_movie_links.append((full, text))

real_movie_links = list(dict.fromkeys(real_movie_links))
print(f"Found {len(real_movie_links)} movie links from IMDB250 page")

for url, text in real_movie_links[:3]:
    print(f"\n  Movie: {text}")
    print(f"  URL: {url}")
    mhtml = parser.get_browser_dom(url)
    if not mhtml:
        print("  FAILED")
        continue
    mbs = BeautifulSoup(mhtml, 'lxml')

    for a in mbs.find_all('a', href=True):
        href = a['href']
        if any(kw in href.lower() for kw in ['magnet:', 'ed2k:', 'thunder:', 'ftp://', '.torrent']):
            print(f"  LINK: {href[:120]}")

    downtps = mbs.find_all(class_=re.compile(r'down', re.I))
    for d in downtps:
        dtext = d.get_text(separator='\n', strip=True)
        if len(dtext) > 10 and len(dtext) < 3000:
            print(f"  DOWN-AREA ({d.get('class', '')}): {dtext[:500]}")

    tables = mbs.find_all('table')
    for t in tables:
        ttext = t.get_text(strip=True)
        if any(kw in ttext.lower() for kw in ['ed2k', 'magnet', 'thunder', 'ftp']):
            print(f"  TABLE with download: {ttext[:500]}")

    text_content = mbs.get_text(separator='\n', strip=True)
    for line in text_content.split('\n'):
        if any(kw in line.lower() for kw in ['ed2k://', 'magnet:', 'thunder://', 'ftp://']):
            print(f"  FOUND: {line[:120]}")

    time.sleep(1)
