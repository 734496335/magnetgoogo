import sys
import time
import json
from collections import OrderedDict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, TimeoutException

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--disable-gpu')
opts.add_argument('--no-sandbox')
opts.add_argument('--window-size=1366,900')
driver = webdriver.Chrome(options=opts)
driver.set_page_load_timeout(35)
driver.implicitly_wait(2)

try:
    driver.get('https://www.swnav.cn')
except TimeoutException:
    pass
time.sleep(3)

els = driver.find_elements(By.CSS_SELECTOR, 'a, button, li, span')
clicked = False
for el in els:
    try:
        text = (el.text or '').strip()
        if 'BT磁力' in text or text == '磁力':
            print(f'Clicking: {text}')
            driver.execute_script("arguments[0].click();", el)
            clicked = True
            break
    except WebDriverException:
        continue

if not clicked:
    for el in els:
        try:
            text = (el.text or '').strip()
            if '磁力' in text and len(text) < 10:
                print(f'Clicking fallback: {text}')
                driver.execute_script("arguments[0].click();", el)
                clicked = True
                break
        except WebDriverException:
            continue

time.sleep(4)

from bs4 import BeautifulSoup
soup = BeautifulSoup(driver.page_source, 'lxml')

names = ['磁力熊猫', '凌风云', '磁力大全', '种子吧', '比特大雄', 'bthaha', '博世', '老王磁力', '磁力宅', 'BT天堂', '磁力']

results = OrderedDict()
for a in soup.find_all('a', href=True):
    text = a.get_text(' ', strip=True)
    href = a.get('href', '').strip()
    title = a.get('title', '') or ''
    data_url = a.get('data-url', '') or ''
    combined = f'{text} {title}'
    matched = ''
    for name in names:
        if name.lower() in combined.lower():
            matched = name
            break
    if not matched:
        continue
    real = data_url if data_url else href
    if not real or real.startswith('#'):
        continue
    if not real.startswith('http'):
        real = 'https://' + real.lstrip('/')
    domain = real.split('://', 1)[-1].split('/', 1)[0].lower().removeprefix('www.')
    print(f'  {matched:12s} {text[:60]:60s} -> {real}')
    results[matched] = {'url': real, 'domain': domain, 'brand': matched, 'title': text[:120]}

driver.quit()

with open(r'D:\lpproduct\magnet\nav_site_crawler_report.json', 'w', encoding='utf-8') as f:
    json.dump({
        'generated_at': '2026-04-20',
        'country': 'korea',
        'real_candidates': list(results.values()),
        'verified': [],
    }, f, indent=2, ensure_ascii=False)
print(f'\nTotal: {len(results)}')
