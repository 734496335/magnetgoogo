import sys;sys.stdout.reconfigure(encoding='utf-8',errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from urllib.parse import urlparse,urljoin
import re,time,json

HASH_RE=re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')

TORRENT_SECTION_KW=['磁力','BT','种子','torrent','magnet','下载专区','影视下载','资源下载','片源','番号']
EXCLUDE_KW=['在线观看','直播','新闻','购物','AI工具','音乐播放','政府','教育']

opts=Options()
opts.add_argument('--headless');opts.add_argument('--disable-gpu');opts.add_argument('--no-sandbox')
opts=Options()
opts.add_argument('--headless');opts.add_argument('--disable-gpu');opts.add_argument('--no-sandbox')
opts.add_argument('--window-size=1920,1080')
opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
d=webdriver.Chrome(options=opts)
d.set_page_load_timeout(25)

results={}
nav_sites=['https://www.ymaoo.cn','https://www.4abyte.com']

for nav_url in nav_sites:
    print(f'\n{"="*60}')
    print(f'  NAV: {nav_url}')
    print(f'{"="*60}')
    try:
        d.get(nav_url)
        time.sleep(6)
    except Exception as e:
        print(f'  FAILED: {e}')
        continue

    html=d.page_source
    s=BeautifulSoup(html,'lxml')
    title=s.title.string.strip()[:60] if s.title and s.title.string else ''
    print(f'  Title: {title}')

    # Strategy: find ALL links, group by nearby heading text
    # First find headings that match torrent keywords
    torrent_headings=set()
    for tag in ['h1','h2','h3','h4','h5','div','span','dt','strong','b']:
        for el in s.find_all(tag):
            txt=el.get_text(strip=True)
            if not txt or len(txt)>30: continue
            tl=txt.lower()
            if any(kw.lower() in tl for kw in TORRENT_SECTION_KW):
                if not any(kw.lower() in tl for kw in EXCLUDE_KW):
                    torrent_headings.add(id(el))
                    # mark parent and siblings
                    p=el.parent
                    if p: torrent_headings.add(id(p))
                    for sib in list(el.next_siblings)[:20]:
                        if hasattr(sib,'find_all'): torrent_headings.add(id(sib))
                    # also mark grandparent section
                    if p and p.parent: torrent_headings.add(id(p.parent))

    # Collect ALL links with context
    all_links=[]
    for a in s.find_all('a',href=True):
        href=a['href']
        txt=a.get_text(strip=True)
        if not href or href.startswith(('#','javascript:','mailto:')): continue
        if not txt or len(txt)<2: continue

        # check if near a torrent heading
        near_torrent=False
        p=a
        for _ in range(8):
            p=p.parent
            if p is None: break
            if id(p) in torrent_headings:
                near_torrent=True
                break

        # check if link text itself has torrent keywords
        tl=txt.lower()
        text_match=any(kw.lower() in tl for kw in TORRENT_SECTION_KW)

        if near_torrent or text_match:
            full=urljoin(nav_url,href)
            dom=urlparse(full).netloc.lower().replace('www.','')
            if dom and full.startswith('http'):
                all_links.append({
                    'url':full,'domain':dom,'title':txt[:60],
                    'near_torrent':near_torrent,'text_match':text_match,
                })

    # Dedupe
    seen=set()
    unique=[]
    for l in all_links:
        if l['domain'] not in seen:
            seen.add(l['domain'])
            unique.append(l)

    print(f'  找到 {len(unique)} 个磁力相关链接:')
    for l in unique:
        mark='[section]' if l['near_torrent'] else '[keyword]'
        print(f'    {mark} {l["domain"]:30s} {l["title"][:40]}')

    results[nav_url]=unique

# Save
out_file='nav_extracted.json'
with open(out_file,'w',encoding='utf-8') as f:
    json.dump(results,f,indent=2,ensure_ascii=False)
print(f'\n已保存到 {out_file}')
d.quit()
