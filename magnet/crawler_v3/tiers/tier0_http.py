"""Tier 0 — Plain HTTP via curl_cffi with Chrome TLS/JA3 fingerprint.

Why curl_cffi:
- Cloudflare's bot-mode rules increasingly check TLS handshake (JA3/JA4) before
  any JS challenge. Node fetch / requests use OpenSSL defaults that don't match
  real Chrome → instant 403 on some sources.
- curl_cffi impersonates real Chrome's BoringSSL handshake, header order, HTTP/2
  pseudo-header order, etc.

Fallback chain:
1. Try curl_cffi with `impersonate="chrome124"`
2. If module not available, fall back to httpx (logs a warning).
"""
from __future__ import annotations

import html as html_lib
import logging
import re
import urllib.parse
from typing import Any

from .base import SearchResult, Tier, TierError, TierKind
from ..parser import extract_results_from_html
from ..cookie_store import CookieStore

log = logging.getLogger(__name__)

_COOKIE_STORE = CookieStore()

try:
    from curl_cffi import requests as cc_requests  # type: ignore
    _HAS_CURL_CFFI = True
except ImportError:
    cc_requests = None
    _HAS_CURL_CFFI = False
    log.warning("curl_cffi not installed → Tier 0 falls back to httpx (no TLS fingerprint match)")

try:
    import httpx  # type: ignore
except ImportError:
    httpx = None


DEFAULT_TIMEOUT = 15
DEFAULT_IMPERSONATE = "chrome124"
_VALID_BTIH_RE = re.compile(
    r"(?:urn:)?btih:(?:[0-9A-Fa-f]{40}|[A-Z2-7]{32})(?=$|[^A-Za-z0-9])",
    re.I,
)


def has_valid_btih_magnet(value: str) -> bool:
    return bool(value.startswith("magnet:?") and _VALID_BTIH_RE.search(value))


class Tier0Http(Tier):
    kind = TierKind.HTTP

    def __init__(self, *, timeout: int = DEFAULT_TIMEOUT, impersonate: str = DEFAULT_IMPERSONATE):
        self.timeout = timeout
        self.impersonate = impersonate

    def search(self, source: dict, query: str, *, limit: int = 24) -> list[SearchResult]:
        url = self._build_search_url(source, query)
        headers = self._build_headers(source)

        # Inject persisted cookies (from prior Tier 1 / verify-interactive passes)
        origin = (source.get("site") or {}).get("origin", "")
        if origin:
            cookie_header = _COOKIE_STORE.to_header(origin.rstrip("/"))
            if cookie_header:
                headers["Cookie"] = cookie_header

        html = self._fetch(url, headers=headers)
        if not html:
            raise TierError("empty response", retryable=True)

        if _looks_like_anti_bot(html):
            raise TierError(
                "anti-bot challenge detected in HTML",
                retryable=False,
                hint="escalate_to_tier1",
            )

        results = extract_results_from_html(html, source=source, base_url=url)
        if not results:
            raise TierError("zero results parsed", retryable=False, hint="check_selectors_or_escalate")

        # Detail-following: if results have detail_url but no magnet, fetch detail pages
        search_cfg = source.get("search") or {}
        detail_cfg = search_cfg.get("detail") or source.get("detail")
        if detail_cfg and detail_cfg.get("selectors", {}).get("magnet"):
            results = self._follow_details(results, source, headers, detail_cfg, limit)

        usable = [result for result in results if has_valid_btih_magnet(result.magnet)]
        if not usable:
            raise TierError("detail/search results yielded zero magnets", retryable=False, hint="check_detail_selector")
        return usable[:limit]

    # ── helpers ──

    def _build_search_url(self, source: dict, query: str) -> str:
        search = source.get("search") or {}
        template = search.get("request_template") or search.get("url") or source.get("search_url")
        if not template:
            raise TierError("source has no search.request_template", retryable=False)

        origin = source.get("site", {}).get("origin", "").rstrip("/")
        # Strip query string from origin (e.g. ?ref=eeenav.com) to avoid URL corruption
        origin = origin.split("?")[0].rstrip("/")
        encoded = urllib.parse.quote_plus(query)
        # Support {query}, {query_b64}, {query_url}
        import base64
        replacements = {
            "{query}": encoded,
            "{query_url}": encoded,
            "{query_b64}": base64.b64encode(query.encode("utf-8")).decode("ascii"),
            "{query_b64url}": base64.urlsafe_b64encode(query.encode("utf-8")).decode("ascii"),
            "{query_hex}": query.encode("utf-8").hex(),
            "{query_raw}": query,
        }
        path = template
        for k, v in replacements.items():
            path = path.replace(k, v)
        if path.startswith("http"):
            return path
        return origin + (path if path.startswith("/") else "/" + path)

    def _build_headers(self, source: dict) -> dict[str, str]:
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        search = source.get("search") or {}
        referer = search.get("referer") or (search.get("parse_metadata") or {}).get("referer")
        if referer:
            headers["Referer"] = referer
        return headers

    def _follow_details(
        self, results: list[SearchResult], source: dict, headers: dict, detail_cfg: dict, limit: int
    ) -> list[SearchResult]:
        """Follow detail pages to fill in magnets for results that only have detail_url."""
        from bs4 import BeautifulSoup as _BS

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
                detail_html = self._fetch(r.detail_url, headers=headers)
                if not detail_html:
                    out.append(r)
                    continue
                sel = detail_cfg.get("selectors", {})
                magnet_sel = sel.get("magnet")
                if _BS is not None:
                    soup = _BS(detail_html, "html.parser")
                    selectors = [
                        magnet_sel,
                        "a[href^='magnet:']",
                        "input[value^='magnet:']",
                        "[data-magnet^='magnet:']",
                    ]
                    seen_selectors = set()
                    for selector in selectors:
                        if not selector or selector in seen_selectors:
                            continue
                        seen_selectors.add(selector)
                        for el in soup.select(selector):
                            for attribute in ("href", "value", "data-magnet", "data-url"):
                                candidate = html_lib.unescape(str(el.get(attribute, "")))
                                if candidate.startswith("magnet:?"):
                                    r.magnet = candidate
                                    break
                            if r.magnet:
                                break
                        if r.magnet:
                            break
                if not r.magnet:
                    decoded_html = html_lib.unescape(detail_html)
                    match = re.search(
                        r"magnet:\?[^\s\"'<>]*?xt=urn:btih:(?:[0-9A-Fa-f]{40}|[A-Z2-7]{32})[^\s\"'<>]*",
                        decoded_html,
                        re.I,
                    )
                    if match:
                        r.magnet = match.group(0)
                if r.magnet:
                    out.append(r)
            except Exception as e:
                log.debug("Detail follow failed for %s: %s", r.detail_url, e)
                out.append(r)
        return out

    def _fetch(self, url: str, *, headers: dict[str, str]) -> str | None:
        if _HAS_CURL_CFFI:
            try:
                r = cc_requests.get(url, headers=headers, impersonate=self.impersonate, timeout=self.timeout)
                if r.status_code >= 400:
                    raise TierError(f"HTTP {r.status_code}", retryable=(r.status_code in {429, 503}))
                return r.text
            except Exception as e:
                if isinstance(e, TierError):
                    raise
                raise TierError(f"curl_cffi fetch failed: {e}", retryable=True)

        if httpx is None:
            raise TierError("neither curl_cffi nor httpx available", retryable=False)

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                r = client.get(url, headers=headers)
                if r.status_code >= 400:
                    raise TierError(f"HTTP {r.status_code}", retryable=(r.status_code in {429, 503}))
                return r.text
        except Exception as e:
            if isinstance(e, TierError):
                raise
            raise TierError(f"httpx fetch failed: {e}", retryable=True)


def _looks_like_anti_bot(html: str) -> bool:
    """Heuristic: detect CF / Turnstile / custom captcha challenge HTML."""
    if not html or len(html) < 200:
        return False
    markers = (
        "challenge-platform",
        "cf-browser-verification",
        "Just a moment",
        "Checking your browser",
        "/recaptcha/v4/challenge",
        "请稍候",
        "正在进行安全验证",
    )
    lowered = html[:8000]  # only check head, captchas usually inject early
    return any(m in lowered for m in markers)
