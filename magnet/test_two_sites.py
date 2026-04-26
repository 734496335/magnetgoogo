"""Test 6v520.com POST search and seedhub.cc movie pages."""
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
print("6v520.com POST search")
print("=" * 60)

search_data = {
    'show': 'title',
    'tempid': '1',
    'tbname': 'article',
    'mid': '1',
    'keyboard': 'Ubuntu',
}
resp = requests.post('https://www.6v520.com/e/search/index.php', data=search_data, timeout=15, headers=HEADERS, allow_redirects=True)
print(f"Status: {resp.status_code}  Final: {resp.url[:60]}  Len: {len(resp.text)}")
soup = BeautifulSoup(resp.text, 'lxml')
title = soup.title.string[:50] if soup.title and soup.title.string else 'N/A'
print(f"Title: {title}")
magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
print(f"Magnets: {len(magnets)}")
links = [(a['href'][:60], a.get_text(strip=True)[:40]) for a in soup.find_all('a', href=True) if a.get_text(strip=True) and not a['href'].startswith('javascript:')][:15]
for h, t in links:
    print(f"  {h:60s} | {t}")

print("\n" + "=" * 60)
print("6v520.com try movie search")
print("=" * 60)
for kw in ['Avatar', 'Interstellar', 'Inception', 'Thor']:
    search_data['keyboard'] = kw
    resp = requests.post('https://www.6v520.com/e/search/index.php', data=search_data, timeout=15, headers=HEADERS, allow_redirects=True)
    soup = BeautifulSoup(resp.text, 'lxml')
    links = [(a['href'][:60], a.get_text(strip=True)[:40]) for a in soup.find_all('a', href=True) if a.get_text(strip=True) and not a['href'].startswith('javascript:')]
    title = soup.title.string[:50] if soup.title and soup.title.string else 'N/A'
    print(f"\n  keyword={kw}: Status={resp.status_code} Len={len(resp.text)} Title={title}")
    print(f"  Links: {len(links)}")
    for h, t in links[:8]:
        print(f"    {h:60s} | {t}")

print("\n" + "=" * 60)
print("seedhub.cc - browse category pages")
print("=" * 60)
for url in [
    'https://www.seedhub.cc/categories/3/types/63/movies/',
    'https://www.seedhub.cc/categories/3/types/66/movies/',
    'https://www.seedhub.cc/',
]:
    print(f"\nURL: {url}")
    resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
    print(f"Status: {resp.status_code}  Len: {len(resp.text)}")
    if resp.status_code != 200:
        continue
    soup = BeautifulSoup(resp.text, 'lxml')
    magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
    hashes = set()
    for a in soup.find_all('a', href=True):
        m = hash_re.search(a['href'])
        if m:
            hashes.add(m.group(1))
    print(f"Magnets: {len(magnets)}  Hashes: {len(hashes)}")
    movie_links = [(a['href'][:60], a.get_text(strip=True)[:40]) for a in soup.find_all('a', href=True) if '/movies/' in a.get('href', '')][:10]
    print(f"Movie links ({len(movie_links)}):")
    for h, t in movie_links:
        print(f"  {h:60s} | {t}")
