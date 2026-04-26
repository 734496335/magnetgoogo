"""Get seedhub download content after h2#download, and 6v520 real movie pages."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from ai_parser.ai_parser import LocalHeuristicParser
from bs4 import BeautifulSoup
import re, requests

parser = LocalHeuristicParser('')

print("=" * 60)
print("seedhub.cc - content AFTER h2#download")
print("=" * 60)

html = parser.get_browser_dom('https://www.seedhub.cc/movies/124272/')
bs = BeautifulSoup(html, 'lxml')

h2 = bs.find(id='download')
if h2:
    sibling = h2.find_next_sibling()
    count = 0
    while sibling and count < 10:
        text = sibling.get_text(separator=' ', strip=True)
        links = [(a['href'][:80], a.get_text(strip=True)[:30]) for a in sibling.find_all('a', href=True)]
        tag = sibling.name
        cls = sibling.get('class', '')
        print(f"\n  <{tag}> class={cls}")
        if text:
            print(f"  Text: {text[:300]}")
        if links:
            for h, t in links:
                print(f"  Link: {h} | {t}")

        for a in sibling.find_all('a', href=True):
            href = a['href']
            if any(kw in href.lower() for kw in ['magnet:', 'ed2k:', '.torrent', 'pan.baidu']):
                print(f"  *** DOWNLOAD LINK: {href[:120]}")

        if any(kw in text.lower() for kw in ['magnet', 'ed2k', 'torrent', 'hash', 'btih']):
            print(f"  *** DOWNLOAD TEXT FOUND")

        sibling = sibling.find_next_sibling()
        count += 1

    print("\n\n  Full HTML after #download:")
    parent = h2.parent
    if parent:
        parent_html = str(parent)
        dl_idx = parent_html.find('id="download"')
        if dl_idx > 0:
            print(parent_html[dl_idx:dl_idx+3000])

print("\n" + "=" * 60)
print("6v520.com - browse actual movie category to find real movie pages")
print("=" * 60)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

resp = requests.get('https://www.6v520.com/s/xijudianying/', timeout=15, headers=HEADERS)
soup = BeautifulSoup(resp.text, 'lxml')

movie_links = []
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if '/dy/' in href and '.html' in href and text and len(text) > 3 and '2026' not in text:
        full = 'https://www.6v520.com' + href if href.startswith('/') else href
        if full not in [m[0] for m in movie_links]:
            movie_links.append((full, text))

movie_links = movie_links[:5]
print(f"Testing {len(movie_links)} movie detail pages...")

for url, text in movie_links:
    print(f"\n  Movie: {text}")
    print(f"  URL: {url}")

    mhtml = parser.get_browser_dom(url)
    if not mhtml:
        print("  FAILED")
        continue
    mbs = BeautifulSoup(mhtml, 'lxml')

    for a in mbs.find_all('a', href=True):
        href = a['href']
        if any(kw in href.lower() for kw in ['ed2k://', 'magnet:', 'thunder://', 'ftp://']):
            print(f"  DOWNLOAD: {href[:120]}")

    full_text = mbs.get_text(separator=' ', strip=True)
    for kw in ['ed2k://', 'magnet:', 'thunder://']:
        idx = full_text.lower().find(kw)
        if idx >= 0:
            print(f"  TEXT-{kw}: {full_text[idx:idx+120]}")

    downtps = mbs.find_all(class_=re.compile(r'down', re.I))
    for d in downtps:
        dtext = d.get_text(separator=' ', strip=True)
        if len(dtext) > 20:
            print(f"  DOWN({d.get('class', '')}): {dtext[:300]}")

    tables = mbs.find_all('table')
    for t in tables:
        ttext = t.get_text(strip=True)
        if len(ttext) > 20 and ('ed2k' in ttext.lower() or 'magnet' in ttext.lower() or 'thunder' in ttext.lower()):
            rows = t.find_all('tr')
            print(f"  TABLE ({len(rows)} rows): {ttext[:300]}")

    time.sleep(1)
