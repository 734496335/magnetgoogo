import sys; sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re, time, json

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--disable-gpu')
opts.add_argument('--no-sandbox')
opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
driver = webdriver.Chrome(options=opts)
driver.set_page_load_timeout(20)

def probe(name, url, search_url=None):
    print(f'\n{"="*60}')
    print(f'  {name}: {url}')
    print(f'{"="*60}')
    
    # Homepage
    driver.get(url)
    time.sleep(6)
    html = driver.page_source
    s = BeautifulSoup(html, 'lxml')
    title = s.title.string if s.title else 'N/A'
    print(f'Homepage: len={len(html)}, title={title}')
    
    for f in s.find_all('form'):
        print(f'Form: action={f.get("action")} method={f.get("method")}')
        for i in f.find_all('input'):
            print(f'  input: name={i.get("name")} type={i.get("type")}')
    
    # Search
    if search_url:
        print(f'\nSearching: {search_url}')
        driver.get(search_url)
        time.sleep(6)
        html2 = driver.page_source
        s2 = BeautifulSoup(html2, 'lxml')
        
        magnets = s2.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        print(f'Magnet links: {len(magnets)}')
        
        hashes = []
        for a in s2.find_all('a', href=True):
            m = re.search(r'[0-9A-Fa-f]{40}', a['href'])
            if m:
                hashes.append((m.group(0), a.get_text(strip=True)[:60]))
        print(f'Hash links: {len(hashes)}')
        
        # Show all non-trivial links
        shown = 0
        for a in s2.find_all('a', href=True):
            href = a['href']
            txt = a.get_text(strip=True)
            if href and len(href) > 5 and txt and len(txt) > 3:
                print(f'  LINK: {href[:100]} | {txt[:60]}')
                shown += 1
                if shown > 25:
                    break
        
        # Also dump a portion of HTML for analysis
        print(f'\nHTML preview (first 3000 chars of body):')
        body = s2.find('body')
        if body:
            txt = body.get_text()[:3000]
            print(txt[:2000])

probe('BTSOW', 'https://btsow.pics', 'https://btsow.pics/search/Big Buck Bunny')
probe('0MAGNET', 'https://0magnet.co', 'https://0magnet.co/search?q=Big Buck Bunny')

# 0magnet.co retry (unstable first time)
print('\n=== 0MAGNET RETRY ===')
driver.get('https://0magnet.co/search?q=Ubuntu')
time.sleep(8)
html3 = driver.page_source
s3 = BeautifulSoup(html3, 'lxml')
m3 = s3.find_all('a', href=lambda h: h and h.startswith('magnet:'))
print(f'Retry magnets: {len(m3)}')
shown = 0
for a in s3.find_all('a', href=True):
    href = a['href']
    txt = a.get_text(strip=True)
    if href and len(href) > 5 and txt and len(txt) > 3:
        print(f'  LINK: {href[:100]} | {txt[:60]}')
        shown += 1
        if shown > 25:
            break

driver.quit()
