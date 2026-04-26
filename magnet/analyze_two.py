"""Analyze 6v520.com and seedhub.cc page structure."""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

SITES = [
    ('6v520 - home', 'https://www.6v520.com/'),
    ('6v520 - search guess', 'https://www.6v520.com/search?q=Inception'),
    ('6v520 - search2', 'https://www.6v520.com/index.php?m=vod-search&wd=Inception'),
    ('6v520 - search3', 'https://www.6v520.com/vodsearch/Inception/'),
    ('6v520 - s', 'https://www.6v520.com/so/Inception.html'),
    ('seedhub - home', 'https://www.seedhub.cc/'),
    ('seedhub - search', 'https://www.seedhub.cc/search?q=Inception'),
    ('seedhub - search2', 'https://www.seedhub.cc/search/Inception/'),
    ('seedhub - s', 'https://www.seedhub.cc/s?q=Inception'),
]

hash_re = re.compile(r'[0-9A-Fa-f]{40}')

for name, url in SITES:
    print(f"\n{'='*60}")
    print(f"{name}: {url}")
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        print(f"Status: {resp.status_code}  Final: {resp.url[:60]}  Len: {len(resp.text)}")
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, 'lxml')

        forms = soup.find_all('form')
        if forms:
            for f in forms[:3]:
                action = f.get('action', '')
                method = f.get('method', 'GET')
                inputs = [(i.get('name', ''), i.get('type', ''), i.get('placeholder', '')) for i in f.find_all('input')]
                selects = [(s.get('name', ''), s.get('id', '')) for s in f.find_all('select')]
                print(f"  Form: action={action} method={method} inputs={inputs} selects={selects}")

        magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
        hashes = set()
        for a in soup.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if m:
                hashes.add(m.group(1))

        print(f"  Magnets: {len(magnets)}  Hashes: {len(hashes)}")

        if magnets:
            for m in magnets[:3]:
                print(f"    magnet: {m.get('href', '')[:80]}")

        all_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if href and text and len(text) > 2 and not href.startswith('javascript:'):
                all_links.append((href[:60], text[:40]))
        if all_links:
            print(f"  Links ({len(all_links)} total, showing first 15):")
            for h, t in all_links[:15]:
                print(f"    {h:60s} | {t}")

        title = soup.title.string[:50] if soup.title and soup.title.string else 'N/A'
        print(f"  Title: {title}")

    except Exception as e:
        print(f"  ERROR: {str(e)[:60]}")
