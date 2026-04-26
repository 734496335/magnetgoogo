#!/usr/bin/env python3
"""
Navigation Site Crawler — 导航站专用磁力源爬取工具
===================================================
目标：从导航站中顺藤摸瓜找到磁力专区下的磁力站/磁力源。

流程：
  1. 打开导航站，自动识别/点击磁力相关 Tab 或分类
  2. 仅在磁力相关区域/品牌白名单中识别卡片
  3. 自动点击卡片进入详情页
  4. 自动点击详情页的直达/访问/前往按钮
  5. 从跳转页、JS、meta refresh、URL query 中提取真实目标地址
  6. 批量验证真实目标地址是否能搜索到 magnet/hash
  7. 写入 sources.json，按 --country 标记可用国家
"""
import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
SOURCES_FILE = os.path.join(ROOT_DIR, 'sources.json')
REPORT_FILE = os.path.join(ROOT_DIR, 'nav_site_crawler_report.json')

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HASH_RE = re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')

MAGNET_BRANDS = [
    'SkrBT', '黑马磁力', '磁力狗', 'SOBT', '磁力猫', '磁力柠檬', '吴签磁力',
    '老王磁力', 'BT1207', '磁力龟', '无限磁力', 'btfox', 'EZTV', '磁力熊猫',
    'ØMagnet', '0Magnet', 'CiLiGeGe', '种子吧', '磁力天堂', 'BT蚂蚁', 'BT迅雷',
    'TorrentKitty', 'MagnetDL', 'BT4G', 'BTDigg', 'BTSOW', 'Nyaa', 'LimeTorrents',
]
MAGNET_SECTION_KEYWORDS = [
    '磁力', '磁力搜', '磁力搜索', 'BT', 'BT搜索', '种子', '种子搜索', 'torrent',
    'magnet', '片源', '资源下载', '影视下载', '下载专区',
]
MAGNET_CARD_KEYWORDS = [
    '磁力', 'BT', 'bt', '种子', 'torrent', 'magnet', '搜索引擎', '链接搜索',
    '资源搜索', 'torrent search', 'magnet search',
]
EXCLUDE_KEYWORDS = [
    '在线影视', '在线观看', '影视在线', '直播', '音乐', '购物', 'AI', '工具',
    '排行榜', '热搜榜', '短视频', '图片', '写真', '设计', '素材', '小说',
]
BAIT_WORDS = ['Big Buck Bunny', 'Inception', 'One Piece', 'Avengers']
SEARCH_PATHS = [
    '/search/{query}', '/search?q={query}', '/?q={query}', '/?s={query}',
    '/search?keyword={query}', '/search?query={query}', '/s/{query}',
    '/search/{query}/1/', '/list/{query}', '/so/{query}',
]

TRACKING_DOMAINS = [
    'hm.baidu.com', 'baidu.com', 'google-analytics.com', 'googletagmanager.com',
    'cnzz.com', 'umeng.com', '51.la', 'sensorsdata.cn', 'doubleclick.net',
]


NON_SEARCH_DOMAINS = {
    'baidu.com', 'bing.com', 'google.com', 'microsoft.com', 'github.com',
    'zhihu.com', 'weibo.com', 'douyin.com', 'bilibili.com', 'youtube.com',
    'qq.com', '163.com', 'taobao.com', 'jd.com', 'douban.com', 'apple.com',
    't.me', 'discord.com', 'telegram.org', 'archive.org', 'wikipedia.org',
    'twitter.com', 'facebook.com', 'instagram.com', 'reddit.com',
    'netflix.com', 'iqiyi.com', 'youku.com', 'mgtv.com', 'letv.com',
    'pptv.com', 'sohu.com', 'toutiao.com', 'csdn.net', 'jianshu.com',
    'alipay.com', 'weixin.qq.com', 'pay.weixin.qq.com', 'open.weixin.qq.com',
    'jquery.com', 'bootstrapcdn.com', 'cdn.jsdelivr.net', 'cdnjs.cloudflare.com',
    'beian.miit.gov.cn', 'beian.mps.gov.cn',
}


NAV_SITES = [
    {'name': 'BT蚂蚁导航', 'url': 'http://8.210.117.39', 'countries': ['china']},
    {'name': '影猫导航', 'url': 'https://www.ymaoo.cn', 'countries': ['china']},
    {'name': '4a影视导航', 'url': 'https://www.4abyte.com', 'countries': ['china']},
]


def is_tracking_domain(domain):
    domain = (domain or '').lower()
    return any(domain == item or domain.endswith('.' + item) for item in TRACKING_DOMAINS)


def normalize_domain(url):
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return ''


def safe_get_text(node):
    try:
        return node.get_text(' ', strip=True)
    except Exception:
        return ''


def load_sources():
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    existing = {}
    for ruleset in data.get('rulesets', []):
        for rule in ruleset.get('rules', []):
            existing[normalize_domain(rule['site']['origin'])] = rule
    return data, existing


def is_magnet_text(text):
    lower = text.lower()
    return any(k.lower() in lower for k in MAGNET_SECTION_KEYWORDS + MAGNET_CARD_KEYWORDS + MAGNET_BRANDS)


def is_excluded_text(text):
    lower = text.lower()
    return any(k.lower() in lower for k in EXCLUDE_KEYWORDS)


def start_driver(headless=False):
    opts = Options()
    if headless:
        opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1366,900')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(35)
    driver.implicitly_wait(2)
    return driver


def get_dom(driver):
    return BeautifulSoup(driver.page_source, 'lxml')


def snapshot_links(driver, nav_url):
    soup = get_dom(driver)
    base_domain = normalize_domain(nav_url)
    items = OrderedDict()
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        text = safe_get_text(a)
        if not href or href.startswith(('#', 'javascript:', 'mailto:')):
            continue
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = urljoin(nav_url, href)
        elif not href.startswith('http'):
            href = urljoin(nav_url, href)
        domain = normalize_domain(href)
        if not domain or domain == base_domain or is_tracking_domain(domain) or domain in NON_SEARCH_DOMAINS:
            continue
        items[href] = {'url': href, 'domain': domain, 'title': text[:120]}
    return items


def click_magnet_tabs(driver, nav_url=''):
    selectors = 'a, button, li, span, div[role="tab"], [data-tab], [data-key], [data-category]'
    clicked = []
    selected_text = ''
    discovered = OrderedDict()
    elements = driver.find_elements(By.CSS_SELECTOR, selectors)
    log.info(f'  扫描可点击元素: {len(elements)}')
    for el in elements:
        try:
            if not el.is_displayed():
                continue
            text = el.text.strip()
            if not text or len(text) > 50:
                continue
            if not is_magnet_text(text) or is_excluded_text(text):
                continue
            if text in clicked:
                continue
            before_links = snapshot_links(driver, nav_url) if nav_url else OrderedDict()
            log.info(f'  点击磁力相关Tab/分类: {text[:40]}')
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.5)
            try:
                el.click()
            except WebDriverException:
                driver.execute_script("arguments[0].click();", el)
            time.sleep(2.5)
            after_links = snapshot_links(driver, nav_url) if nav_url else OrderedDict()
            for href, item in after_links.items():
                if href not in before_links:
                    item['category'] = text[:80]
                    discovered[href] = item
            clicked.append(text)
            if '磁力搜' in text or text.strip() == '磁力':
                selected_text = text
        except WebDriverException:
            continue
    return clicked, selected_text, list(discovered.values())


def find_active_magnet_container(driver):
    selectors = [
        '.tab-content .active', '.tabs-content .active', '.tab-pane.active', '.layui-show',
        '.swiper-slide-active', '[role="tabpanel"]', '.category-content', '.panel-body'
    ]
    for selector in selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, selector):
                if not el.is_displayed():
                    continue
                text = (el.text or '').strip()
                if not text or len(text) < 30:
                    continue
                if '磁力搜' in text or any(brand in text for brand in MAGNET_BRANDS):
                    return el
            
        except WebDriverException:
            continue
    return None


def infer_brand(text):
    lower = text.lower()
    for brand in MAGNET_BRANDS:
        if brand.lower() in lower:
            return brand
    return ''


def extract_data_url_cards(driver, nav_url):
    soup = get_dom(driver)
    base_domain = normalize_domain(nav_url)
    candidates = OrderedDict()
    for a in soup.select('a[data-url]'):
        href = (a.get('data-url') or '').strip()
        text = safe_get_text(a)
        title = a.get('title', '')
        combined = f'{text} {title}'
        if not href:
            continue
        if href.startswith('//'):
            href = 'https:' + href
        elif not href.startswith('http'):
            href = 'https://' + href.lstrip('/')
        domain = normalize_domain(href)
        if not domain or domain == base_domain or is_tracking_domain(domain) or domain in NON_SEARCH_DOMAINS:
            continue
        if not infer_brand(combined) and not is_magnet_text(combined):
            continue
        candidates[href] = {
            'card_url': a.get('href') or href,
            'card_domain': normalize_domain(a.get('href') or href),
            'title': text[:120] or title[:120] or domain,
            'brand': infer_brand(combined),
            'matched_by': 'data-url',
            'real_url_hint': href,
        }
    return list(candidates.values())


def extract_candidate_cards(driver, nav_url, container_html=None):
    soup = BeautifulSoup(container_html, 'lxml') if container_html else get_dom(driver)
    base_domain = normalize_domain(nav_url)
    candidates = OrderedDict()

    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        text = safe_get_text(a)
        if not href or href.startswith(('#', 'javascript:', 'mailto:')):
            continue
        if not text:
            continue

        parent_text = ''
        p = a.parent
        for _ in range(4):
            if not p:
                break
            parent_text = (parent_text + ' ' + safe_get_text(p))[:600]
            p = p.parent

        combined = f'{text} {parent_text}'
        brand = infer_brand(combined)
        brand_hit = bool(brand)
        keyword_hit = is_magnet_text(combined) and not is_excluded_text(combined)
        if not brand_hit and not keyword_hit:
            continue

        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = urljoin(nav_url, href)
        elif not href.startswith('http'):
            href = urljoin(nav_url, href)

        domain = normalize_domain(href)
        if not domain or domain == base_domain:
            card_key = href
        else:
            card_key = href

        if card_key not in candidates:
            candidates[card_key] = {
                'card_url': href,
                'card_domain': domain,
                'title': text[:120],
                'brand': brand,
                'matched_by': 'brand' if brand_hit else 'keyword',
            }

    # 优先只保留品牌白名单命中的卡片，避免继续抓到无关卡片
    brand_cards = [c for c in candidates.values() if c.get('brand')]
    return brand_cards if brand_cards else list(candidates.values())


def extract_http_anchor_category_candidates(nav_url):
    try:
        resp = requests.get(nav_url, headers=HEADERS, timeout=20, allow_redirects=True)
    except requests.RequestException:
        return []
    if resp.status_code != 200 or len(resp.text) < 200:
        return []
    soup = BeautifulSoup(resp.text, 'lxml')
    candidates = OrderedDict()
    base_domain = normalize_domain(nav_url)
    category_terms = []
    for a in soup.find_all('a', href=True):
        text = safe_get_text(a)
        href = a.get('href', '').strip()
        if href.startswith('#term-') and is_magnet_text(text) and not is_excluded_text(text):
            category_terms.append(href.lstrip('#'))
    for term_id in category_terms:
        section = soup.find(id=term_id)
        if not section:
            continue
        scope = section.parent or section
        for a in scope.find_all('a', href=True):
            href = a.get('href', '').strip()
            text = safe_get_text(a)
            if not href or href.startswith(('#', 'javascript:', 'mailto:')):
                continue
            combined = f'{text} {safe_get_text(a.parent) if a.parent else ""}'
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = urljoin(nav_url, href)
            elif not href.startswith('http'):
                href = urljoin(nav_url, href)
            domain = normalize_domain(href)
            if not domain or domain == base_domain or is_tracking_domain(domain) or domain in NON_SEARCH_DOMAINS:
                continue
            if not infer_brand(combined) and not is_magnet_text(combined):
                continue
            candidates[href] = {
                'url': href,
                'domain': domain,
                'brand': infer_brand(combined),
                'title': text[:120],
                'from_nav': nav_url,
                'via': f'anchor-category:{term_id}',
            }
    return list(candidates.values())


def extract_http_named_candidates(nav_url, names):
    try:
        resp = requests.get(nav_url, headers=HEADERS, timeout=20, allow_redirects=True)
    except requests.RequestException:
        return []
    if resp.status_code != 200 or len(resp.text) < 200:
        return []
    soup = BeautifulSoup(resp.text, 'lxml')
    wanted = [name.strip() for name in names if name.strip()]
    wanted_lower = [name.lower() for name in wanted]
    base_domain = normalize_domain(nav_url)
    candidates = OrderedDict()

    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        text = safe_get_text(a)
        title = a.get('title', '')
        data_url = (a.get('data-url') or '').strip()
        combined = f'{text} {title}'
        lower = combined.lower()
        matched_name = ''
        for idx, name in enumerate(wanted_lower):
            if name and name in lower:
                matched_name = wanted[idx]
                break
        if not matched_name:
            continue

        real_url = data_url or href
        if not real_url or real_url.startswith(('#', 'javascript:', 'mailto:')):
            continue
        if real_url.startswith('//'):
            real_url = 'https:' + real_url
        elif real_url.startswith('/'):
            real_url = urljoin(nav_url, real_url)
        elif not real_url.startswith('http'):
            real_url = urljoin(nav_url, real_url)

        domain = normalize_domain(real_url)
        if not domain or domain == base_domain or is_tracking_domain(domain) or domain in NON_SEARCH_DOMAINS:
            continue

        candidates[matched_name] = {
            'url': real_url,
            'domain': domain,
            'brand': matched_name,
            'title': text[:120] or title[:120] or matched_name,
            'from_nav': nav_url,
            'via': 'named-http',
        }
    return list(candidates.values())


def extract_http_nav_candidates(nav_url):
    try:
        resp = requests.get(nav_url, headers=HEADERS, timeout=20, allow_redirects=True)
    except requests.RequestException:
        return []
    if resp.status_code != 200 or len(resp.text) < 200:
        return []
    soup = BeautifulSoup(resp.text, 'lxml')
    candidates = OrderedDict()
    base_domain = normalize_domain(nav_url)
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        text = safe_get_text(a)
        if not href or href.startswith(('#', 'javascript:', 'mailto:')):
            continue
        combined = f'{text} {safe_get_text(a.parent) if a.parent else ""}'
        if not is_magnet_text(combined) or is_excluded_text(combined):
            continue
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = urljoin(nav_url, href)
        elif not href.startswith('http'):
            href = urljoin(nav_url, href)
        domain = normalize_domain(href)
        if not domain or domain == base_domain or is_tracking_domain(domain) or domain in NON_SEARCH_DOMAINS:
            continue
        candidates[href] = {
            'url': href,
            'domain': domain,
            'brand': infer_brand(combined),
            'title': text[:120],
            'from_nav': nav_url,
            'via': 'http-fallback',
        }
    return list(candidates.values())


def wait_for_external_target(driver, nav_url, previous_url='', seconds=12):
    nav_domain = normalize_domain(nav_url)
    end_at = time.time() + seconds
    last_url = ''
    while time.time() < end_at:
        current_url = driver.current_url
        if current_url != last_url:
            log.info(f'    当前跳转页: {current_url[:120]}')
            last_url = current_url
        direct = resolve_from_url(current_url)
        if direct:
            return direct
        direct = extract_direct_url_from_html(driver.page_source, current_url, nav_url)
        if direct:
            return direct
        current_domain = normalize_domain(current_url)
        if current_domain and current_domain != nav_domain and current_url != previous_url and not is_tracking_domain(current_domain):
            return current_url
        click_jump_button(driver)
        time.sleep(1)
    return None


def click_jump_button(driver):
    words = ['立即跳转', '继续访问', '确认跳转', '跳转', '进入网站', '打开网站', '立即进入', '继续前往', 'go', 'continue']
    for el in driver.find_elements(By.CSS_SELECTOR, "a, button, input[type='button'], input[type='submit'], div[onclick], span[onclick]"):
        try:
            if not el.is_displayed():
                continue
            text = (el.text or el.get_attribute('value') or el.get_attribute('title') or '').strip()
            if not text or len(text) > 40:
                continue
            if not any(word.lower() in text.lower() for word in words):
                continue
            log.info(f'    点击跳转页按钮: {text}')
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.2)
            try:
                el.click()
            except WebDriverException:
                driver.execute_script("arguments[0].click();", el)
            return True
        except WebDriverException:
            continue
    return False


def resolve_from_url(url):
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for key in ['url', 'u', 'target', 'link', 'redirect', 'goto', 'jump', 'to', 'site']:
        if key in qs:
            value = unquote(qs[key][0])
            if value.startswith('http'):
                domain = normalize_domain(value)
                if domain and not is_tracking_domain(domain):
                    return value
    return None


def open_card_and_resolve(driver, card, nav_url):
    from selenium.webdriver.common.by import By

    main = driver.current_window_handle
    card_url = card['card_url']
    direct = card.get('real_url_hint') or resolve_from_url(card_url)
    if direct:
        return direct

    before = set(driver.window_handles)
    try:
        driver.execute_script("window.open(arguments[0], '_blank');", card_url)
        time.sleep(2)
        after = set(driver.window_handles)
        new_tabs = list(after - before)
        if new_tabs:
            driver.switch_to.window(new_tabs[0])
        else:
            driver.switch_to.window(driver.window_handles[-1])
        time.sleep(2)

        current_url = driver.current_url
        direct = resolve_from_url(current_url)
        if direct:
            return direct

        html = driver.page_source
        log.info(f"    详情页: {current_url[:120]}")

        direct_selectors = [
            "a", "button", "input[type='button']", "input[type='submit']",
            "div[onclick]", "span[onclick]"
        ]
        priority_words = ['链接直达', '直达链接', '立即访问', '前往', '访问', '打开网站', '立即进入',
                          '确认跳转', '进入网站', '点击访问', '访问官网', '去看看', '进入', '打开']

        clickable_candidates = []
        for selector in direct_selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in els:
                    if not el.is_displayed():
                        continue
                    text = (el.text or el.get_attribute('value') or el.get_attribute('title') or '').strip()
                    href = el.get_attribute('href') or ''
                    onclick = el.get_attribute('onclick') or ''
                    haystack = f'{text} {href} {onclick}'
                    if len(text) > 60:
                        continue
                    if href:
                        href_domain = normalize_domain(href)
                        if href_domain and is_tracking_domain(href_domain):
                            continue
                    if any(word in haystack for word in priority_words):
                        clickable_candidates.append((el, text or href[:40] or 'onclick'))
            except WebDriverException:
                pass

        clickable_candidates.sort(key=lambda item: 0 if any(word in item[1] for word in ['链接直达', '直达链接', '立即访问', '访问官网', '打开网站']) else 1)
        log.info(f"    直达按钮候选: {[text for _, text in clickable_candidates[:5]]}")

        for el, text in clickable_candidates:
            try:
                log.info(f"    点击详情页直达按钮: {text}")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.5)

                before_click_url = driver.current_url
                before_click_windows = set(driver.window_handles)

                try:
                    el.click()
                except WebDriverException:
                    driver.execute_script("arguments[0].click();", el)

                time.sleep(2)

                after_click_windows = set(driver.window_handles)
                new_after_click = list(after_click_windows - before_click_windows)
                if new_after_click:
                    driver.switch_to.window(new_after_click[0])

                direct = wait_for_external_target(driver, nav_url, before_click_url, seconds=15)
                if direct:
                    return direct

            except WebDriverException:
                continue

        return None
    finally:
        try:
            while len(driver.window_handles) > 1:
                if driver.current_window_handle != main:
                    driver.close()
                driver.switch_to.window(main)
                break
            driver.switch_to.window(main)
        except Exception:
            pass


def extract_direct_url_from_html(html, current_url, nav_url):
    soup = BeautifulSoup(html, 'lxml')
    nav_domain = normalize_domain(nav_url)
    current_domain = normalize_domain(current_url)
    priority_words = ['直达', '访问', '前往', '进入', '打开', '跳转', '确认', 'visit', 'go', 'continue', '立即']
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = safe_get_text(a).lower()
        if any(word.lower() in text for word in priority_words):
            direct = resolve_from_url(href)
            if direct:
                return direct
            if href.startswith('http'):
                domain = normalize_domain(href)
                if domain and domain not in {nav_domain, current_domain} and not is_tracking_domain(domain):
                    return href
            if href.startswith('/'):
                full = urljoin(current_url, href)
                direct = resolve_from_url(full)
                if direct:
                    return direct
    for meta in soup.find_all('meta'):
        content = meta.get('content', '')
        match = re.search(r'url=(https?://[^\s"\']+)', content, re.I)
        if match:
            return match.group(1)
    for script in soup.find_all('script'):
        urls = re.findall(r'https?://[^\s"\'<>\\]+', script.get_text())
        for url in urls:
            domain = normalize_domain(url)
            if domain and domain not in {nav_domain, current_domain} and not is_tracking_domain(domain):
                return url.rstrip("');,")
    for a in soup.find_all('a', href=True):
        href = a['href']
        direct = resolve_from_url(href)
        if direct:
            return direct
        if href.startswith('http'):
            domain = normalize_domain(href)
            if domain and domain not in {nav_domain, current_domain} and not is_tracking_domain(domain):
                return href
    return None


def selenium_verify_source(url):
    driver = start_driver(headless=True)
    try:
        for bait in BAIT_WORDS[:2]:
            q = urllib.parse.quote(bait)
            for path in SEARCH_PATHS[:4]:
                try:
                    driver.get(url.rstrip('/') + path.replace('{query}', q))
                    time.sleep(5)
                except Exception:
                    continue
                magnets = extract_magnets(driver.page_source, url)
                if magnets:
                    return {
                        'magnets': len(magnets),
                        'path': path,
                        'bait': bait,
                        'samples': magnets[:3],
                        'requires_browser': True,
                    }
        return None
    finally:
        driver.quit()


def add_sources(verified, country):
    if not verified:
        return 0
    data, existing = load_sources()
    ruleset = data['rulesets'][0]
    added = 0
    updated = 0

    for item in verified:
        domain = normalize_domain(item['url'])
        if domain in existing:
            rule = existing[domain]
            countries = rule['site'].setdefault('countries', [])
            if country and country not in countries:
                countries.append(country)
                updated += 1
            continue

        rule_id = hashlib.md5(item['url'].encode()).hexdigest()[:12]
        rule = {
            'id': rule_id,
            'site': {
                'name': domain,
                'origin': item['url'].rstrip('/'),
                'countries': [country] if country else [],
                'brand': item.get('brand', ''),
            },
            'capabilities': {'supports_search': True, 'supports_detail': False},
            'search': {
                'request_template': item.get('path', '/search?q={query}'),
                'timeout_ms': 15000,
                'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                'requires_waf_bypass': False,
                'requires_browser': item.get('requires_browser', False),
                'parse_metadata': {
                    'selectors': {
                        'list_item': 'div.item',
                        'title': 'a[href^="magnet:"]',
                        'magnet': 'a[href^="magnet:"]',
                        'size': 'span.size',
                        'date': 'span.date',
                    }
                },
            },
            'quality': {'score': 70, 'tags': ['追新极客']},
            'health': {
                'status': 'green',
                'status_detail': 'ok',
                'last_checked_at': datetime.now(timezone.utc).isoformat(),
                'magnets_found': item.get('magnets', 0),
                'sample_title': item.get('samples', [{}])[0].get('title', '')[:80] if item.get('samples') else '',
            },
        }
        ruleset['rules'].append(rule)
        existing[domain] = rule
        added += 1
        log.info(f"  Added {domain} ({item.get('magnets', 0)} magnets)")

    data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
    data['generated_at'] = datetime.now(timezone.utc).isoformat()
    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"  sources.json: added={added}, updated_countries={updated}")
    return added


def resolve_detail_page(detail_url, nav_url, headless=False):
    driver = start_driver(headless=headless)
    try:
        try:
            driver.get(detail_url)
        except TimeoutException:
            log.info('  详情页加载超时，继续使用已加载DOM')
        time.sleep(3)
        return open_card_and_resolve(driver, {'card_url': detail_url, 'title': detail_url, 'brand': ''}, nav_url)
    finally:
        driver.quit()


def crawl_nav(nav, country, headless):
    url = nav['url'] if isinstance(nav, dict) else nav
    log.info('\n' + '=' * 70)
    log.info(f'NAV: {url}')
    log.info('=' * 70)

    driver = start_driver(headless=headless)
    resolved = OrderedDict()
    try:
        try:
            driver.get(url)
        except TimeoutException:
            log.info('  页面加载超时，继续使用已加载DOM')
        time.sleep(5)

        clicked_tabs, selected_tab, tab_discovered = click_magnet_tabs(driver, url)
        log.info(f'  已点击Tab/分类: {clicked_tabs}')
        if selected_tab:
            log.info(f'  优先使用分类: {selected_tab}')
        time.sleep(3)

        container = find_active_magnet_container(driver)
        container_html = container.get_attribute('outerHTML') if container else None
        if container_html:
            log.info('  已锁定磁力分类容器')
        else:
            log.info('  未锁定到分类容器，回退全页解析')

        cards = extract_candidate_cards(driver, url, container_html=container_html)
        if not cards:
            cards = extract_data_url_cards(driver, url)
        if not cards and tab_discovered:
            log.info(f'  使用Tab增量链接回退: {len(tab_discovered)}')
            cards = [
                {
                    'card_url': item['url'],
                    'card_domain': item['domain'],
                    'title': item['title'],
                    'brand': infer_brand(f"{item['title']} {item.get('category', '')}"),
                    'matched_by': 'tab-diff',
                }
                for item in tab_discovered
            ]
        log.info(f'  识别磁力卡片: {len(cards)}')
        for card in cards:
            log.info(f"    {card.get('brand') or '-':15s} {card['title'][:45]} -> {card['card_domain']}")

        for idx, card in enumerate(cards, 1):
            log.info(f"  [{idx}/{len(cards)}] 穿透: {card['title'][:50]}")
            try:
                real = open_card_and_resolve(driver, card, url)
            except Exception as e:
                log.info(f"    穿透异常，跳过: {str(e)[:80]}")
                continue
            if not real:
                log.info('    未解析到真实URL')
                continue
            domain = normalize_domain(real)
            if not domain:
                continue
            if domain not in resolved:
                resolved[domain] = {
                    'url': real,
                    'domain': domain,
                    'brand': card.get('brand') or card.get('title', ''),
                    'title': card.get('title', ''),
                    'from_nav': url,
                }
                log.info(f'    => {domain}')
            time.sleep(0.5)
    finally:
        driver.quit()

    if not resolved:
        http_candidates = extract_http_anchor_category_candidates(url)
        if http_candidates:
            log.info(f'  使用HTTP锚点分类回退提取: {len(http_candidates)}')
            for item in http_candidates:
                domain = item['domain']
                if domain not in resolved:
                    resolved[domain] = item

    if not resolved:
        http_candidates = extract_http_nav_candidates(url)
        if http_candidates:
            log.info(f'  使用HTTP回退提取: {len(http_candidates)}')
            for item in http_candidates:
                domain = item['domain']
                if domain not in resolved:
                    resolved[domain] = item

    return list(resolved.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='*', help='navigation site urls')
    parser.add_argument('--country', default='korea', help='country tag for verified reachable sources')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--resolve-only', action='store_true', help='only resolve real domains from nav cards')
    parser.add_argument('--verify-browser', action='store_true', help='use selenium fallback verification')
    parser.add_argument('--resolve-detail', help='resolve a single nav detail page url')
    parser.add_argument('--names-file', help='target names file for named extraction')
    args = parser.parse_args()

    if args.resolve_detail:
        real = resolve_detail_page(args.resolve_detail, args.urls[0] if args.urls else 'https://www.ymaoo.cn', headless=args.headless)
        log.info(f'Resolved detail: {real}')
        return

    if args.names_file:
        with open(args.names_file, 'r', encoding='utf-8') as f:
            names = [line.strip() for line in f if line.strip()]
        nav_url = args.urls[0] if args.urls else NAV_SITES[0]['url']
        items = extract_http_named_candidates(nav_url, names)
        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'country': args.country,
                'real_candidates': items,
                'verified': [],
            }, f, indent=2, ensure_ascii=False)
        log.info(f'定向提取: {len(items)}')
        for item in items:
            log.info(f"  {item['brand']:16s} -> {item['domain']}")
        log.info(f'Report saved: {REPORT_FILE}')
        return

    navs = args.urls or [n['url'] for n in NAV_SITES]
    all_real = OrderedDict()

    for url in navs:
        for item in crawl_nav(url, args.country, args.headless):
            all_real[item['domain']] = item

    log.info('\n' + '=' * 70)
    log.info(f'真实URL候选: {len(all_real)}')
    log.info('=' * 70)
    for item in all_real.values():
        log.info(f"  {item['domain']:30s} {item.get('brand','')[:30]}")

    if args.resolve_only:
        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'country': args.country,
                'real_candidates': list(all_real.values()),
                'verified': [],
            }, f, indent=2, ensure_ascii=False)
        log.info(f'Report saved: {REPORT_FILE}')
        return

    verified = []
    browser_queue = []
    for idx, item in enumerate(all_real.values(), 1):
        log.info(f"\n[{idx}/{len(all_real)}] 验证 {item['domain']}")
        result = verify_source(item['url'])
        if result and result.get('magnets', 0) > 0:
            log.info(f"  OK HTTP: {result['magnets']} magnets path={result['path']}")
            verified.append({**item, **result})
        elif result and result.get('has_keyword'):
            log.info('  有磁力关键词，HTTP未提取到')
            browser_queue.append(item)
        else:
            log.info('  跳过')

    if args.verify_browser and browser_queue:
        for item in browser_queue:
            log.info(f"\nBrowser verify {item['domain']}")
            result = selenium_verify_source(item['url'])
            if result and result.get('magnets', 0) > 0:
                log.info(f"  OK Browser: {result['magnets']} magnets")
                verified.append({**item, **result})

    log.info('\n' + '=' * 70)
    log.info(f'验证通过: {len(verified)}')
    for item in verified:
        log.info(f"  + {item['domain']:30s} {item.get('magnets',0):3d} magnets country={args.country}")

    add_sources(verified, args.country)

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'country': args.country,
            'real_candidates': list(all_real.values()),
            'verified': verified,
        }, f, indent=2, ensure_ascii=False)
    log.info(f'Report saved: {REPORT_FILE}')


if __name__ == '__main__':
    main()
