"""Browser-based navigation hub parser - extract real search site links from JS-rendered pages."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_parser.ai_parser import LocalHeuristicParser
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re, json

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

NAV_SITES = [
    ('bashi5.com', 'https://bashi5.com'),
    ('cilihezi.com', 'https://cilihezi.com'),
    ('cilimao.biz', 'https://cilimao.biz'),
    ('cilihezi.top', 'https://www.cilihezi.top'),
    ('cilitiantang.vip', 'https://www.cilitiantang.vip'),
    ('cldq.cc', 'https://cldq.cc'),
    ('ezhentang.com', 'https://www.ezhentang.com'),
    ('cilishenqi.me', 'https://cilishenqi.me'),
    ('cilihezi.com/link', 'https://cilihezi.com/link.html'),
    ('cilsousuoyinqng.com.cn', 'https://cilsousuoyinqng.com.cn'),
    ('wuqianaa.xyz', 'https://wuqianaa.xyz'),
    ('12580.org', 'https://12580.org'),
]

parser = LocalHeuristicParser('')
all_discovered = {}

for name, url in NAV_SITES:
    print(f"\n{'='*60}")
    print(f"NAV: {name}")
    html = parser.get_browser_dom(url)
    if not html:
        print("  FAILED - no HTML")
        continue

    soup = BeautifulSoup(html, 'lxml')
    title = soup.title.string[:50] if soup.title else 'N/A'
    print(f"  Title: {title}")
    print(f"  HTML: {len(html)}")

    current_origin = urlparse(url if '://' in url else 'https://' + url).netloc.lower()

    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        text = a.get_text(strip=True)

        if not href or href.startswith('javascript:') or href.startswith('#') or href.startswith('mailto:'):
            continue

        if href.startswith('/'):
            href = urljoin('https://' + current_origin, href)

        parsed = urlparse(href)
        domain = parsed.netloc.lower()

        if not domain or domain == current_origin:
            continue

        display = text[:40] if text else ''
        if domain not in all_discovered:
            all_discovered[domain] = {
                'url': href,
                'text': display,
                'source': name,
                'scheme': parsed.scheme,
            }

    seen = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if not href or href.startswith('javascript:') or href.startswith('#'):
            continue
        if href.startswith('/'):
            continue
        parsed = urlparse(href)
        domain = parsed.netloc.lower()
        if domain and domain != current_origin and domain not in seen:
            seen.add(domain)
            display = a.get_text(strip=True)[:30]
            print(f"  {domain:35s} | {display}")

    time.sleep(1)

print(f"\n\n{'='*60}")
print(f"ALL UNIQUE EXTERNAL DOMAINS: {len(all_discovered)}")

MAGNET_KW = ['magnet', 'torrent', 'bt', 'cili', 'zhongzi', 'sousuo', 'search',
             'dht', 'p2p', 'cilimao', 'btdigg', 'nyaa', 'mikan', 'anime',
             'share', 'acg', 'btfox', 'sbt', 'cilijun', 'ciliss', 'laowang',
             'clm', 'cld', 'hezi', 'tiantang', 'cat', 'btdb', 'btsow',
             'limetorrent', 'kickass', 'pirate', 'rarbg', 'eztv', 'yts',
             'torrentdownload', 'solidtorrent', 'idope', 'zooqle',
             'mag', 'btcat', 'souzhongzi', 'zhongziso', 'cilibili',
             'dmhy', 'tosho', 'anidex', 'cilibra', 'magbot']

magnet_sites = {}
other_sites = {}
for domain, info in sorted(all_discovered.items()):
    is_magnet = any(kw in domain for kw in MAGNET_KW)
    is_magnet = is_magnet or any(kw in info['text'].lower() for kw in MAGNET_KW)
    if is_magnet:
        magnet_sites[domain] = info
    else:
        other_sites[domain] = info

print(f"\nMAGNET-RELATED ({len(magnet_sites)}):")
for domain, info in sorted(magnet_sites.items()):
    print(f"  {info['scheme']}://{domain:35s} | {info['text'][:25]:25s} | from: {info['source']}")

print(f"\nOTHER ({len(other_sites)}):")
for domain, info in sorted(other_sites.items()):
    print(f"  {info['scheme']}://{domain:35s} | {info['text'][:25]:25s} | from: {info['source']}")

with open('nav_extracted.json', 'w', encoding='utf-8') as f:
    json.dump({'magnet': magnet_sites, 'other': other_sites}, f, indent=2, ensure_ascii=False)
print(f"\nSaved to nav_extracted.json")
