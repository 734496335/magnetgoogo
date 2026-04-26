"""Final attempt: test more China-accessible sites from nav hubs + known DHT engines."""
import requests
from bs4 import BeautifulSoup
import re, time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}
hash_re = re.compile(r'[0-9A-Fa-f]{40}')

SITES = [
    ('tgcloud.cyou', 'https://www.tgcloud.cyou'),
    ('cili.one', 'https://cili.one/search?q=Ubuntu'),
    ('mag.net', 'https://mag.net/search?q=Ubuntu'),
    ('cilibili.fun', 'https://cilibili.fun/search?q=Ubuntu'),
    ('cili.date', 'https://cili.date/search?q=Ubuntu'),
    ('cili.day', 'https://cili.day/search?q=Ubuntu'),
    ('btbus.app', 'https://btbus.app/search?q=Ubuntu'),
    ('btdigg', 'http://btdigg.org/search?q=Ubuntu'),
    ('btdig', 'https://btdig.com/search?q=Ubuntu'),
    ('torrentdownload.info', 'https://www.torrentdownload.info/search?q=Ubuntu'),
    ('animetosho', 'https://animetosho.org/search?q=One+Piece'),
    ('souxung', 'https://www.souxung.com/search?q=Ubuntu'),
    ('cilibra', 'https://cilibra.org/search?q=Ubuntu'),
    ('cilibra.net', 'https://cilibra.net/search?q=Ubuntu'),
    ('cilibra.xyz', 'https://cilibra.xyz/search?q=Ubuntu'),
    ('xiguasousou', 'https://www.xiguasousou.com/search?q=Ubuntu'),
    ('btsow', 'https://www.btsow.vip/search/Ubuntu'),
    ('ciLiMaO2', 'https://www.cilimaocili.com/search?q=Ubuntu'),
    ('clmaoc.top', 'https://clmaoc.top/search?q=Ubuntu'),
    ('ciliss', 'https://www.ciliss.cc/search?q=Ubuntu'),
]

for name, url in SITES:
    print(f"\n{name}: {url}")
    try:
        resp = requests.get(url, timeout=12, headers=HEADERS, allow_redirects=True)
        print(f"  Status: {resp.status_code}  Len: {len(resp.text)}  Final: {resp.url[:50]}")
        if resp.status_code != 200 or len(resp.text) < 100:
            continue
        soup = BeautifulSoup(resp.text, 'lxml')
        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hashes = set()
        for a in soup.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if m:
                hashes.add(m.group(1))
        title = soup.title.string[:40] if soup.title and soup.title.string else ''
        print(f"  Title: {title}")
        print(f"  Magnets: {len(magnets)}  Hashes: {len(hashes)}")
        if magnets:
            for m in magnets[:2]:
                print(f"    {m.get('href', '')[:80]}")
        if hashes and not magnets:
            count = 0
            for a in soup.find_all('a', href=True):
                m = hash_re.search(a['href'])
                if m:
                    print(f"    {a['href'][:50]} | {a.get_text(strip=True)[:30]}")
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
