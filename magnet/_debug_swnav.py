import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

resp = requests.get('https://www.swnav.cn', headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
soup = BeautifulSoup(resp.text, 'lxml')

names = ['磁力熊猫', '凌风云', '磁力大全', '种子吧', '比特大雄', 'bthaha', '博世', '老王磁力', '磁力宅', 'BT天堂', '磁力']

for a in soup.find_all('a', href=True):
    text = a.get_text(' ', strip=True)
    href = a.get('href', '').strip()
    title = a.get('title', '') or ''
    data_url = a.get('data-url', '') or ''
    combined = f'{text} {title}'
    for name in names:
        if name.lower() in combined.lower():
            print(f'MATCH [{name}] text={text[:80]} href={href} data-url={data_url}')
            break

for h in soup.find_all(['h2', 'h3', 'h4']):
    text = h.get_text(' ', strip=True)
    lower = text.lower()
    if any(kw in lower for kw in ['磁力', 'bt', '种子', '资源搜索', 'torrent', '片源']):
        print(f'HEADING: {text[:80]}')
        parent = h.parent
        if parent:
            for a in parent.find_all('a', href=True):
                at = a.get_text(' ', strip=True)
                ah = a.get('href', '')
                du = a.get('data-url', '')
                print(f'  LINK: {at[:60]} href={ah} data-url={du}')
