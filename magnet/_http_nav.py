import sys;sys.stdout.reconfigure(encoding='utf-8',errors='replace')
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin,urlparse

HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
TORRENT_KW=['磁力','BT','种子','torrent','magnet','下载','影视下载','资源下载','片源','番号']
EXCLUDE=['在线观看','直播','新闻','购物','AI','音乐','政府','教育','设计','工具']

for nav in ['https://www.ymaoo.cn','https://www.4abyte.com']:
    print(f'\n=== {nav} ===')
    try:
        r=requests.get(nav,timeout=12,headers=HEADERS)
        print(f'HTTP {r.status_code} len={len(r.text)}')
        if r.status_code!=200 or len(r.text)<500:
            continue
    except Exception as e:
        print(f'FAILED: {e}')
        continue

    s=BeautifulSoup(r.text,'lxml')
    t=s.title
    tstr=t.string.strip()[:60] if t and t.string else 'N/A'
    print(f'Title: {tstr}')

    seen=set()
    for a in s.find_all('a',href=True):
        href=a['href']
        txt=a.get_text(strip=True)
        if not txt or len(txt)<2: continue
        if href.startswith('//'): href='https:'+href
        elif href.startswith('/'): href=urljoin(nav,href)
        if not href.startswith('http'): continue
        dom=urlparse(href).netloc.lower().replace('www.','')
        base=urlparse(nav).netloc.lower().replace('www.','')
        if dom and dom!=base and dom not in seen:
            seen.add(dom)
            tl=txt.lower()
            is_t=any(kw.lower() in tl for kw in TORRENT_KW)
            is_e=any(kw.lower() in tl for kw in EXCLUDE)
            marker='[BT]' if (is_t and not is_e) else '    '
            print(f'  {marker} {dom:30s} {txt[:45]}')
