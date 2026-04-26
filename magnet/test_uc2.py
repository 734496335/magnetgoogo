"""Test uc with local chromedriver path."""
import undetected_chromedriver as uc
import selenium.webdriver
from bs4 import BeautifulSoup
import time, os, glob

chrome_paths = [
    r"C:\Users\luhuo\AppData\Local\Programs\Python\Python310\Lib\site-packages\selenium\webdriver\chrome",
]

driver_exe = None
for p in chrome_paths:
    matches = glob.glob(os.path.join(p, '**', 'chromedriver.exe'), recursive=True)
    if matches:
        driver_exe = matches[0]
        break

if not driver_exe:
    import shutil
    driver_exe = shutil.which('chromedriver')
    if not driver_exe:
        d = selenium.webdriver.Chrome()
        driver_exe = None
        d.quit()

print(f"Using chromedriver: {driver_exe}")

SITES = [
    ('btso.cc', 'https://btso.cc/search?q=Ubuntu'),
    ('btdb.to', 'https://btdb.to/search?q=Ubuntu'),
]

options = uc.ChromeOptions()
options.add_argument('--window-size=1920,1080')

try:
    if driver_exe:
        driver = uc.Chrome(options=options, driver_executable_path=driver_exe)
    else:
        driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(30)

    for name, url in SITES:
        print(f"\n{'='*50}")
        print(f"{name}: {url}")
        try:
            driver.get(url)
            time.sleep(12)
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
    driver.quit()
except Exception as e:
    print(f"Init error: {e}")
