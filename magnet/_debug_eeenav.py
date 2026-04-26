import requests
from bs4 import BeautifulSoup
import sys, json
from collections import OrderedDict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

names = ['磁力多', '磁力夜', '搜番', '磁力星球', '磁力猫', '磁力狐', 'Knaben', '老王磁力', '91BT', '吴签磁力', 'BT1207', '磁力宝', 'BT联盟', '磁力柠檬', 'SkrBT', 'BT搜索联盟', '无极磁链', '磁力先锋', '磁力发', '磁力王', '磁力狗']

resp = requests.get('https://eeenav.com/favorites/cilss', headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://eeenav.com/'}, timeout=20)
print(f'status={resp.status_code} len={len(resp.text)}')
soup = BeautifulSoup(resp.text, 'lxml')

results = OrderedDict()
for a in soup.find_all('a', href=True):
    text = a.get_text(' ', strip=True)
    href = a.get('href', '').strip()
    title = a.get('title', '') or ''
    data_url = a.get('data-url', '') or ''
    combined = f'{text} {title}'.lower()
    matched = ''
    for name in names:
        if name.lower() in combined:
            matched = name
            break
    if not matched:
        continue
    real = data_url if data_url else href
    if not real or real.startswith('#'):
        continue
    if not real.startswith('http'):
        real = 'https://' + real.lstrip('/')
    domain = real.split('://', 1)[-1].split('/', 1)[0].lower().removeprefix('www.')
    print(f'  [{matched:12s}] {text[:50]:50s} -> {real}')
    if matched not in results:
        results[matched] = {'url': real, 'domain': domain, 'brand': matched, 'title': text[:120]}

with open(r'D:\lpproduct\magnet\nav_site_crawler_report.json', 'w', encoding='utf-8') as f:
    json.dump({
        'generated_at': '2026-04-20',
        'country': 'korea',
        'real_candidates': list(results.values()),
        'verified': [],
    }, f, indent=2, ensure_ascii=False)
print(f'\nTotal: {len(results)}')
