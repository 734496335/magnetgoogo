import sys;sys.stdout.reconfigure(encoding='utf-8',errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re,time

HASH_RE=re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')

opts=Options()
opts.add_argument('--headless');opts.add_argument('--disable-gpu');opts.add_argument('--no-sandbox')
d=webdriver.Chrome(options=opts)
d.set_page_load_timeout(20)

# 1) ciligou publish page
print('=== ciligoufabuye3.xyz ===')
d.get('https://www.ciligoufabuye3.xyz')
time.sleep(6)
s=BeautifulSoup(d.page_source,'lxml')
for a in s.find_all('a',href=True):
    h=a['href'];t=a.get_text(strip=True)
    if h.startswith('http') and t:
        print('  PUBLISH:',h[:70],'|',t[:50])

# 2) ciligou real
print('\n=== clg2.clgapp1.xyz ===')
d.get('https://clg2.clgapp1.xyz')
time.sleep(5)
s=BeautifulSoup(d.page_source,'lxml')
title=s.title.string if s.title else 'N/A'
print('Title:',title)
for f in s.find_all('form'):
    act=f.get('action','');method=f.get('method','')
    inputs=[(i.get('name',''),i.get('type','')) for i in f.find_all('input')]
    print('  Form:',act,method,inputs)

# try searches
for bait in ['Ubuntu','Big Buck Bunny']:
    for sp in ['/search/'+bait,'/search?keyword='+bait,'/search?q='+bait,'/?q='+bait,'/s/'+bait]:
        try:
            d.get('https://clg2.clgapp1.xyz'+sp)
            time.sleep(4)
            s2=BeautifulSoup(d.page_source,'lxml')
            magnets=[a for a in s2.find_all('a',href=lambda h:h and h.startswith('magnet:'))]
            hashes=set()
            for a in s2.find_all('a',href=True):
                m=HASH_RE.search(a['href'])
                if m: hashes.add(m.group(0).upper())
            if magnets or hashes:
                print('  FOUND:',sp,'magnets='+str(len(magnets)),'hashes='+str(len(hashes)))
                for m in magnets[:3]:
                    print('    MAG:',m['href'][:80])
                break
        except: pass

# 3) ymaoo.cn
print('\n=== ymaoo.cn ===')
d.get('https://www.ymaoo.cn')
time.sleep(5)
s=BeautifulSoup(d.page_source,'lxml')
print('Title:',s.title.string if s.title else 'N/A')

# find category/section links
for a in s.find_all('a',href=True):
    h=a['href'];t=a.get_text(strip=True)
    tl=t.lower()
    if any(kw in tl for kw in ['下载','磁力','bt','torrent','种子','影视下载','资源下载','片源','影视资源']):
        print('  SECTION:',h[:60],'|',t[:40])

# all external links
seen=set()
for a in s.find_all('a',href=True):
    h=a['href'];t=a.get_text(strip=True)
    if not h.startswith('http'): continue
    dom=urlparse(h).netloc.lower().replace('www.','')
    if dom and 'ymaoo' not in dom and dom not in seen and t:
        seen.add(dom)
        print('  LINK:',dom,'|',t[:40])

# 4) 4abyte.com
print('\n=== 4abyte.com ===')
d.get('https://www.4abyte.com')
time.sleep(5)
s=BeautifulSoup(d.page_source,'lxml')
print('Title:',s.title.string if s.title else 'N/A')

for a in s.find_all('a',href=True):
    h=a['href'];t=a.get_text(strip=True)
    tl=t.lower()
    if any(kw in tl for kw in ['下载','磁力','bt','torrent','种子','影视下载','资源下载','片源','影视资源']):
        print('  SECTION:',h[:60],'|',t[:40])

seen=set()
for a in s.find_all('a',href=True):
    h=a['href'];t=a.get_text(strip=True)
    if not h.startswith('http'): continue
    dom=urlparse(h).netloc.lower().replace('www.','')
    if dom and '4abyte' not in dom and '4a' not in dom and dom not in seen and t:
        seen.add(dom)
        print('  LINK:',dom,'|',t[:40])

d.quit()
