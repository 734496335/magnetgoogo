"""Test undetected-chromedriver against FingerprintJS gate sites."""
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import time

SITES = [
    ('btso.cc', 'https://btso.cc/search?q=Ubuntu'),
    ('btdb.to', 'https://btdb.to/search?q=Ubuntu'),
    ('extratorrent.ag', 'https://extratorrent.ag/search?q=Ubuntu'),
    ('btbtt12.com', 'https://btbtt12.com/search?q=Ubuntu'),
    ('limetorrents.fun', 'https://www.limetorrents.fun/search/all/Ubuntu/'),
]

print("Initializing undetected ChromeDriver...")
options = uc.ChromeOptions()
options.add_argument('--window-size=1920,1080')
driver = uc.Chrome(options=options)
driver.set_page_load_timeout(30)

try:
    for name, url in SITES:
        print(f"\n{'='*50}")
        print(f"{name}: {url}")
        try:
            driver.get(url)
            time.sleep(10)
            html = driver.page_source
            soup = BeautifulSoup(html, 'lxml')
            title = soup.title.string[:60] if soup.title else 'N/A'
            magnets = soup.find_all('a', href=lambda h: h and h.startswith('magnet:'))
            text = soup.get_text(strip=True)[:200]
            print(f"Title: {title}")
            print(f"HTML len: {len(html)}")
            print(f"Magnets: {len(magnets)}")
            print(f"Text: {text}")
            if magnets:
                for m in magnets[:3]:
                    print(f"  magnet: {m.get('href', '')[:80]}")
        except Exception as e:
            print(f"ERROR: {e}")
finally:
    driver.quit()
