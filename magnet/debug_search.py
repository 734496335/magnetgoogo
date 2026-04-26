"""Test 6v520.com search with full form params + browser."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://www.6v520.com/',
}

# Try different search configs
search_configs = [
    {'show': 'title', 'tempid': '1', 'tbname': 'article', 'mid': '1', 'keyboard': 'Avatar'},
    {'show': 'title,smalltext', 'tempid': '1', 'tbname': 'article', 'mid': '1', 'keyboard': 'Avatar', 'classid': '0'},
    {'keyboard': 'Avatar', 'show': 'title', 'tbname': 'article', 'tempid': '1', 'mid': '1', 'classid': '3'},
    {'keyboard': 'Avatar', 'show': 'title,newstext', 'tbname': 'article', 'tempid': '1', 'mid': '1'},
]

for i, body in enumerate(search_configs):
    print(f"\nConfig {i+1}: {body}")
    resp = requests.post('https://www.6v520.com/e/search/index.php', data=body, timeout=15, headers=HEADERS, allow_redirects=True)
    print(f"  Status: {resp.status_code}  Len: {len(resp.text)}  Final: {resp.url[:50]}")
    soup = BeautifulSoup(resp.text, 'lxml')
    title = soup.title.string[:30] if soup.title and soup.title.string else 'N/A'
    text = soup.get_text(strip=True)[:100]
    print(f"  Title: {title}")
    print(f"  Text: {text}")
    links = [(a['href'][:50], a.get_text(strip=True)[:30]) for a in soup.find_all('a', href=True) if a.get_text(strip=True)]
    if links:
        for h, t in links[:5]:
            print(f"  Link: {h} | {t}")

# Also try the sousuo.html page
print("\n\nSousuo page:")
resp = requests.get('https://www.6v520.com/sousuo.html', timeout=15, headers=HEADERS)
print(f"  Status: {resp.status_code}  Len: {len(resp.text)}")
soup = BeautifulSoup(resp.text, 'lxml')
forms = soup.find_all('form')
for f in forms[:3]:
    action = f.get('action', '')
    method = f.get('method', 'GET')
    inputs = [(i.get('name', ''), i.get('type', ''), i.get('value', '')[:20]) for i in f.find_all('input')]
    print(f"  Form: action={action} method={method} inputs={inputs}")

# Try using browser for the search
print("\n\nBrowser search:")
from ai_parser.ai_parser import LocalHeuristicParser
parser = LocalHeuristicParser('')
html = parser.get_browser_dom('https://www.6v520.com/e/search/index.php')
if html and len(html) > 1000:
    print(f"  Browser HTML: {len(html)}")
    soup = BeautifulSoup(html, 'lxml')
    links = [(a['href'][:50], a.get_text(strip=True)[:30]) for a in soup.find_all('a', href=True) if a.get_text(strip=True)]
    print(f"  Links: {len(links)}")
    for h, t in links[:5]:
        print(f"    {h} | {t}")
else:
    print(f"  Browser returned small HTML ({len(html) if html else 0}), trying Google-like search page...")

    # Try GET-based search (some EmpireCMS versions support this)
    for path in ['/e/search/result.php?searchid=1&keyboard=Avatar',
                 '/search/?keyboard=Avatar',
                 '/e/search/index.php?keyboard=Avatar&show=title&tbname=article',
                 '/s/Avatar/',
                 '/so/Avatar.html']:
        url = 'https://www.6v520.com' + path
        resp = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
        print(f"  GET {path}: {resp.status_code} len={len(resp.text)} title={resp.url[:40]}")
        if resp.status_code == 200 and len(resp.text) > 2000:
            soup = BeautifulSoup(resp.text, 'lxml')
            magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
            links = [(a['href'][:50], a.get_text(strip=True)[:30]) for a in soup.find_all('a', href=True) if a.get_text(strip=True) and '/dy/' in a.get('href', '')][:5]
            if magnets or links:
                print(f"    MAGNETS: {len(magnets)} MOVIE_LINKS: {len(links)}")
                for h, t in links:
                    print(f"    {h} | {t}")
