"""Check what 6v520 search results page actually contains."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

search_body = {
    'show': 'title',
    'tempid': '1',
    'tbname': 'article',
    'mid': '1',
    'keyboard': 'Avatar',
}

resp = requests.post('https://www.6v520.com/e/search/index.php', data=search_body, timeout=15, headers=HEADERS, allow_redirects=True)
print(f"Status: {resp.status_code}  Final: {resp.url}  Len: {len(resp.text)}")

soup = BeautifulSoup(resp.text, 'lxml')
title = soup.title.string[:50] if soup.title and soup.title.string else 'N/A'
print(f"Title: {title}")

links = [(a['href'][:60], a.get_text(strip=True)[:40]) for a in soup.find_all('a', href=True) if a.get_text(strip=True)]
print(f"Links ({len(links)}):")
for h, t in links[:15]:
    print(f"  {h:60s} | {t}")

magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
print(f"\nMagnets: {len(magnets)}")

text = soup.get_text(strip=True)[:300]
print(f"\nText: {text}")
