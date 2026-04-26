"""Deep dive into seedhub.cc and 6v520.com detail pages."""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}
hash_re = re.compile(r'[0-9A-Fa-f]{40}')

print("=" * 60)
print("seedhub.cc - extract movie detail links from homepage")
print("=" * 60)
resp = requests.get('https://www.seedhub.cc/', timeout=15, headers=HEADERS)
soup = BeautifulSoup(resp.text, 'lxml')

movie_detail_links = set()
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if '/movies/' in href and text:
        full_url = urljoin('https://www.seedhub.cc', href)
        movie_detail_links.add((full_url, text[:40]))

print(f"Found {len(movie_detail_links)} movie detail links")
for url, text in list(movie_detail_links)[:5]:
    print(f"\n  Detail: {url} | {text}")
    try:
        detail_resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        print(f"  Status: {detail_resp.status_code}  Len: {len(detail_resp.text)}")
        if detail_resp.status_code != 200:
            continue
        dsoup = BeautifulSoup(detail_resp.text, 'lxml')
        magnets = dsoup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hashes = set()
        for a in dsoup.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if m:
                hashes.add(m.group(1))
        print(f"  Magnets: {len(magnets)}  Hashes: {len(hashes)}")
        if magnets:
            for m in magnets[:3]:
                print(f"    {m.get('href', '')[:100]}")
        if hashes:
            for h in list(hashes)[:3]:
                print(f"    hash: {h}")
        title = dsoup.title.string[:50] if dsoup.title and dsoup.title.string else 'N/A'
        print(f"  Title: {title}")
        all_hrefs = [a['href'][:60] for a in dsoup.find_all('a', href=True)][:15]
        print(f"  Links: {all_hrefs}")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("6v520.com - find movie detail pages from homepage")
print("=" * 60)
resp = requests.get('https://www.6v520.com/', timeout=15, headers=HEADERS)
soup = BeautifulSoup(resp.text, 'lxml')

detail_links = set()
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if not text or len(text) < 3 or href.startswith('javascript:'):
        continue
    if any(p in href for p in ['/html/', '/article/', '/vod/', '/movie/', '/film/', '/detail/', '.html']):
        if not any(nav in href for nav in ['/e/', '/search', '/sousuo', 'index']):
            full_url = urljoin('https://www.6v520.com', href)
            detail_links.add((full_url, text[:40]))

print(f"Found {len(detail_links)} potential detail links")
for url, text in list(detail_links)[:5]:
    print(f"\n  Detail: {url} | {text}")
    try:
        detail_resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        print(f"  Status: {detail_resp.status_code}  Len: {len(detail_resp.text)}")
        if detail_resp.status_code != 200:
            continue
        dsoup = BeautifulSoup(detail_resp.text, 'lxml')
        magnets = dsoup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hashes = set()
        for a in dsoup.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if m:
                hashes.add(m.group(1))
        ed2k_links = dsoup.find_all('a', href=lambda h: h and h.startswith('ed2k:'))
        thunder_links = dsoup.find_all('a', href=lambda h: h and h.startswith('thunder:'))
        print(f"  Magnets: {len(magnets)}  Hashes: {len(hashes)}  ed2k: {len(ed2k_links)}  thunder: {len(thunder_links)}")
        if magnets:
            for m in magnets[:2]:
                print(f"    magnet: {m.get('href', '')[:100]}")
        if hashes:
            for h in list(hashes)[:3]:
                print(f"    hash: {h}")
        if ed2k_links:
            for e in ed2k_links[:2]:
                print(f"    ed2k: {e.get('href', '')[:80]}")
        title = dsoup.title.string[:50] if dsoup.title and dsoup.title.string else 'N/A'
        print(f"  Title: {title}")
    except Exception as e:
        print(f"  ERROR: {e}")
