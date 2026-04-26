"""Deep analyze seedhub.cc and 6v520.com detail page download areas."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from ai_parser.ai_parser import LocalHeuristicParser
from bs4 import BeautifulSoup
import re

parser = LocalHeuristicParser('')

print("=" * 60)
print("seedhub.cc - deep analyze detail page")
print("=" * 60)

for url in ['https://www.seedhub.cc/movies/124272/']:
    print(f"\nURL: {url}")
    html = parser.get_browser_dom(url)
    if not html:
        print("FAILED")
        continue
    bs = BeautifulSoup(html, 'lxml')

    all_links = []
    for a in bs.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        all_links.append((href, text))

    download_related = []
    for href, text in all_links:
        if any(kw in href.lower() for kw in ['magnet:', 'ed2k:', 'thunder:', 'ftp:', '.torrent', 'download', 'pan.baidu']):
            download_related.append((href[:80], text[:30]))
        elif any(kw in text.lower() for kw in ['magnet', 'ed2k', 'thunder', 'torrent', 'download', 'pan.baidu', 'magnet:?xt', 'hash']):
            download_related.append((href[:80], text[:30]))

    print(f"All links: {len(all_links)}  Download-related: {len(download_related)}")
    for h, t in download_related:
        print(f"  DOWNLOAD: {h} | {t}")

    buttons = bs.find_all('button')
    print(f"\nButtons: {len(buttons)}")
    for b in buttons:
        print(f"  {b.get_text(strip=True)[:30]} | onclick={b.get('onclick', '')[:50]}")

    inputs = bs.find_all(['input', 'textarea'])
    print(f"\nInputs: {len(inputs)}")
    for i in inputs:
        if i.get('value') and len(i.get('value', '')) > 10:
            print(f"  {i.get('name', '')} = {i.get('value', '')[:80]}")

    divs_with_id = bs.find_all(['div', 'section', 'span'], id=True)
    for d in divs_with_id:
        text = d.get_text(strip=True)
        if any(kw in text.lower() for kw in ['magnet', 'ed2k', 'hash', 'btih']):
            print(f"\n  DIV id={d.get('id')}: {text[:200]}")

    text_content = bs.get_text(separator='\n', strip=True)
    for line in text_content.split('\n'):
        line_stripped = line.strip()
        if any(kw in line_stripped.lower() for kw in ['magnet:', 'ed2k:', 'thunder:', 'hash:', 'btih']):
            print(f"  FOUND IN TEXT: {line_stripped[:100]}")

    print(f"\n  Sample text (first 500 chars):")
    print(f"  {text_content[:500]}")

print("\n" + "=" * 60)
print("6v520.com - deep analyze real movie page")
print("=" * 60)

import requests
http_resp = requests.get('https://www.6v520.com/', timeout=15, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})
soup = BeautifulSoup(http_resp.text, 'lxml')

movie_links = []
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if text and '/dy/' in href and '.html' in href:
        full = 'https://www.6v520.com' + href if href.startswith('/') else href
        movie_links.append((full, text[:40]))

movie_links = list(dict.fromkeys(movie_links))
print(f"Found {len(movie_links)} movie links")

for url, text in movie_links[:3]:
    print(f"\n  Movie: {text}")
    print(f"  URL: {url}")
    html = parser.get_browser_dom(url)
    if not html:
        print("  FAILED")
        continue
    bs = BeautifulSoup(html, 'lxml')
    text_content = bs.get_text(separator='\n', strip=True)
    for line in text_content.split('\n'):
        line_stripped = line.strip()
        if any(kw in line_stripped.lower() for kw in ['magnet:', 'ed2k:', 'thunder:', 'ftp://']):
            print(f"  FOUND IN TEXT: {line_stripped[:120]}")

    for a in bs.find_all('a', href=True):
        href = a['href']
        if any(kw in href.lower() for kw in ['magnet:', 'ed2k:', 'thunder:', 'ftp://', '.torrent']):
            print(f"  LINK: {href[:100]} | {a.get_text(strip=True)[:30]}")

    downtps = bs.find_all(class_=re.compile(r'down', re.I))
    for d in downtps:
        dtext = d.get_text(strip=True)
        if len(dtext) > 5:
            print(f"  DOWN-AREA: {dtext[:200]}")
    time.sleep(1)
