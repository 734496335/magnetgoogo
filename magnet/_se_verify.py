import sys; sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re, time

HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--disable-gpu')
opts.add_argument('--no-sandbox')
opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
driver = webdriver.Chrome(options=opts)
driver.set_page_load_timeout(20)

sites = [
    ('btsow.xyz', 'https://btsow.xyz/search/Big Buck Bunny'),
    ('btsow.live', 'https://btsow.live/search/Big Buck Bunny'),
    ('idope.xyz', 'https://idope.xyz/search?q=Big Buck Bunny'),
    ('btdigg.org', 'https://btdigg.org/search?q=Big Buck Bunny'),
    ('eztv.gold', 'https://eztv.gold/search/Big Buck Bunny'),
    ('thepiratebay.asia', 'https://thepiratebay.asia/search.php?q=Big Buck Bunny'),
    ('8.210.117.39', 'http://8.210.117.39/search?q=Big Buck Bunny'),
    ('thepiratebay10.org', 'https://thepiratebay10.org/search.php?q=Ubuntu'),
    ('torlock.com', 'https://torlock.com/search?q=Big Buck Bunny'),
    ('magnetdl.today', 'https://magnetdl.today/big+buck+bunny/'),
    ('1337x.unblockit.download', 'https://1337x.unblockit.download/search/Big Buck Bunny/1/'),
    ('tpb.party', 'https://tpb.party/search?q=Big Buck Bunny'),
    ('yts.mx', 'https://yts.mx/browse-movies/0/all/all/0/year/0/0'),
    ('torrentgalaxy.to', 'https://torrentgalaxy.to/torrents.php?search=Big Buck Bunny'),
    ('torlock.info', 'https://torlock.info/search?q=Big Buck Bunny'),
    ('kickasstorrents.to', 'https://kickasstorrents.to/usearch/Big Buck Bunny/'),
    ('nyaa.iss.ink', 'https://nyaa.iss.ink/?f=0&q=One+Piece'),
    'saved'
]

del sites[-1]

for name, url in sites:
    print(f'\n--- {name}: {url}')
    try:
        driver.get(url)
        time.sleep(6)
        html = driver.page_source
        soup = BeautifulSoup(html, 'lxml')
        title = soup.title.string.strip()[:50] if soup.title and soup.title.string else 'N/A'
        magnets = [a for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))]
        hashes = set()
        for a in soup.find_all('a', href=True):
            m = HASH_RE.search(a['href'])
            if m:
                hashes.add(m.group(0).upper())
        body_text = soup.get_text()[:500]
        print(f'  title: {title}')
        print(f'  magnets: {len(magnets)}, hashes: {len(hashes)}')
        if magnets:
            print(f'  SAMPLE: {magnets[0]["href"][:80]}')
        if hashes:
            for h in list(hashes)[:3]:
                print(f'  HASH: {h}')
        if not magnets and not hashes:
            print(f'  body preview: {body_text[:150]}')
    except Exception as e:
        print(f'  ERROR: {str(e)[:80]}')

driver.quit()
