"""
MagnetExtractorV2 — 继承 V1，把 requests 抓取换成 Scrapling Fetcher (TLS 指纹伪装).

策略：
  1. 主路径：Fetcher.get(impersonate='chrome') — 看起来就是真 Chrome 的 TLS 指纹
  2. 失败时 fallback 到 v1 的 requests 流程（保证不退化）
  3. 浏览器路径：StealthyFetcher 替代 Selenium（反 Cloudflare Turnstile）

返回结构与 v1 一致，可平替使用。
"""
from crawler.extractor import MagnetExtractor

try:
    from scrapling.fetchers import Fetcher, StealthyFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False
    Fetcher = None
    StealthyFetcher = None


class MagnetExtractorV2(MagnetExtractor):
    """Scrapling-powered extractor. Inherits all extraction logic; only network is overridden."""

    IMPERSONATE_PROFILE = 'chrome'  # 'chrome120', 'firefox', etc — try generic first
    FETCHER_RETRIES = 1  # MUST be >=1 (Scrapling 0.4.8 bug: retries=0 → "No active session"); we have our own bait-word loop
    FETCHER_RETRY_DELAY = 1

    def __init__(self, source_config, proxy=None):
        super().__init__(source_config)
        self.proxy = proxy
        # Wire proxy into v1's requests.Session for _fetch_detail_page fallback
        if self.proxy:
            self._session.proxies = {"http": self.proxy, "https": self.proxy}
        # v0.3.10: keep capabilities so search() can route detail_follow sources
        # through the healer's detail_follow_v2 path instead of failing on
        # list-page extraction (which never sees magnets for these sources).
        self._capabilities = source_config.get('capabilities') or {}
        self._source_config = source_config
        self._scrapling_failed = False  # sticky flag: if Fetcher 3x in a row fails, fall back
        # v0.3.9: instance-level URL → html cache. Prevents re-fetching the
        # same search URL when the multi-bait loop probes a 302-redirect-to-
        # homepage site (laowangzo etc.). Per-instance, so a fresh extractor
        # for the next rule starts clean.
        self._html_cache = {}
        # v0.3.10: sticky flag — once we observe that fetching a search URL
        # ended up at the site origin (i.e. the search page 302-redirects
        # to the homepage, signalling "search broken"), short-circuit all
        # subsequent baits to return []. Without this, sites like laowangzo
        # spend 100-300s probing 4-6 baits that each redirect.
        self._search_dead_redirect = False

    def _cache_key(self, url, method, body):
        # body is a dict for POST or None for GET; tuple-ify to make it hashable
        body_key = None
        if isinstance(body, dict):
            body_key = tuple(sorted(body.items()))
        return (method, url, body_key)

    def _is_redirect_to_home(self, requested_url, final_url):
        """True iff the requested URL was non-origin (e.g. /search?...) but
        Scrapling landed us at the bare origin URL. Used to detect dead-search
        redirect loops without paying for additional baits."""
        try:
            from urllib.parse import urlparse
            req = urlparse(requested_url)
            fin = urlparse(final_url)
            # Same host required (otherwise it's a different site, not a redirect)
            if (req.hostname or '').lower() != (fin.hostname or '').lower():
                return False
            req_path = (req.path or '/').rstrip('/')
            fin_path = (fin.path or '/').rstrip('/')
            req_query = req.query or ''
            fin_query = fin.query or ''
            # final must be at root + no query; requested must be non-trivial
            return (fin_path == '' and not fin_query
                    and (req_path != '' or req_query))
        except Exception:
            return False

    def _fetch_html_via_scrapling(self, url, method='GET', body=None):
        """Try fetching with Scrapling's TLS-impersonating Fetcher. Returns html str or None.
        Cached per (url, method, body) tuple within this extractor instance."""
        ck = self._cache_key(url, method, body)
        if ck in self._html_cache:
            return self._html_cache[ck]
        if not SCRAPLING_AVAILABLE or self._scrapling_failed:
            return None
        try:
            common = dict(
                impersonate=self.IMPERSONATE_PROFILE,
                timeout=self.timeout,
                retries=self.FETCHER_RETRIES,
                retry_delay=self.FETCHER_RETRY_DELAY,
            )
            if self.proxy:
                common['proxy'] = self.proxy
            if method == 'POST' and body is not None:
                resp = Fetcher.post(url, data=body, **common)
            else:
                resp = Fetcher.get(url, **common)
            if resp.status == 200:
                # v0.3.10: detect search → home redirect (laowangzo style).
                # If we requested a non-origin path but landed back at origin,
                # this site's search is dead — flag for short-circuit.
                final_url = getattr(resp, 'url', '') or ''
                if final_url and self._is_redirect_to_home(url, final_url):
                    self._search_dead_redirect = True
                # html_content is a TextHandler (str-like); body is bytes
                html = str(resp.html_content) if resp.html_content else resp.body.decode('utf-8', errors='replace')
                self._html_cache[ck] = html
                return html
            return None
        except Exception as e:
            err_msg = str(e).lower()
            # SSRF / redirect-to-localhost errors are per-URL (proxy routing
            # artifact), not a global Scrapling failure — don't set sticky flag
            # so other URLs can still benefit from TLS impersonation.
            _ssrf_hints = ('ssrf', 'loopback', '127.0.0.1', 'localhost', 'private', 'internal ip')
            if not any(h in err_msg for h in _ssrf_hints):
                self._scrapling_failed = True
            print(f"  [v2 Fetcher] failed for {url[:60]}: {str(e)[:80]} — falling back to requests")
            return None

    def _fetch_html_via_browser_v2(self, url):
        """StealthyFetcher: real browser with anti-fingerprint patches (replaces Selenium).
        Cached per URL within this extractor instance."""
        ck = ('stealth', url, None)
        if ck in self._html_cache:
            return self._html_cache[ck]
        if not SCRAPLING_AVAILABLE:
            return None
        try:
            resp = StealthyFetcher.fetch(
                url,
                headless=True,
                network_idle=True,
                timeout=max(self.timeout * 1000, 20000),
                block_images=True,  # speed up
                disable_resources=False,
                **(dict(proxy=self.proxy) if self.proxy else {}),
            )
            if resp.status in (200, 304):
                html = str(resp.html_content) if resp.html_content else resp.body.decode('utf-8', errors='replace')
                self._html_cache[ck] = html
                return html
        except Exception as e:
            print(f"  [v2 StealthyFetcher] failed for {url[:60]}: {str(e)[:80]}")
        return None

    def _fetch_with_fallback(self, url):
        """Try Scrapling Fetcher, fall back to plain requests on hard failure.
        Used inside _search_via_detail_follow where the URL might be behind
        a proxy that triggers Scrapling's SSRF protection (e.g. clb.im via
        Clash → 127.0.0.1 redirect)."""
        html = self._fetch_html_via_scrapling(url)
        if html is not None:
            return html
        try:
            import requests
            r = requests.get(url, timeout=self.timeout, allow_redirects=True, verify=False,
                             proxies={"http": self.proxy, "https": self.proxy} if self.proxy else None,
                             headers={
                                 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                                               'Chrome/124.0.0.0 Safari/537.36',
                                 'Referer': 'https://www.google.com/',
                             })
            if r.status_code in (200, 304):
                return r.text
        except Exception:
            pass
        return None

    def _v1_search_proxied(self, query, limit=20):
        """Re-implement v1's search() using self._session (which carries proxy).
        Called when Fetcher fails and we fall back to requests-based path."""
        import requests as _req
        url = self.build_search_url(query)
        try:
            if self.search_method == 'POST' and self.search_body:
                body = {k: (v.replace('{query}', query) if isinstance(v, str) else v)
                        for k, v in self.search_body.items()}
                resp = self._session.post(url, data=body, timeout=self.timeout, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                }, allow_redirects=True)
            else:
                resp = self._session.get(url, timeout=self.timeout, headers={
                    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                                   'Chrome/91.0.4472.124 Safari/537.36'),
                })
            if resp.status_code == 200:
                magnets = self.extract_magnets(resp.text)
                return magnets[:limit]
        except Exception as e:
            print(f"  [v2 v1-proxied] search failed: {str(e)[:80]}")
        return []

    def _search_via_detail_follow(self, query, limit=5):
        """For detail_follow sources: fetch list page, harvest detail anchors,
        fetch each detail page, regex-scan for magnets. Returns up to `limit`
        magnet dicts. Mirror of HealerV2._try_detail_follow but invoked from
        the search path so verify_rule (extractor.search) handles these sites."""
        import re as _re
        from urllib.parse import urljoin
        from bs4 import BeautifulSoup
        _MAGNET_RE = _re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}[^"\'\s<>]*', _re.I)

        url = self.build_search_url(query)
        list_html = self._fetch_with_fallback(url)
        if not list_html:
            return []

        # Harvest detail URLs (try selectors first, then path heuristic)
        soup = BeautifulSoup(list_html, 'lxml')
        detail_sel = (self.selectors or {}).get('detail_link', '')
        detail_urls = []
        if detail_sel:
            try:
                for el in soup.select(detail_sel)[:limit * 2]:
                    href = el.get('href', '')
                    if href:
                        detail_urls.append(urljoin(url, href))
            except Exception:
                pass
        if not detail_urls:
            # Fallback path-segment heuristic
            hints = ('/movie/', '/detail/', '/torrent/', '/view/', '/doc/',
                     '/info/', '/post/', '/topic/', '/show/')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if any(p in href for p in hints):
                    detail_urls.append(urljoin(url, href))
                    if len(detail_urls) >= limit * 2:
                        break

        # Dedupe + same-host filter
        from urllib.parse import urlparse as _up
        base_host = _up(self.url).hostname or ''
        seen, deduped = set(), []
        for du in detail_urls:
            if du in seen:
                continue
            h = _up(du).hostname or ''
            if h and base_host and h.split('.')[-2:] != base_host.split('.')[-2:]:
                continue
            seen.add(du)
            deduped.append(du)
            if len(deduped) >= limit:
                break

        if not deduped:
            return []

        # Fetch each detail page + regex magnets
        results = []
        for du in deduped:
            body = self._fetch_with_fallback(du)
            if not body:
                continue
            hits = _MAGNET_RE.findall(body)
            if not hits:
                continue
            title = ''
            try:
                d_soup = BeautifulSoup(body, 'lxml')
                t_el = d_soup.find('h1') or d_soup.find('title')
                if t_el:
                    title = t_el.get_text(strip=True)[:120]
            except Exception:
                pass
            results.append({
                'title': title,
                'magnet': hits[0],
                'size': '',
                'date': '',
                'source': self.url,
                'detail_url': du,
            })
            if len(results) >= limit:
                break
        return results

    def search(self, query, limit=20, fast=False):
        """Override v1's search: try Fetcher first, fall back to requests, then browser.
        When fast=True, skip browser fallback and detail_follow (for batch probe)."""
        # v0.3.10: if a previous bait already proved this site's search is
        # broken (302 → home), skip the entire pipeline. This is the dominant
        # speedup for laowangzo-class sites (4-6 baits × 25s each → 25s total).
        if self._search_dead_redirect:
            return []
        url = self.build_search_url(query)
        body = None
        if self.search_method == 'POST' and self.search_body:
            body = {k: (v.replace('{query}', query) if isinstance(v, str) else v)
                    for k, v in self.search_body.items()}

        # 1) Try Scrapling Fetcher (TLS impersonate)
        html = self._fetch_html_via_scrapling(url, method=self.search_method, body=body)
        if html:
            magnets = self.extract_magnets(html)
            if magnets:
                return magnets[:limit]

        # 2) Fall back to requests-based path (proxy-aware via self._session)
        if html is None:
            try:
                magnets = self._v1_search_proxied(query, limit=limit)
                if magnets:
                    return magnets
            except Exception as e:
                print(f"  [v2 fallback] requests failed: {str(e)[:80]}")

        if fast:
            return []

        # 3) Browser fallback (StealthyFetcher beats Selenium against Cloudflare)
        if self.requires_browser or not html:
            browser_html = self._fetch_html_via_browser_v2(url)
            if browser_html:
                magnets = self.extract_magnets(browser_html)
                if magnets:
                    return magnets[:limit]

        # 4) v0.3.10: detail_follow last-ditch. Only kicks in when paths 1-3
        # all returned 0 magnets, so healthy list_page sources are unaffected.
        # Capped at 3 detail URLs to keep cost bounded for sources that have
        # no detail-page magnets either (~15-30s instead of ~50s).
        return self._search_via_detail_follow(query, limit=3)

    def _fetch_detail_page(self, url):
        """Override detail-page fetch to also benefit from Fetcher's TLS impersonation."""
        cached = self._detail_cache.get(url)
        if cached is not None:
            return cached
        html = self._fetch_html_via_scrapling(url)
        if html:
            self._detail_cache[url] = html
            return html
        # Fall back to parent's requests + Selenium logic
        return super()._fetch_detail_page(url)
