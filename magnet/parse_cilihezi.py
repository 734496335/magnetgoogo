import sys, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from bs4 import BeautifulSoup
from urllib.parse import urlparse

resp = requests.get('https://cilihezi.com/', timeout=20, headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
soup = BeautifulSoup(resp.text, 'lxml')

links = {}
for a in soup.find_all('a', href=True):
    href = a['href'].strip()
    text = a.get_text(strip=True)
    if not href or href.startswith('#') or href.startswith('javascript:') or href.startswith('/'):
        continue
    parsed = urlparse(href)
    domain = parsed.netloc.lower()
    if domain and '.' in domain:
        if domain not in links:
            links[domain] = {'url': parsed.scheme + '://' + parsed.netloc, 'text': text[:40]}

print(f'Total external domains: {len(links)}')
print()
for d in sorted(links.keys()):
    info = links[d]
    t = info['text']
    print(f'  {d:35s} | {t}')
