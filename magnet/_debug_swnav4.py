import sys, time, json
from collections import OrderedDict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, TimeoutException
from bs4 import BeautifulSoup

opts = Options()
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

html_before = driver.page_source
len_before = len(html_before)
links_before = len(BeautifulSoup(html_before, 'lxml').find_all('a', href=True))

for el in driver.find_elements(By.CSS_SELECTOR, 'a, li, span'):
    try:
        text = (el.text or '').strip()
        if text == 'BT磁力':
            print(f'Clicking: [{text}]')
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", el)
            break
    except WebDriverException:
        continue

for wait in range(1, 8):
    time.sleep(1)
    html_after = driver.page_source
    links_after = len(BeautifulSoup(html_after, 'lxml').find_all('a', href=True))
    print(f'  wait={wait}s links={links_after} html_len={len(html_after)} diff={len(html_after)-len_before}')

soup = BeautifulSoup(driver.page_source, 'lxml')
names = ['磁力熊猫', '凌风云', '磁力大全', '种子吧', '比特大雄', 'bthaha', '博世', '老王磁力', '磁力宅', 'BT天堂', '磁力', 'cilimao', '0mag', '种子']

for a in soup.find_all('a', href=True):
    text = a.get_text(' ', strip=True)
    href = a.get('href', '').strip()
    title = a.get('title', '') or ''
    data_url = a.get('data-url', '') or ''
    combined = f'{text} {title}'.lower()
    for name in names:
        if name.lower() in combined:
            real = data_url if data_url else href
            if not real or real.startswith('#'):
                continue
            if not real.startswith('http'):
                real = 'https://' + real.lstrip('/')
            print(f'  FOUND [{name}] text={text[:50]} -> {real}')
            break

driver.quit()
