import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import sys, re, base64, json
from collections import OrderedDict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

names = ['磁力熊猫', '凌风云', '磁力大全', '种子吧', '比特大雄', 'bthaha', '博世', '老王磁力', '磁力宅', 'BT天堂', '磁力', 'seed8']

resp = requests.get('https://www.swnav.cn', headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
soup = BeautifulSoup(resp.text, 'lxml')

term_el = soup.find(id='term-291254-6744')
if term_el:
    print('Found term anchor')
    href = term_el.get('href', '')
    data_action = term_el.get('data-action', '')
    data_id = term_el.get('data-id', '')
    taxonomy = term_el.get('data-taxonomy', '')
    print(f'  href={href} data-action={data_action} data-id={data_id} taxonomy={taxonomy}')
    for attr in term_el.attrs:
        print(f'  attr {attr}={term_el.get(attr)}')

for a in soup.find_all('a', href=True):
    text = a.get_text(' ', strip=True)
    href = a.get('href', '').strip()
    if 'term-291254' in href:
        print(f'TERM LINK: {text[:60]} href={href}')
        for attr in a.attrs:
            print(f'  attr {attr}={a.get(attr)}')

for tag in soup.find_all(attrs={'data-id': True}):
    text = tag.get_text(' ', strip=True)
    if '磁力' in text:
        print(f'DATA-ID element: {text[:60]} data-id={tag.get("data-id")} data-action={tag.get("data-action")}')

ajax_urls = [
    'https://www.swnav.cn/wp-admin/admin-ajax.php?action=load_home_tab&taxonomy=favorites&term_id=6744',
    'https://www.swnav.cn/wp-admin/admin-ajax.php?action=load_home_tab&taxonomy=favorites&id=6744',
    'https://www.swnav.cn/?action=load_home_tab&taxonomy=favorites&term_id=6744',
]
for url in ajax_urls:
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.swnav.cn/'}, timeout=10)
        print(f'AJAX {url}: status={r.status_code} len={len(r.text)}')
        if r.status_code == 200 and len(r.text) > 200:
            ss = BeautifulSoup(r.text, 'lxml')
            for a in ss.find_all('a', href=True):
                t = a.get_text(' ', strip=True)
                h = a.get('href', '')
                du = a.get('data-url', '')
                title = a.get('title', '')
                combined = f'{t} {title}'.lower()
                for name in names:
                    if name.lower() in combined:
                        real = du if du else h
                        if not real or real.startswith('#'):
                            continue
                        if not real.startswith('http'):
                            real = 'https://' + real.lstrip('/')
                        print(f'  FOUND [{name}] {t[:50]} -> {real}')
                        break
            all_links = [(a.get_text(' ',strip=True)[:40], a.get('href','')) for a in ss.find_all('a', href=True) if a.get('href','').startswith('http')]
            if all_links:
                print(f'  ALL LINKS ({len(all_links)}):')
                for t, h in all_links[:30]:
                    print(f'    {t:40s} -> {h}')
    except Exception as e:
        print(f'AJAX {url}: error {e}')
