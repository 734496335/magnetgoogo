"""Analyze navigation hub sites to understand link structure."""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re, json

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

NAV_SITES = [
    ('cilihezi.com', 'https://cilihezi.com'),
    ('bashi5.com', 'https://bashi5.com'),
    ('cilimao.biz', 'https://cilimao.biz'),
    ('cilihezi.top', 'https://www.cilihezi.top'),
    ('cilitiantang.vip', 'https://www.cilitiantang.vip'),
    ('cili5.net', 'https://www.cili5.net'),
    ('cilihezi.com/link', 'https://cilihezi.com/link.html'),
    ('cldq.cc', 'https://cldq.cc'),
    ('ezhentang.com', 'https://ezhentang.com'),
]

all_discovered = {}

for name, url in NAV_SITES:
    print(f"\n{'='*60}")
    print(f"NAV: {name} ({url})")
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
        print(f"Status: {resp.status_code}  Final: {resp.url[:50]}  Len: {len(resp.text)}")
        if resp.status_code != 200 or len(resp.text) < 200:
            continue

        soup = BeautifulSoup(resp.text, 'lxml')
        title = soup.title.string[:50] if soup.title else 'N/A'
        print(f"Title: {title}")

        magnet_keywords = ['magnet', 'torrent', 'bt', 'cili', 'zhongzi', 'sousuo', 'search',
                           'dagong', 'dht', 'p2p', 'cilimao', 'btdigg', 'nyaa', 'mikan',
                           'anime', 'share', 'acg', 'btfox', 'sbt', 'cilijun', 'ciliss',
                           'laowang', 'clm', 'cld', 'hezi', 'tiantang', 'cat']

        links = []
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text(strip=True)

            if not href or href.startswith('javascript:') or href.startswith('#'):
                continue
            if href.startswith('/'):
                href = urljoin(resp.url, href)

            parsed = urlparse(href)
            domain = parsed.netloc.lower()

            if not domain or domain == urlparse(resp.url).netloc.lower():
                continue

            is_magnet_site = any(kw in domain for kw in magnet_keywords)
            is_magnet_text = any(kw in text.lower() for kw in magnet_keywords)

            if is_magnet_site or is_magnet_text:
                display = text[:30] if text else domain
                links.append({
                    'url': href,
                    'domain': domain,
                    'text': display,
                    'is_site_match': is_magnet_site,
                })
                if domain not in all_discovered:
                    all_discovered[domain] = {'url': href, 'text': display, 'source': name}

        seen = set()
        for link in links:
            d = link['domain']
            if d in seen:
                continue
            seen.add(d)
            tag = 'DOMAIN' if link['is_site_match'] else 'TEXT'
            print(f"  [{tag}] {link['domain']:35s} | {link['text'][:30]} | {link['url'][:60]}")

    except Exception as e:
        print(f"ERROR: {str(e)[:60]}")

print(f"\n\n{'='*60}")
print(f"TOTAL UNIQUE DOMAINS DISCOVERED: {len(all_discovered)}")
for domain, info in sorted(all_discovered.items()):
    print(f"  {domain:35s} | {info['text'][:25]:25s} | from: {info['source']}")
