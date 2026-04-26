"""Test limetorrents.fun search functionality."""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

urls = [
    'https://www.limetorrents.fun/search/all/Ubuntu/',
    'https://www.limetorrents.fun/',
    'https://limetorrents.pro/',
    'https://tellme.pw/bts',
    'https://btsow.com/search/Ubuntu',
]

for url in urls:
    print(f'\n{"="*50}')
    print(f'URL: {url}')
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        print(f'Status: {resp.status_code}  Final: {resp.url[:60]}  Len: {len(resp.text)}')
        soup = BeautifulSoup(resp.text, 'lxml')
        title = soup.title.string[:60] if soup.title else 'N/A'
        print(f'Title: {title}')
        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        print(f'Magnets: {len(magnets)}')
        text = soup.get_text(separator=' ', strip=True)
        print(f'Text: {text[:200]}')
    except Exception as e:
        print(f'ERROR: {e}')
