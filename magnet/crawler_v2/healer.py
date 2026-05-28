"""
HealerV2 — 继承 V1 Healer，仅替换两处网络调用：
  1. 主 HTTP 请求 requests.get → Scrapling Fetcher (TLS 指纹伪装)
  2. 浏览器降级 Selenium → StealthyFetcher (反 Cloudflare Turnstile)

诊断逻辑（WAF/parking 检测、bait 轮询、选择器修复、LLM 兜底）完全复用 v1。
"""
import re
import time
import copy
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from crawler.healer import Healer
from crawler.extractor import MagnetExtractor
from crawler_v2.extractor import MagnetExtractorV2
from ai_parser.ai_parser import LocalHeuristicParser
from discovery.search_form_probe import probe_search_url

# Capture the full magnet URI (including &dn=, &tr=, etc.) — not just the hash.
_MAGNET_URI_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}[^"\'\s<>]*', re.I)

try:
    from scrapling.fetchers import Fetcher, StealthyFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False


class _FakeResp:
    """Adapter: makes Scrapling response look like a requests.Response for _detect_waf."""
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class HealerV2(Healer):
    """Scrapling-powered healer. Same return shape as v1."""

    IMPERSONATE_PROFILE = 'chrome'
    FETCHER_RETRIES = 1  # MUST be >=1 (Scrapling 0.4.8 bug: retries=0 → "No active session"); 1 << default 3
    FETCHER_RETRY_DELAY = 1

    def __init__(self, *args, proxy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.proxy = proxy
        # v0.3.10: sticky flag — once a fetched URL ends up redirecting to
        # the bare site origin (search broken, redirects to homepage), short-
        # circuit subsequent test-bait probes inside heal_and_retry so we
        # don't pay 4-6 × 25s on a known-dead site (laowangzo class).
        self._search_dead_redirect = False
        # v0.3.9: Session-level URL → response cache.
        # Without this, detail_follow + multi-bait + heal_and_retry's multiple
        # fallback paths fetch the same URL 30-40 times for sites that 302
        # redirect search→homepage (e.g. laowangzo). Each fetch is 2-3s via
        # Scrapling, so a single source can take 100-300s. With cache, ≤ 6
        # unique URLs per source = ~15-20s.
        # Key: (kind, url) tuple. Value: (status_code, html_text) tuple.
        # `kind` is 'scrapling' or 'stealth' — separate because the same URL
        # may need different fetchers (e.g. WAF-protected detail page).
        self._fetch_cache = {}

    def _cache_get(self, kind, url):
        return self._fetch_cache.get((kind, url))

    def _cache_set(self, kind, url, value):
        # Bound cache: most heal_and_retry sessions see < 20 URLs, but cap to
        # 100 to guard against pathological loops.
        if len(self._fetch_cache) >= 100:
            return  # silently drop — caller will refetch but won't OOM
        self._fetch_cache[(kind, url)] = value

    def reset_cache(self):
        """Clear fetch cache + sticky flags. Call between unrelated source verifications."""
        self._fetch_cache.clear()
        self._search_dead_redirect = False

    def _is_redirect_to_home(self, requested_url, final_url):
        """True iff Scrapling's request to a non-origin URL ended up at the
        bare origin URL (no path, no query). Signals dead-search redirect."""
        try:
            from urllib.parse import urlparse
            req = urlparse(requested_url)
            fin = urlparse(final_url)
            if (req.hostname or '').lower() != (fin.hostname or '').lower():
                return False
            req_path = (req.path or '/').rstrip('/')
            fin_path = (fin.path or '/').rstrip('/')
            req_query = req.query or ''
            fin_query = fin.query or ''
            return (fin_path == '' and not fin_query
                    and (req_path != '' or req_query))
        except Exception:
            return False

    def _probe_search_path(self, origin_url, proxy=None):
        """Try to discover the correct search path by probing the homepage.
        Returns a request_template string (e.g. '/s/{query}') or None."""
        try:
            pattern = probe_search_url(origin_url, proxy=proxy)
            if pattern and pattern.magnets_seen >= 1:
                return pattern.request_template
        except Exception as e:
            print(f"  [v2 search_probe] failed: {str(e)[:80]}")
        return None

    def _fetch_via_scrapling(self, url):
        """Returns (status_code, html_text) or None on hard failure.
        Cached within a single HealerV2 instance."""
        cached = self._cache_get('scrapling', url)
        if cached is not None:
            return cached
        if not SCRAPLING_AVAILABLE:
            return None
        try:
            resp = Fetcher.get(
                url,
                impersonate=self.IMPERSONATE_PROFILE,
                timeout=self.timeout,
                retries=self.FETCHER_RETRIES,
                retry_delay=self.FETCHER_RETRY_DELAY,
                **(dict(proxy=self.proxy) if self.proxy else {}),
            )
            # v0.3.10: detect search→home redirect to enable early-exit later
            try:
                final_url = getattr(resp, 'url', '') or ''
                if final_url and self._is_redirect_to_home(url, final_url):
                    self._search_dead_redirect = True
            except Exception:
                pass
            html = str(resp.html_content) if resp.html_content else resp.body.decode('utf-8', errors='replace')
            result = (resp.status, html)
            self._cache_set('scrapling', url, result)
            return result
        except Exception as e:
            print(f"  [v2 Fetcher] {url[:60]}: {str(e)[:80]}")
            return None

    def _fetch_via_stealth_browser(self, url):
        """StealthyFetcher: replaces Selenium for WAF-protected sites.
        Cached within a single HealerV2 instance."""
        cached = self._cache_get('stealth', url)
        if cached is not None:
            return cached
        if not SCRAPLING_AVAILABLE:
            return None
        try:
            resp = StealthyFetcher.fetch(
                url,
                headless=True,
                network_idle=True,
                timeout=max(self.timeout * 1000, 20000),
                block_images=True,
                **(dict(proxy=self.proxy) if self.proxy else {}),
            )
            if resp.status in (200, 304):
                html = str(resp.html_content) if resp.html_content else resp.body.decode('utf-8', errors='replace')
                self._cache_set('stealth', url, html)
                return html
        except Exception as e:
            print(f"  [v2 StealthyFetcher] {url[:60]}: {str(e)[:80]}")
        return None

    # ── detail_follow capability ──────────────────────────────────────
    # When a list page yields list_item rows but no magnets (yts.rs /
    # cilitiantang.club style sources where the magnet lives on the detail
    # page, not the listing), follow the first N detail links and regex-scan
    # each one for magnet URIs. Zero-config: works whether or not the source
    # has explicit detail_link selectors.
    _DETAIL_PATH_HINTS = ('/movie/', '/detail/', '/torrent/', '/view/',
                          '/doc/', '/info/', '/post/', '/topic/', '/show/')

    def _collect_detail_urls(self, html, source_config, base_url, max_urls=5):
        """Best-effort: harvest candidate detail-page URLs from a list page.

        Tries three strategies in priority order:
          A. list_item + detail_link selectors (when both configured)
          B. detail_link selector applied directly to the document
          C. heuristic: anchors whose href contains '/movie/', '/torrent/', etc.
        """
        selectors = (source_config.get('search', {}).get('parse_metadata', {}).get('selectors')
                     or source_config.get('selectors', {}))
        list_sel = selectors.get('list_item', '')
        detail_sel = selectors.get('detail_link', '')

        soup = BeautifulSoup(html, 'lxml')
        urls = []

        if list_sel and detail_sel:
            for item in soup.select(list_sel)[:max_urls * 2]:
                el = item.select_one(detail_sel)
                if el and el.get('href'):
                    urls.append(urljoin(base_url, el['href']))
        elif detail_sel:
            for el in soup.select(detail_sel)[:max_urls * 2]:
                if el.get('href'):
                    urls.append(urljoin(base_url, el['href']))
        else:
            for a in soup.find_all('a', href=True):
                href = a['href']
                if any(p in href for p in self._DETAIL_PATH_HINTS):
                    urls.append(urljoin(base_url, href))
                    if len(urls) >= max_urls * 2:
                        break

        # Dedupe + cap, keep only same-origin or close-to-origin links
        from urllib.parse import urlparse
        base_host = urlparse(base_url).hostname or ''
        seen, unique = set(), []
        for u in urls:
            if u in seen:
                continue
            h = urlparse(u).hostname or ''
            # cross-origin detail links sometimes legit (knaben.org → knaben.xyz),
            # but skip generic platforms (youtube/twitter/...)
            if h and base_host and (h != base_host
                                    and base_host.split('.')[-2:] != h.split('.')[-2:]):
                # different second-level domain — skip unless brand-aligned
                continue
            seen.add(u)
            unique.append(u)
            if len(unique) >= max_urls:
                break
        return unique

    def _try_detail_follow(self, list_html, source_config, base_url, max_follow=5,
                           bait_used=''):
        """Follow detail pages, regex-scan for magnets. Returns list of magnet dicts."""
        detail_urls = self._collect_detail_urls(list_html, source_config, base_url,
                                                max_urls=max_follow)
        if not detail_urls:
            return []

        print(f"  [v2 detail_follow] {len(detail_urls)} detail page(s) to inspect")
        magnets = []
        for du in detail_urls:
            fetched = self._fetch_via_scrapling(du)
            if not fetched:
                # detail pages are often static + cacheable, but if Fetcher
                # gave up, try Stealthy once (some pages need JS)
                stealth_html = self._fetch_via_stealth_browser(du)
                if not stealth_html:
                    continue
                status, body = 200, stealth_html
            else:
                status, body = fetched
                if status != 200 or not body:
                    continue
            hits = _MAGNET_URI_RE.findall(body)
            # v0.3.10: HTTP fetch returned 200 but no magnets → likely a
            # JS-rendered detail page (bt4g, some Chinese sites inject the
            # magnet via JavaScript at runtime). Upgrade to Stealthy once.
            if not hits and status == 200:
                stealth_html = self._fetch_via_stealth_browser(du)
                if stealth_html:
                    body = stealth_html
                    hits = _MAGNET_URI_RE.findall(body)
            if not hits:
                continue
            # Try to get a title for the first magnet from <title> or <h1>
            title = ''
            try:
                dsoup = BeautifulSoup(body, 'lxml')
                t_el = dsoup.find('h1') or dsoup.find('title')
                if t_el:
                    title = t_el.get_text(strip=True)[:120]
            except Exception:
                pass
            magnets.append({
                'title': title,
                'magnet': hits[0],
                'detail_url': du,
            })
            if len(magnets) >= max_follow:
                break
        return magnets

    def heal_and_retry(self, source_config, query=None):
        """Reimplement v1 with Scrapling. Same return contract.

        Each call is treated as one independent session: the fetch cache is
        reset on entry so cross-rule fetches don't share results (which would
        produce false positives if e.g. two sources sit behind a shared CDN).
        Within one call, however, identical URLs are deduplicated to avoid
        the 40+ duplicate fetches we observed on 302-redirect-loop sites.
        """
        self.reset_cache()
        url = source_config.get('url') or source_config.get('site', {}).get('origin')
        site_name = source_config.get('site', {}).get('name', 'Unknown')

        if not url:
            return {'status': 'error', 'error': 'missing origin url'}

        search_cfg = source_config.get('search', {})
        search_path = search_cfg.get('request_template') or source_config.get('search_path', '/search?q={query}')
        selectors = search_cfg.get('parse_metadata', {}).get('selectors') or source_config.get('selectors', {})

        category = self._get_category(url)
        baits = self.BAIT_REGISTRY.get(category, self.BAIT_REGISTRY['DEFAULT'])
        test_queries = [query] if query else baits

        html = None
        last_test_query = test_queries[0]
        last_status_code = None

        for test_query in test_queries:
            # v0.3.10: short-circuit if a previous fetch already proved this
            # site's search redirects to home. Saves 4-6 × 25s per dead site.
            if self._search_dead_redirect and test_query != test_queries[0]:
                print(f"  [v2] search→home redirect detected, skipping remaining baits")
                break
            test_url = url.rstrip('/') + search_path.replace('{query}', test_query)

            # --- v2 change: Fetcher first, requests fallback ---
            fetched = self._fetch_via_scrapling(test_url)
            if fetched is None:
                # Fetcher hard-failed (network/SSL) — try plain requests
                try:
                    resp = requests.get(test_url, timeout=self.timeout, headers=self.headers,
                                         proxies={"http": self.proxy, "https": self.proxy} if self.proxy else None)
                    fetched = (resp.status_code, resp.text)
                except requests.exceptions.Timeout:
                    return {'status': 'unreachable', 'url': url, 'error': 'Timeout (Network/GFW)'}
                except requests.exceptions.ConnectionError:
                    return {'status': 'unreachable', 'url': url, 'error': 'DNS/Connection Failure'}
                except Exception as e:
                    return {'status': 'error', 'url': url, 'error': f'fetch failed: {e}'}

            status_code, body_text = fetched
            last_status_code = status_code
            last_test_query = test_query
            fake_resp = _FakeResp(status_code, body_text)

            if status_code == 404:
                # v0.3.13: Instead of giving up on 404, try to discover the
                # correct search endpoint via form/anchor/common-guess probing.
                # Many sites change their search URL over time (e.g. /search?q=
                # → /s/ or /?keyword=) but the healer used to bail immediately.
                print(f"  [v2] 404 on {test_url[:80]}, probing for new search path...")
                new_path = self._probe_search_path(url, proxy=self.proxy)
                if new_path:
                    print(f"  [v2] discovered new search path: {new_path}")
                    # Inject the new request_template and re-fetch
                    healed_config = copy.deepcopy(source_config)
                    healed_config.setdefault('search', {})['request_template'] = new_path
                    new_url = url.rstrip('/') + new_path.replace('{query}', test_query)
                    fetched2 = self._fetch_via_scrapling(new_url)
                    if fetched2 is None:
                        try:
                            resp2 = requests.get(new_url, timeout=self.timeout, headers=self.headers,
                                                 proxies={"http": self.proxy, "https": self.proxy} if self.proxy else None)
                            fetched2 = (resp2.status_code, resp2.text)
                        except Exception:
                            fetched2 = None
                    if fetched2 and fetched2[0] == 200:
                        sc2, body2 = fetched2
                        extractor = MagnetExtractorV2(healed_config, proxy=self.proxy)
                        magnets = extractor.extract_magnets(body2, base_url=url)
                        if magnets:
                            return {
                                'status': 'healed', 'url': url,
                                'original_selectors': selectors,
                                'healed_selectors': selectors,
                                'healed_request_template': new_path,
                                'magnets_found': len(magnets),
                                'sample': magnets[0],
                                'bait_used': test_query,
                                'method': 'search_path_probe',
                            }
                return {'status': '404', 'url': url, 'error': 'Page Not Found (404)', 'status_code': 404}

            if self._detect_waf(fake_resp):
                # v2 advantage: try StealthyFetcher to break through WAF
                print(f"  [v2] WAF detected (HTTP {status_code}), trying StealthyFetcher...")
                stealth_html = self._fetch_via_stealth_browser(test_url)
                if stealth_html:
                    extractor = MagnetExtractorV2(source_config, proxy=self.proxy)
                    magnets = extractor.extract_magnets(stealth_html, base_url=url)
                    if magnets:
                        return {
                            'status': 'ok', 'url': url,
                            'magnets_found': len(magnets),
                            'sample': magnets[0],
                            'selectors': selectors,
                            'bait_used': test_query,
                            'method': 'stealth_browser',
                        }
                    html = stealth_html  # may still parse via heuristic
                    continue
                return {
                    'status': 'waf', 'url': url,
                    'error': f'WAF blocked (HTTP {status_code})',
                    'status_code': status_code,
                }

            if status_code >= 500:
                html = body_text
                continue

            if status_code == 200:
                html = body_text

                if self._detect_parking(html):
                    self.discover_new_domain(site_name)
                    return {'status': 'expired', 'url': url, 'error': 'Domain expired/parking/for sale'}

                extractor = MagnetExtractorV2(source_config, proxy=self.proxy)
                magnets = extractor.extract_magnets(html, base_url=url)

                if magnets:
                    return {
                        'status': 'ok', 'url': url,
                        'magnets_found': len(magnets),
                        'sample': magnets[0],
                        'selectors': selectors,
                        'bait_used': test_query,
                        'method': 'http_v2',
                    }

            time.sleep(0.5)

        if not html:
            return {
                'status': 'unreachable', 'url': url,
                'error': f'All queries failed (last HTTP {last_status_code})'
            }

        # --- Heuristic re-parse (selector healing) — wrapped: parser may emit invalid CSS ---
        try:
            local_parser = LocalHeuristicParser(url)
            local_parser._soup = BeautifulSoup(html, 'lxml')

            if local_parser._is_parking_page():
                self.discover_new_domain(site_name)
                return {'status': 'expired', 'url': url, 'error': 'Domain expired/parking'}

            new_rules = local_parser.parse(html)
            new_selectors = new_rules.get('selectors', {})

            if new_selectors.get('list_item'):
                healed_config = self._inject_selectors(source_config, new_selectors)
                healed_extractor = MagnetExtractorV2(healed_config, proxy=self.proxy)
                magnets = healed_extractor.extract_magnets(html, base_url=url)
                if magnets:
                    return {
                        'status': 'healed', 'url': url,
                        'original_selectors': selectors,
                        'healed_selectors': new_selectors,
                        'magnets_found': len(magnets),
                        'sample': magnets[0],
                        'bait_used': last_test_query,
                        'method': 'http_heuristic_v2',
                    }
        except Exception as e:
            print(f"  [v2] heuristic parser raised: {str(e)[:120]} — continuing to browser fallback")
            local_parser = LocalHeuristicParser(url)  # fresh instance for browser path

        # --- v2 change: StealthyFetcher instead of Selenium for browser fallback ---
        # v0.3.10: skip the (expensive) browser fallback when we already know
        # the search URL just redirects to the homepage — the browser will
        # see the same homepage HTML and waste 20-40s spinning up Chromium.
        if self._search_dead_redirect:
            print(f"  [v2] skipping StealthyFetcher (search→home redirect already detected)")
            browser_html = None
        else:
            print(f"  [v2] HTTP parsing gap for {url}, attempting StealthyFetcher fallback...")
            browser_html = self._fetch_via_stealth_browser(
                url.rstrip('/') + search_path.replace('{query}', last_test_query)
            )

        if browser_html:
            extractor = MagnetExtractorV2(source_config, proxy=self.proxy)
            magnets = extractor.extract_magnets(browser_html, base_url=url)

            if magnets:
                return {
                    'status': 'ok', 'url': url,
                    'magnets_found': len(magnets),
                    'sample': magnets[0],
                    'selectors': selectors,
                    'bait_used': last_test_query,
                    'method': 'stealth_browser',
                }

            local_parser._soup = BeautifulSoup(browser_html, 'lxml')
            new_rules = local_parser.parse(browser_html)
            new_selectors = new_rules.get('selectors', {})

            if new_selectors.get('list_item'):
                healed_config = self._inject_selectors(source_config, new_selectors)
                healed_extractor = MagnetExtractorV2(healed_config, proxy=self.proxy)
                magnets = healed_extractor.extract_magnets(browser_html, base_url=url)
                if magnets:
                    return {
                        'status': 'healed', 'url': url,
                        'original_selectors': selectors,
                        'healed_selectors': new_selectors,
                        'magnets_found': len(magnets),
                        'sample': magnets[0],
                        'bait_used': last_test_query,
                        'method': 'stealth_browser_heuristic',
                    }

        # --- detail_follow last-ditch: many sources (yts.rs / cilitiantang /
        # cilishenqi / yhdm33) put magnets ONLY on the detail page, not the
        # listing. We harvest detail URLs from whichever HTML we already have
        # (browser_html preferred — better cross-WAF) and regex-scan them. ---
        # v0.3.10: skip detail_follow when search redirects to homepage —
        # the "list" HTML is the homepage, and any /movie/ /torrent/ anchors
        # we find are likely unrelated nav links, wasting 5 × 20s = 100s.
        if self._search_dead_redirect:
            print(f"  [v2] skipping detail_follow (search→home redirect — list_html is just the homepage)")
            detail_magnets = []
        else:
            candidate_list_html = browser_html or html
            if candidate_list_html:
                detail_magnets = self._try_detail_follow(
                    candidate_list_html, source_config, url,
                    max_follow=5, bait_used=last_test_query,
                )
            else:
                detail_magnets = []
            if detail_magnets:
                return {
                    'status': 'ok', 'url': url,
                    'magnets_found': len(detail_magnets),
                    'sample': detail_magnets[0],
                    'selectors': selectors,
                    'bait_used': last_test_query,
                    'method': 'detail_follow_v2',
                }

        return {
            'status': 'parsing_failed', 'url': url,
            'error': 'page accessible but parsing failed (Fetcher + StealthyFetcher + detail_follow)',
            'selectors_tried': selectors,
        }
