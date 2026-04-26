"""Analyze actual page structure of China-accessible sites."""
import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

SITES = [
    ('cilimao.biz', 'https://cilimao.biz'),
    ('cilitiantang.vip', 'https://www.cilitiantang.vip'),
    ('cilijun.com', 'https://cilijun.com/search/Ubuntu/1/0/0.html'),
    ('cilihezi.com', 'https://cilihezi.com'),
    ('btcat.bid', 'https://www.btcat.bid'),
    ('zhongziso.in', 'https://www.zhongziso.in'),
    ('wuqianaa.xyz', 'https://wuqianaa.xyz'),
    ('cili5.net', 'https://www.cili5.net'),
    ('cilihezi.top', 'https://www.cilihezi.top'),
    ('bashi5.com', 'https://bashi5.com'),
    ('cldq.cc', 'https://cldq.cc'),
    ('12580.org', 'https://12580.org'),
]

for name, url in SITES:
    print(f"\n{'='*50}")
    print(f"{name}: {url}")
    try:
        resp = requests.get(url, timeout=12, headers=HEADERS, allow_redirects=True)
        print(f"Status: {resp.status_code}  Final: {resp.url[:60]}  Len: {len(resp.text)}")
        soup = BeautifulSoup(resp.text, 'lxml')
        title = soup.title.string[:60] if soup.title else 'N/A'
        print(f"Title: {title}")

        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hash_re = re.compile(r'[0-9A-Fa-f]{40}')
        hash_urls = [a for a in soup.find_all('a', href=True) if hash_re.search(a['href'])]
        forms = soup.find_all('form')
        search_inputs = soup.find_all('input', {'type': 'search'}) + soup.find_all('input', {'name': re.compile(r'q|search|keyword|wd', re.I)})

        print(f"Magnets: {len(magnets)}  HashURLs: {len(hash_urls)}  Forms: {len(forms)}  SearchInputs: {len(search_inputs)}")

        if forms:
            for f in forms[:3]:
                action = f.get('action', '')
                method = f.get('method', 'GET')
                inputs_info = [(i.get('name', ''), i.get('type', '')) for i in f.find_all('input')]
                print(f"  Form: action={action} method={method} inputs={inputs_info}")

        all_links = [a['href'][:60] for a in soup.find_all('a', href=True)][:10]
        print(f"Top links: {all_links}")

        text = soup.get_text(strip=True)[:150]
        print(f"Text: {text}")
    except Exception as e:
        print(f"ERROR: {e}")
