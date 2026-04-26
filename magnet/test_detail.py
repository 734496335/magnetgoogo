import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
url = 'https://www.torrentdownload.info/DD8255ECDC7CA55FB0BBF81323D87062DB1F6D1C/Big-Buck-Bunny'
resp = requests.get(url, timeout=15, headers=headers)
soup = BeautifulSoup(resp.text, 'lxml')
magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
print(f'Status: {resp.status_code}  Magnets: {len(magnets)}')
for m in magnets:
    print(f'  {m["href"][:120]}')
t = soup.title.string[:60] if soup.title else 'N/A'
print(f'Title: {t}')

print('\n--- Detail page links ---')
for a in soup.find_all('a', href=True):
    h = a['href']
    if 'magnet' in h or 'download' in h:
        print(f'  {h[:120]}')
