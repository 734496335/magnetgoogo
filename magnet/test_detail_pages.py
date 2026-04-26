"""Test 6v520 detail pages and seedhub with referer."""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}
hash_re = re.compile(r'[0-9A-Fa-f]{40}')

print("=" * 60)
print("6v520.com - test detail pages")
print("=" * 60)

resp = requests.get('https://www.6v520.com/', timeout=15, headers=HEADERS)
soup = BeautifulSoup(resp.text, 'lxml')

detail_links = []
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if not text or len(text) < 3 or href.startswith('javascript:'):
        continue
    if any(p in href for p in ['/html/', '.html']):
        if not any(nav in href for nav in ['/e/', '/search', '/sousuo', '/search/', 'index.html']):
            full_url = urljoin('https://www.6v520.com', href)
            if full_url not in [d[0] for d in detail_links]:
                detail_links.append((full_url, text[:40]))

print(f"Found {len(detail_links)} detail links")

tested = 0
found = 0
for url, text in detail_links:
    if tested >= 8:
        break
    tested += 1
    try:
        detail_resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        if detail_resp.status_code != 200:
            print(f"  [{tested}] {text}: HTTP {detail_resp.status_code}")
            continue
        dsoup = BeautifulSoup(detail_resp.text, 'lxml')
        magnets = dsoup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hashes = set()
        for a in dsoup.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if m:
                hashes.add(m.group(1))
        ed2k = [a for a in dsoup.find_all('a', href=True) if a['href'].startswith('ed2k://')]
        thunder = [a for a in dsoup.find_all('a', href=True) if a['href'].startswith('thunder://')]

        has_download = len(magnets) > 0 or len(hashes) > 0 or len(ed2k) > 0 or len(thunder) > 0
        if has_download:
            found += 1
            print(f"  [{tested}] {text}: magnet={len(magnets)} hash={len(hashes)} ed2k={len(ed2k)} thunder={len(thunder)}")
            for m in magnets[:1]:
                print(f"       magnet: {m.get('href', '')[:100]}")
            for h in list(hashes)[:1]:
                print(f"       hash: {h}")
            for e in ed2k[:1]:
                print(f"       ed2k: {e.get('href', '')[:80]}")
            for t in thunder[:1]:
                print(f"       thunder: {t.get('href', '')[:80]}")
        else:
            print(f"  [{tested}] {text}: no download links found")
    except Exception as e:
        print(f"  [{tested}] {text}: ERROR {str(e)[:40]}")

print(f"\n6v520: tested={tested} found_download_links={found}")

print("\n" + "=" * 60)
print("seedhub.cc - test with Referer header")
print("=" * 60)

seedhub_headers = dict(HEADERS)
seedhub_headers['Referer'] = 'https://www.seedhub.cc/'
seedhub_headers['Origin'] = 'https://www.seedhub.cc'

resp = requests.get('https://www.seedhub.cc/', timeout=15, headers=HEADERS)
soup = BeautifulSoup(resp.text, 'lxml')

movie_links = []
for a in soup.find_all('a', href=True):
    href = a['href']
    if '/movies/' in href and href.count('/') >= 3:
        mid = href.rstrip('/').split('/')[-1]
        if mid.isdigit():
            full_url = urljoin('https://www.seedhub.cc', href)
            movie_links.append(full_url)

movie_links = list(dict.fromkeys(movie_links))[:5]
print(f"Testing {len(movie_links)} movie detail pages with Referer...")

for url in movie_links:
    try:
        r = requests.get(url, timeout=15, headers=seedhub_headers, allow_redirects=True)
        print(f"  {url}: HTTP {r.status_code}  Len: {len(r.text)}")
        if r.status_code == 200:
            dsoup = BeautifulSoup(r.text, 'lxml')
            magnets = dsoup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
            hashes = set()
            for a in dsoup.find_all('a', href=True):
                m = hash_re.search(a['href'])
                if m:
                    hashes.add(m.group(1))
            title = dsoup.title.string[:40] if dsoup.title and dsoup.title.string else ''
            print(f"    Title: {title}  Magnets: {len(magnets)}  Hashes: {len(hashes)}")
            if magnets:
                for m in magnets[:2]:
                    print(f"    magnet: {m.get('href', '')[:100]}")
            if hashes:
                for h in list(hashes)[:2]:
                    print(f"    hash: {h}")
    except Exception as e:
        print(f"  {url}: ERROR {str(e)[:40]}")
