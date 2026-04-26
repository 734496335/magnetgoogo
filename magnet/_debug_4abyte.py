import requests
from bs4 import BeautifulSoup

html = requests.get('https://www.4abyte.com', headers={'User-Agent': 'Mozilla/5.0'}, timeout=30).text
idx = html.find('id="term-1389"')
print('idx', idx)
print(html[idx:idx + 5000].encode('unicode_escape').decode())
soup = BeautifulSoup(html, 'lxml')
el = soup.find(id='term-1389')
print('el', el.name if el else None, el.get_text(' ', strip=True)[:80] if el else '')
for parent_level in range(1, 6):
    p = el
    for _ in range(parent_level):
        p = p.parent if p else None
    if not p:
        break
    links = p.find_all('a', href=True)
    print('parent', parent_level, p.name, len(links), p.get('class'))
    for a in links[:20]:
        print(' ', a.get_text(' ', strip=True)[:60], a.get('href'))
