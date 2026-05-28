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

            # Wait for any CF/Turnstile challenge to auto-resolve
            self._wait_for_challenge_resolved(page)

            html = page.content()
            if not html:
                raise TierError("empty page content", retryable=True)

            results = extract_results_from_html(html, source=source, base_url=url)
            if not results:
                # SPA may still be rendering; give it a beat and retry once
                time.sleep(2)
                html = page.content()
                results = extract_results_from_html(html, source=source, base_url=url)

            if not results:
                raise TierError("zero results after render", retryable=False, hint="check_selectors")

            return results[:limit]

        finally:
            try:
                browser.close()
            except Exception:
                pass

    def _build_search_url(self, source: dict, query: str) -> str:
        template = source.get("search", {}).get("url") or source.get("search_url")
        if not template:
            raise TierError("source has no search.url template", retryable=False)
        origin = source.get("site", {}).get("origin", "").rstrip("/")
        encoded = urllib.parse.quote_plus(query)
        path = template.replace("{query}", encoded).replace("{query_url}", encoded).replace("{query_raw}", query)
        return path if path.startswith("http") else origin + (path if path.startswith("/") else "/" + path)

    def _wait_for_challenge_resolved(self, page) -> None:
        start = time.time()
        while time.time() - start < MAX_CHALLENGE_WAIT:
            try:
                html_head = page.evaluate("() => document.documentElement.outerHTML.slice(0, 4000)") or ""
            except Exception:
                # navigation in progress
                time.sleep(POLL_INTERVAL)
                continue

            if not any(m in html_head for m in CHALLENGE_MARKERS):
                # Challenge cleared (or never was one)
                return
            time.sleep(POLL_INTERVAL)

        raise TierError(
            "challenge did not resolve within timeout",
            retryable=False,
            hint="escalate_to_tier2_or_userassist",
        )
