"""Quick probe: analyze HTML structure of parsing_failed sites."""
import requests
from bs4 import BeautifulSoup

sites = [
    ('btso.cc', 'https://btso.cc/search?q=Ubuntu'),
    ('btdb.to', 'https://btdb.to/search?q=Ubuntu'),
    ('extratorrent.ag', 'https://extratorrent.ag/search?q=Ubuntu'),
    ('btbtt12.com', 'https://btbtt12.com/search?q=Ubuntu'),
    ('btcake.com', 'https://btcake.com/search?q=Ubuntu'),
    ('cilimao.com', 'https://cilimao.com/search?q=Ubuntu'),
    ('verycd.com', 'https://verycd.com/search?q=Ubuntu'),
    ('bitport.io', 'https://bitport.io'),
]

SEP = '=' * 60
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

for name, url in sites:
    print()
    print(SEP)
    print(f'SITE: {name}  URL: {url}')
    try:
        resp = requests.get(url, timeout=15, headers=headers)
        print(f'Status: {resp.status_code}  Length: {len(resp.text)}')
        soup = BeautifulSoup(resp.text, 'lxml')

        magnets = soup.find_all('a', href=lambda h: h and 'magnet:' in h)
        print(f'Direct magnet links: {len(magnets)}')

        title = soup.title.string if soup.title else 'N/A'
        print(f'Title: {title[:100]}')

        text = soup.get_text(separator=' ', strip=True)
        print(f'Text preview: {text[:300]}')

        links_with_magnet_kw = [a for a in soup.find_all('a')
                                if 'magnet' in (a.get('href', '') + ' ' + a.get_text()).lower()]
        print(f'Links with magnet keyword: {len(links_with_magnet_kw)}')

        all_hrefs = [a.get('href', '')[:80] for a in soup.find_all('a', href=True)][:20]
        print(f'Top links: {all_hrefs}')

        has_kw = 'torrent' in text.lower() or 'magnet' in text.lower()
        print(f'Contains torrent/magnet keywords: {"YES" if has_kw else "NO"}')

        if len(resp.text) < 1000:
            print(f'Full HTML: {resp.text}')
        else:
            print(f'HTML sample: {resp.text[:500]}')

    except Exception as e:
        print(f'ERROR: {e}')
