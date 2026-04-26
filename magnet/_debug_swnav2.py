import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

resp = requests.get('https://www.swnav.cn', headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
soup = BeautifulSoup(resp.text, 'lxml')

term = soup.find(id='term-291254-6744')
if not term:
    print('NOT FOUND term')
    sys.exit(1)

print('TERM:', term.name, term.get_text(' ', strip=True)[:80])

scope = term.parent
for _ in range(3):
    if scope.parent and len(scope.find_all('a', href=True)) < 5:
        scope = scope.parent

links = scope.find_all('a', href=True)
print(f'Links in scope: {len(links)}')

for a in links:
    text = a.get_text(' ', strip=True)
    href = a.get('href', '').strip()
    title = a.get('title', '') or ''
    data_url = a.get('data-url', '') or ''
    if not href or href.startswith('#'):
        continue
    if not href.startswith('http'):
        href = urljoin('https://www.swnav.cn', href)
    if data_url:
        real = data_url if data_url.startswith('http') else 'https://' + data_url.lstrip('/')
    else:
        real = href
    print(f'  {text[:50]:50s} -> {real}')
