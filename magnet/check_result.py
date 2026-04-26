"""Check what 6v520 search result page looks like with correct params."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://www.6v520.com/',
}

body = {
    'show': 'title,smalltext',
    'tempid': '1',
    'tbname': 'article',
    'mid': '1',
    'classid': '0',
    'keyboard': 'Avatar',
}

resp = requests.post('https://www.6v520.com/e/search/index.php', data=body, timeout=15, headers=HEADERS, allow_redirects=True)
print(f"Status: {resp.status_code}  Final: {resp.url}  Len: {len(resp.text)}")

soup = BeautifulSoup(resp.text, 'lxml')

movie_links = []
for a in soup.find_all('a', href=True):
    href = a['href']
    text = a.get_text(strip=True)
    if text and len(text) > 3 and '/dy/' in href and '.html' in href:
        from urllib.parse import urljoin
        full = urljoin(resp.url, href)
        movie_links.append((full, text))

print(f"\nMovie detail links: {len(movie_links)}")
for url, text in movie_links[:10]:
    print(f"  {url}")
    print(f"  {text}")

if movie_links:
    print(f"\nFetching first detail page: {movie_links[0][0]}")
    detail_resp = requests.get(movie_links[0][0], timeout=15, headers=HEADERS)
    dsoup = BeautifulSoup(detail_resp.text, 'lxml')
    magnets = dsoup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
    print(f"  Magnets: {len(magnets)}")
    for m in magnets[:2]:
        print(f"    {m.get('href', '')[:100]}")
