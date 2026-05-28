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

log = logging.getLogger(__name__)

try:
    from cloakbrowser import launch as cloak_launch  # type: ignore
    _HAS_CLOAK = True
except ImportError:
    cloak_launch = None
    _HAS_CLOAK = False


# CF / Turnstile detection markers
CHALLENGE_MARKERS = (
    "challenge-platform",
    "cf-browser-verification",
    "Just a moment",
    "Checking your browser",
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
            if not results:
                raise TierError(
                    "zero results after render (challenge may not have resolved)",
                    retryable=False,
                    hint="check_selectors_or_escalate",
                )
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
            challenge_present = any(m in head for m in CHALLENGE_MARKERS)
            if not challenge_present and elapsed > 3:
                # page settled, no challenge, no results — selectors likely wrong, give up
                return []

            time.sleep(POLL_INTERVAL)

        # Final attempt after timeout
        return extract_results_from_html(last_html, source=source, base_url=base_url)

    def _build_search_url(self, source: dict, query: str) -> str:
        import base64
        search = source.get("search") or {}
        template = search.get("request_template") or search.get("url") or source.get("search_url")
        if not template:
            raise TierError("source has no search.request_template", retryable=False)
        origin = source.get("site", {}).get("origin", "").rstrip("/")
        encoded = urllib.parse.quote_plus(query)
        path = template
        for k, v in {
            "{query}": encoded,
            "{query_url}": encoded,
            "{query_raw}": query,
            "{query_b64}": base64.b64encode(query.encode("utf-8")).decode("ascii"),
        }.items():
            path = path.replace(k, v)
        return path if path.startswith("http") else origin + (path if path.startswith("/") else "/" + path)

