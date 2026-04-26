"""Probe sites that returned pages but no magnets - check actual search URLs."""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

SITES = [
    ('rarbg.to', 'https://rarbg.to/torrents.php?search=Ubuntu', 'https://rarbg.to'),
    ('rarbg.to/index', 'https://rarbg.to/index.php?search=Ubuntu', 'https://rarbg.to'),
    ('limetorrents.pro', 'https://limetorrents.pro/search/all/Ubuntu/', 'https://limetorrents.pro'),
    ('demonoid.is', 'https://demonoid.is/files/?q=Ubuntu', 'https://demonoid.is'),
    ('mteam.cc', 'https://kp.mteam.cc/index.php', 'https://kp.mteam.cc'),
    ('hdhome.org', 'https://hdhome.org/index.php', 'https://hdhome.org'),
    ('audiences.me', 'https://audiences.me/index.php', 'https://audiences.me'),
]

SEP = '=' * 50
for name, url, origin in SITES:
    print()
    print(SEP)
    print(f'{name}: {url}')
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        print(f'Status: {resp.status_code}  Len: {len(resp.text)}  Final URL: {resp.url[:80]}')
        soup = BeautifulSoup(resp.text, 'lxml')
        title = soup.title.string if soup.title else 'N/A'
        print(f'Title: {title[:80]}')
        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        print(f'Magnets: {len(magnets)}')
        text = soup.get_text(separator=' ', strip=True)
        print(f'Text: {text[:200]}')
        if 'login' in text.lower() or 'sign in' in text.lower() or 'register' in text.lower():
            print('LOGIN WALL DETECTED')
    except Exception as e:
        print(f'ERROR: {e}')
