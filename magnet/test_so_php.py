"""Test cilihezi.com/so.php and similar actual search endpoints."""
import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

SITES = [
    ('cilihezi/so.php', 'https://cilihezi.com/so.php?q=Ubuntu'),
    ('cilihezi/so.php', 'https://cilihezi.com/so.php?keywords=Ubuntu'),
    ('cilihezi/so.php', 'https://cilihezi.com/so.php?wd=Ubuntu'),
    ('cilihezi/so.php', 'https://cilihezi.com/so.php?search=Ubuntu'),
    ('cilihezi/so', 'https://cilihezi.com/so?q=Ubuntu'),
    ('torrentdownload', 'https://www.torrentdownload.info/search?q=Ubuntu'),
    ('animetosho', 'https://animetosho.org/search?q=Ubuntu'),
]

hash_re = re.compile(r'[0-9A-Fa-f]{40}')

for name, url in SITES:
    print(f"\n{name}: {url}")
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        ct = resp.headers.get('content-type', '')[:30]
        print(f"  Status: {resp.status_code}  Len: {len(resp.text)}  Final: {resp.url[:60]}")
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, 'lxml')
        title = soup.title.string[:50] if soup.title else 'N/A'
        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hashes = set()
        for a in soup.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if m:
                hashes.add(m.group(1))
        print(f"  Title: {title}")
        print(f"  Magnets: {len(magnets)}  Hashes: {len(hashes)}")
        if magnets:
            for m in magnets[:2]:
                print(f"    {m.get('href', '')[:80]}")
        if hashes:
            count = 0
            for a in soup.find_all('a', href=True):
                m = hash_re.search(a['href'])
                if m:
                    print(f"    {a['href'][:60]} | {a.get_text(strip=True)[:40]}")
                    count += 1
                    if count >= 3:
                        break
    except Exception as e:
        print(f"  ERROR: {str(e)[:60]}")
