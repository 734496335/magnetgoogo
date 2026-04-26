"""Test China sources with correct search paths."""
import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

SITES = [
    ('cilihezi.com', 'https://cilihezi.com/search.php?keywords=Ubuntu'),
    ('cilihezi.com', 'https://cilihezi.com/search.php?keywords=Big+Buck+Bunny'),
    ('cili5.net/btfox', 'https://btfox12.top/?wd=Ubuntu'),
    ('cili5.net/btfox', 'https://btfox12.top/?wd=Big+Buck+Bunny'),
    ('cilihezi.top', 'https://www.cilihezi.top/?s=Ubuntu'),
    ('cilihezi.top', 'https://www.cilihezi.top/?s=Big+Buck+Bunny'),
    ('cilimao.biz', 'https://cilimao.im/search?q=Ubuntu'),
    ('cilimao.biz', 'https://clm8.top/search?q=Ubuntu'),
    ('cilijun.com', 'https://cilijun.com/search/Ubuntu/1/0/0.html'),
    ('cilitiantang.vip', 'https://www.cilitiantang.vip/search?q=Ubuntu'),
    ('cilitiantang.vip', 'https://cltt.me/search?q=Ubuntu'),
    ('ezhentang.com', 'https://ezhentang.com/search?q=Ubuntu'),
    ('cilisousuoyinqng', 'https://cilsousuoyinqng.com.cn/search?q=Ubuntu'),
]

hash_re = re.compile(r'[0-9A-Fa-f]{40}')

for name, url in SITES:
    print(f"\n{'='*50}")
    print(f"{name}: {url}")
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        print(f"Status: {resp.status_code}  Final: {resp.url[:60]}  Len: {len(resp.text)}")
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, 'lxml')
        title = soup.title.string[:60] if soup.title else 'N/A'
        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hash_urls = [a for a in soup.find_all('a', href=True) if hash_re.search(a['href'])]

        print(f"Title: {title}")
        print(f"Magnets: {len(magnets)}  HashURLs: {len(hash_urls)}")

        if magnets:
            for m in magnets[:3]:
                href = m.get('href', '')[:80]
                text = m.get_text(strip=True)[:40]
                print(f"  magnet: {href}")
                print(f"  text: {text}")

        if hash_urls:
            for a in hash_urls[:3]:
                print(f"  hash-link: {a['href'][:60]} | {a.get_text(strip=True)[:40]}")

        if not magnets and not hash_urls and len(resp.text) > 500:
            text = soup.get_text(strip=True)[:200]
            print(f"Text: {text}")
            all_hrefs = [a['href'][:50] for a in soup.find_all('a', href=True)][:10]
            print(f"Links: {all_hrefs}")

    except Exception as e:
        print(f"ERROR: {e}")
