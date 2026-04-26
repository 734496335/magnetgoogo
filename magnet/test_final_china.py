"""Final round: test all promising China-accessible magnet sources."""
import requests
from bs4 import BeautifulSoup
import re, time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}
hash_re = re.compile(r'[0-9A-Fa-f]{40}')

SITES = [
    ('bt.biedian.me', 'https://bt.biedian.me/search?q=Ubuntu'),
    ('ciliss.cc', 'https://www.ciliss.cc/search?q=Ubuntu'),
    ('cili8.biz', 'https://www.cili8.biz/search?q=Ubuntu'),
    ('cilibili', 'https://www.cilibili.com/search?q=Ubuntu'),
    ('cilibili', 'https://www.cilibili.net/search?q=Ubuntu'),
    ('btbtt.net', 'https://www.btbtt.net/search?q=Ubuntu'),
    ('btbtt20.com', 'https://btbtt20.com/search?q=Ubuntu'),
    ('ciLiMaO', 'https://www.cilimaocili.com/search?q=Ubuntu'),
    ('clmaoc.top', 'https://clmaoc.top/search?q=Ubuntu'),
    ('cili01.com', 'https://cili01.com/search?q=Ubuntu'),
    ('magbot', 'https://www.magbot.xyz/search?q=Ubuntu'),
    ('torrentkitty', 'https://www.torrentkitty.tv/search/Ubuntu/'),
    ('torrentkitty2', 'https://www.torrentkitty.net/search/Ubuntu/'),
    ('nyafun', 'https://nyafun.com/search?q=One+Piece'),
    ('mikan', 'https://mikanani.me/RSS/Search?searchword=One+Piece'),
    ('mikan', 'https://mikanime.tv/RSS/Search?searchword=Ubuntu'),
    ('acg.rip', 'https://acg.rip/search?q=One+Piece'),
    ('share.dmhy.org', 'https://share.dmhy.org/topics/list?keyword=One+Piece'),
    ('nyaa', 'https://nyaa.si/?f=0&q=One+Piece'),
    ('animetosho', 'https://animetosho.org/search?q=Ubuntu'),
    ('torrentdownload', 'https://www.torrentdownload.info/search?q=Ubuntu'),
]

for name, url in SITES:
    print(f"\n{name}: {url}")
    try:
        resp = requests.get(url, timeout=12, headers=HEADERS, allow_redirects=True)
        ct = resp.headers.get('content-type', '')[:30]
        print(f"  Status: {resp.status_code}  Len: {len(resp.text)}  Final: {resp.url[:50]}")
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, 'lxml')

        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hashes = set()
        for a in soup.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if m:
                hashes.add(m.group(1))

        title = soup.title.string[:50] if soup.title else 'N/A'
        print(f"  Title: {title}")
        print(f"  Magnets: {len(magnets)}  Hashes: {len(hashes)}")

        if magnets:
            for m in magnets[:2]:
                print(f"    magnet: {m.get('href', '')[:80]}")
        if hashes and not magnets:
            count = 0
            for a in soup.find_all('a', href=True):
                m = hash_re.search(a['href'])
                if m:
                    print(f"    hash: {a['href'][:50]} | {a.get_text(strip=True)[:30]}")
                    count += 1
                    if count >= 2:
                        break
    except requests.exceptions.Timeout:
        print(f"  TIMEOUT")
    except requests.exceptions.ConnectionError:
        print(f"  DNS FAIL")
    except Exception as e:
        print(f"  ERROR: {str(e)[:50]}")
    time.sleep(0.3)
