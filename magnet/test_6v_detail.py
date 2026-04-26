"""Test 6v520 movie detail page with browser."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from ai_parser.ai_parser import LocalHeuristicParser
from bs4 import BeautifulSoup

parser = LocalHeuristicParser('')

movie_urls = [
    'https://www.6v520.com/dy/2026-03-29/49243.html',
    'https://www.6v520.com/dy/2023-01-03/41032.html',
]

for url in movie_urls:
    print(f"\nURL: {url}")
    html = parser.get_browser_dom(url)
    if not html:
        print("  FAILED")
        continue
    soup = BeautifulSoup(html, 'lxml')
    magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
    print(f"  HTML: {len(html)}  Magnets: {len(magnets)}")
    for m in magnets[:3]:
        href = m.get('href', '')
        print(f"  magnet: {href[:100]}")
