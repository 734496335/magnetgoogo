"""Tier 1 — CloakBrowser (anti-fingerprint Chromium).

Replaces:
- Old `cloak_yellow_verify.py` one-shot script
- Web `route.ts` execFile + verify-extension MV3 hack (P3 migration)
- crawler_v2 Scrapling StealthyFetcher (CloakBrowser is more rigorous: C++
  source-level patches vs. Patchright runtime JS patches)

Auto-handles:
- Cloudflare JS challenge (`navigator.webdriver` false at C++ level)
- Cloudflare Turnstile (auto-pass without interaction when running fresh)
- Generic SPA rendering (waits for content + extracts post-render DOM)

humanize=True flag enables bezier-curve mouse + paced typing — needed for
sites with behavior-based bot detection (was the missing piece on 2026-05-16
when we first tried CloakBrowser).
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any

from .base import SearchResult, Tier, TierError, TierKind
from ..parser import extract_results_from_html
from ..cookie_store import CookieStore

log = logging.getLogger(__name__)

_COOKIE_STORE = CookieStore()

try:
    from cloakbrowser import launch as cloak_launch  # type: ignore
    _HAS_CLOAK = True
except ImportError:
    cloak_launch = None
    _HAS_CLOAK = False


# CF challenge detection — split into strong (always in head) and weak (title-only)
# to avoid false positives from common Chinese loading text on regular sites.
CF_STRONG_MARKERS = (
    "challenge-platform",
    "cf-browser-verification",
    "Just a moment",
    "Checking your browser",
    "__cf_chl_",
    "cf-mitigated",
)
CF_WEAK_TITLE_MARKERS = (
    "请稍候",
    "正在进行安全验证",
)
MAX_CHALLENGE_WAIT = 40  # seconds
POLL_INTERVAL = 1.0


class Tier1Cloak(Tier):
    kind = TierKind.CLOAK

    def __init__(self, *, headless: bool = True, humanize: bool = True, timeout: int = 30):
        if not _HAS_CLOAK:
            raise TierError(
                "cloakbrowser package not installed",
                retryable=False,
                hint="pip install cloakbrowser",
            )
        self.headless = headless
        self.humanize = humanize
        self.timeout = timeout

    def search(self, source: dict, query: str, *, limit: int = 24) -> list[SearchResult]:
        url = self._build_search_url(source, query)

        browser = cloak_launch(headless=self.headless, humanize=self.humanize)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)

            # Smart wait: poll for either (a) extractable results, or (b) clean page
            # without challenge markers. Whichever comes first ends the wait.
            results = self._poll_for_results(page, source=source, base_url=url)

            # Harvest cookies on success (for future Tier 0 reuse)
            if results:
                origin = (source.get("site") or {}).get("origin", "")
                if origin:
                    try:
                        cookies = page.context.cookies()
                        if cookies:
                            _COOKIE_STORE.put(origin.rstrip("/"), [dict(c) for c in cookies])
                            log.info("Harvested %d cookies for %s", len(cookies), origin)
                    except Exception as e:
                        log.debug("Cookie harvest failed (non-fatal): %s", e)

            if not results:
                raise TierError(
                    "zero results after render (challenge may not have resolved)",
                    retryable=False,
                    hint="check_selectors_or_escalate",
                )

            # Detail-following: if results have detail_url but no magnet, fetch detail pages
            search_cfg = source.get("search") or {}
            detail_cfg = search_cfg.get("detail") or source.get("detail")
            if detail_cfg and detail_cfg.get("selectors", {}).get("magnet"):
                results = self._follow_details(results, source, detail_cfg, limit)

            return results[:limit]

        finally:
            try:
                browser.close()
            except Exception:
                pass

    def _poll_for_results(self, page, *, source: dict, base_url: str) -> list[SearchResult]:
        """Poll page content every POLL_INTERVAL until results extractable or timeout.

        Stops early if:
        - extract_results_from_html returns >0 results (success)
        - challenge markers gone AND we've polled at least 3s (give SPA time to hydrate)
        """
        start = time.time()
        last_html = ""
        while time.time() - start < MAX_CHALLENGE_WAIT:
            try:
                last_html = page.content() or ""
            except Exception:
                # navigation in progress
                time.sleep(POLL_INTERVAL)
                continue

            results = extract_results_from_html(last_html, source=source, base_url=base_url)
            if results:
                return results

            elapsed = time.time() - start
            head = last_html[:8000]
            challenge_present = (
                any(m in head for m in CF_STRONG_MARKERS)
                or self._title_has_weak_marker(page)
            )
            if not challenge_present and elapsed > 3:
                # page settled, no challenge, no results — selectors likely wrong, give up
                return []

            time.sleep(POLL_INTERVAL)

        # Final attempt after timeout
        return extract_results_from_html(last_html, source=source, base_url=base_url)

    def _title_has_weak_marker(self, page) -> bool:
        """Check if <title> contains weak CF markers (avoids body false positives)."""
        try:
            title = page.title() or ""
        except Exception:
            return False
        return any(m in title for m in CF_WEAK_TITLE_MARKERS)

    def _build_search_url(self, source: dict, query: str) -> str:
        import base64
        search = source.get("search") or {}
        template = search.get("request_template") or search.get("url") or source.get("search_url")
        if not template:
            raise TierError("source has no search.request_template", retryable=False)
        origin = source.get("site", {}).get("origin", "").rstrip("/")
        # Strip query string from origin (e.g. ?ref=eeenav.com) to avoid URL corruption
        origin = origin.split("?")[0].rstrip("/")
        encoded = urllib.parse.quote_plus(query)
        path = template
        for k, v in {
            "{query}": encoded,
            "{query_url}": encoded,
            "{query_raw}": query,
            "{query_b64}": base64.b64encode(query.encode("utf-8")).decode("ascii"),
            "{query_b64url}": base64.urlsafe_b64encode(query.encode("utf-8")).decode("ascii"),
            "{query_hex}": query.encode("utf-8").hex(),
        }.items():
            path = path.replace(k, v)
        return path if path.startswith("http") else origin + (path if path.startswith("/") else "/" + path)

    def _follow_details(
        self, results: list[SearchResult], source: dict, detail_cfg: dict, limit: int
    ) -> list[SearchResult]:
        """Follow detail pages to fill in magnets for results that only have detail_url."""
        from bs4 import BeautifulSoup as _BS
        try:
            from curl_cffi import requests as cc_requests
            has_cc = True
        except ImportError:
            cc_requests = None
            has_cc = False

        try:
            import httpx
        except ImportError:
            httpx = None

        origin = (source.get("site") or {}).get("origin", "").rstrip("/")
        cookie_header = _COOKIE_STORE.to_header(origin)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if cookie_header:
            headers["Cookie"] = cookie_header

        out: list[SearchResult] = []
        followed = 0
        for r in results:
            if r.magnet or not r.detail_url:
                out.append(r)
                continue
            if followed >= limit:
                out.append(r)
                continue
            followed += 1
            try:
                html = None
                if has_cc and cc_requests is not None:
                    try:
                        res = cc_requests.get(r.detail_url, headers=headers, impersonate="chrome124", timeout=10)
                        if res.status_code < 400:
                            html = res.text
                    except Exception:
                        pass
                if not html and httpx is not None:
                    try:
                        with httpx.Client(timeout=10, follow_redirects=True) as client:
                            res = client.get(r.detail_url, headers=headers)
                            if res.status_code < 400:
                                html = res.text
                    except Exception:
                        pass

                if not html:
                    out.append(r)
                    continue

                sel = detail_cfg.get("selectors", {})
                magnet_sel = sel.get("magnet")
                if magnet_sel and _BS is not None:
                    soup = _BS(html, "html.parser")
                    for el in soup.select(magnet_sel):
                        href = el.get("href", "")
                        if href.startswith("magnet:"):
                            r.magnet = href
                            break
                        val = el.get("value", "")
                        if val.startswith("magnet:"):
                            r.magnet = val
                            break
                        data_mag = el.get("data-magnet", "")
                        if data_mag.startswith("magnet:"):
                            r.magnet = data_mag
                            break
                out.append(r)
            except Exception as e:
                log.debug("Cloak detail follow failed for %s: %s", r.detail_url, e)
                out.append(r)
        return out

