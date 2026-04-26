import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


class MagnetExtractor:
    def __init__(self, source_config):
        self.url = source_config.get('url') or source_config.get('site', {}).get('origin', '')
        
        search_cfg = source_config.get('search', {})
        self.search_path = search_cfg.get('request_template') or source_config.get('search_path', '/search?q={query}')
        self.search_method = search_cfg.get('search_method', 'GET')
        self.search_body = search_cfg.get('search_body', None)
        self.requires_browser = search_cfg.get('requires_browser', False)
        
        self.selectors = search_cfg.get('parse_metadata', {}).get('selectors') or source_config.get('selectors', {})
        
        self.requires_waf_bypass = search_cfg.get('requires_waf_bypass') or source_config.get('requires_waf_bypass', False)
        self.timeout = 15
        self._session = requests.Session()
        self._detail_cache = {}
        self._max_detail_fetches_per_page = int(search_cfg.get('max_detail_fetches_per_page', 6) or 6)

    def build_search_url(self, query):
        base = self.url.rstrip('/')
        path = self.search_path.replace('{query}', query)
        return base + path

    def extract_magnets(self, html, base_url=None):
        if base_url is None:
            base_url = self.url
        soup = BeautifulSoup(html, 'lxml')
        magnets = []
        items = self._extract_items(soup)
        for item in items:
            magnet = self._extract_magnet_from_item(item, soup, base_url)
            if magnet:
                magnets.append(magnet)
        if not magnets:
            magnets = self._extract_hash_urls(soup, base_url)
        return magnets

    def _extract_hash_urls(self, soup, base_url):
        results = []
        seen = set()
        hash_re = re.compile(r'/([0-9A-Fa-f]{40})/')
        for a in soup.find_all('a', href=True):
            m = hash_re.search(a['href'])
            if not m:
                continue
            info_hash = m.group(1).upper()
            if info_hash in seen:
                continue
            seen.add(info_hash)
            title = a.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            magnet_uri = f'magnet:?xt=urn:btih:{info_hash}'
            results.append({
                'title': title,
                'magnet': magnet_uri,
                'size': '',
                'date': '',
                'source': self.url,
            })
        return results

    def _extract_items(self, soup):
        list_sel = self.selectors.get('list_item', 'div.item')
        try:
            items = soup.select(list_sel)
            if items:
                return items
        except:
            pass
        fallback_selectors = [
            'tr.torrent', 'tr.torrent_row', 'div.torrent', 'div.torrent-item',
            'div.search-result', 'div.result', 'div.item', 'li.torrent',
            'table tbody tr', 'div.data-row', 'a.torrent'
        ]
        for sel in fallback_selectors:
            try:
                items = soup.select(sel)
                if len(items) >= 3:
                    return items
            except:
                pass
        return []

    def _extract_magnet_from_item(self, item, soup, base_url):
        magnet_sel = self.selectors.get('magnet', 'a[href^="magnet:"]')
        title_sel = self.selectors.get('title', 'a[href*="/torrent/"]')
        size_sel = self.selectors.get('size', 'span.size')
        date_sel = self.selectors.get('date', 'span.date')
        magnet_link = None
        magnet_anchors = item.select(magnet_sel) if hasattr(item, 'select') else []
        if not magnet_anchors:
            magnet_anchors = soup.select(magnet_sel)
        for a in magnet_anchors:
            href = a.get('href', '')
            if href and 'magnet:' in href:
                magnet_link = href
                break
        if not magnet_link:
            href_patterns = ['/torrent/', '/view/', '/info/', '/detail/', '/dy/', '/movies/']
            anchors = []
            if hasattr(item, 'find_all'):
                anchors = item.find_all('a', href=True)
            if not anchors:
                anchors = soup.find_all('a', href=True)

            fetched = 0
            for a in anchors:
                if fetched >= self._max_detail_fetches_per_page:
                    break
                href = a.get('href', '')
                if not href or not any(p in href for p in href_patterns):
                    continue

                detail_url = urljoin(base_url, href)
                detail_html = self._fetch_detail_page(detail_url)
                fetched += 1
                if not detail_html:
                    continue

                detail_soup = BeautifulSoup(detail_html, 'lxml')
                detail_magnets = detail_soup.select('a[href^="magnet:"]')
                for ma in detail_magnets:
                    mh = ma.get('href', '')
                    if mh and 'magnet:' in mh:
                        magnet_link = mh
                        break
                if magnet_link:
                    break
        if not magnet_link:
            all_magnets = soup.select('a[href^="magnet:"]')
            for a in all_magnets:
                href = a.get('href', '')
                if href and 'magnet:' in href:
                    magnet_link = href
                    break
        title = ''
        title_anchors = item.select(title_sel) if hasattr(item, 'select') else []
        if not title_anchors:
            title_anchors = soup.select(title_sel)
        for a in title_anchors[:1]:
            title = a.get_text(strip=True)
            if title:
                break
        if not title:
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if any(p in href for p in ['/torrent/', '/view/', '/info/', '/detail/']):
                    title = a.get_text(strip=True)
                    if title:
                        break
        size = ''
        size_elems = item.select(size_sel) if hasattr(item, 'select') else []
        if not size_elems:
            size_elems = soup.select(size_sel)
        for s in size_elems[:1]:
            size = s.get_text(strip=True)
            if size:
                break
        date = ''
        date_elems = item.select(date_sel) if hasattr(item, 'select') else []
        if not date_elems:
            date_elems = soup.select(date_sel)
        for d in date_elems[:1]:
            date = d.get_text(strip=True)
            if date:
                break
        if magnet_link:
            return {
                'title': title,
                'magnet': magnet_link,
                'size': size,
                'date': date,
                'source': self.url
            }
        return None

    def _fetch_detail_page(self, url):
        cached = self._detail_cache.get(url)
        if cached is not None:
            return cached
        try:
            resp = self._session.get(url, timeout=self.timeout, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            if resp.status_code == 200:
                self._detail_cache[url] = resp.text
                return resp.text
        except requests.RequestException:
            pass
        if self.requires_browser:
            try:
                from ai_parser.ai_parser import LocalHeuristicParser
                parser = LocalHeuristicParser('')
                html = parser.get_browser_dom(url)
                self._detail_cache[url] = html
                return html
            except Exception:
                pass
        self._detail_cache[url] = None
        return None

    def search(self, query, limit=20):
        url = self.build_search_url(query)
        try:
            if self.search_method == 'POST' and self.search_body:
                body = {}
                for k, v in self.search_body.items():
                    body[k] = v.replace('{query}', query) if isinstance(v, str) else v
                resp = requests.post(url, data=body, timeout=self.timeout, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                }, allow_redirects=True)
            else:
                resp = requests.get(url, timeout=self.timeout, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                })
            if resp.status_code == 200:
                magnets = self.extract_magnets(resp.text)
                if not magnets and self.requires_browser:
                    try:
                        from ai_parser.ai_parser import LocalHeuristicParser
                        parser = LocalHeuristicParser('')
                        html = parser.get_browser_dom(url)
                        if html:
                            magnets = self.extract_magnets(html)
                    except:
                        pass
                return magnets[:limit]
        except Exception as e:
            print(f"Search error for {self.url}: {e}")
        return []
