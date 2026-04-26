"""Check torrentdownload.info search page for embedded hashes/magnets."""
import requests
from bs4 import BeautifulSoup
import re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

for q in ['Interstellar', 'Ubuntu']:
    url = f'https://www.torrentdownload.info/search?q={q}'
    print(f'\n{"="*50}')
    print(f'Query: {q}')
    try:
        resp = requests.get(url, timeout=20, headers=headers)
    except Exception as e:
        print(f'ERROR: {e}')
        continue

    print(f'Status: {resp.status_code}  Len: {len(resp.text)}')

    magnet_in_html = re.findall(r'magnet:\?[^"\'<>\s]+', resp.text)
    print(f'Magnet URIs in raw HTML: {len(magnet_in_html)}')
    for m in magnet_in_html[:3]:
        print(f'  {m[:100]}')

    hash_pattern = re.findall(r'[0-9A-Fa-f]{40}', resp.text)
    print(f'40-char hex hashes: {len(hash_pattern)}')
    for h in hash_pattern[:5]:
        print(f'  {h}')

    soup = BeautifulSoup(resp.text, 'lxml')
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) > 5:
            print(f'\nMain table ({len(rows)} rows):')
            for row in rows[1:6]:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    link = cells[0].find('a')
                    title = link.get_text(strip=True)[:50] if link else cells[0].get_text(strip=True)[:50]
                    href = link['href'][:60] if link else ''
                    size = cells[-1].get_text(strip=True) if len(cells) > 1 else ''
                    print(f'  {title:50s} | {href}')
            break
