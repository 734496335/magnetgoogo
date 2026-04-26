from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup


_URL_RE = re.compile(r"https?://[^\s<>'\"\\)\\]]+")
_JS_LOC_RE = re.compile(r"(?:location\\.href|window\\.location)\\s*=\\s*['\"]([^'\"]+)['\"]", re.I)
_META_REFRESH_RE = re.compile(r"url=([^;]+)", re.I)


@dataclass(frozen=True)
class RealUrlCandidate:
    url: str
    reason: str


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    return url


def _try_decode_base64_url(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = unquote(s)
    s = s.strip()
    # padding
    if len(s) % 4:
        s = s + "=" * (4 - len(s) % 4)
    try:
        decoded = base64.b64decode(s).decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""
    if decoded.startswith("http://") or decoded.startswith("https://"):
        return decoded
    return ""


def _extract_from_redirect_params(href: str) -> str:
    try:
        parsed = urlparse(href)
    except Exception:
        return ""
    qs = parse_qs(parsed.query)
    for key in ("url", "target", "link", "redirect", "goto", "jump", "dst", "to"):
        if key not in qs:
            continue
        val = qs[key][0]
        val = unquote(val)
        if val.startswith(("http://", "https://")):
            return val
        decoded = _try_decode_base64_url(val)
        if decoded:
            return decoded
    # fallback: key=value in raw href
    m = re.search(r"(?:url|target|link|redirect|goto|jump|to)=([^&]+)", href, re.I)
    if m:
        raw = m.group(1)
        raw = unquote(raw)
        if raw.startswith(("http://", "https://")):
            return raw
        decoded = _try_decode_base64_url(raw)
        if decoded:
            return decoded
    return ""


def extract_real_external_urls(
    html: str,
    page_url: str,
    nav_origin: Optional[str] = None,
) -> List[RealUrlCandidate]:
    """
    Extract external target URLs from a navigation site's detail/interstitial page.

    Priority roughly follows docs/project-nebula/SOURCE-DISCOVERY-AND-VERIFICATION-STRATEGY.md.
    """
    page_url = _normalize_url(page_url)
    if nav_origin:
        nav_origin = _normalize_url(nav_origin)
    base_dom = urlparse(nav_origin or page_url).netloc.lower()

    soup = BeautifulSoup(html or "", "lxml")
    out: List[RealUrlCandidate] = []
    seen = set()

    def push(u: str, reason: str) -> None:
        u = _normalize_url(u)
        if not u.startswith(("http://", "https://")):
            return
        dom = urlparse(u).netloc.lower()
        if not dom or dom == base_dom:
            return
        key = u.split("#", 1)[0]
        if key in seen:
            return
        seen.add(key)
        out.append(RealUrlCandidate(url=key, reason=reason))

    # 1) direct external links
    for a in soup.find_all("a", href=True):
        href = _normalize_url(a.get("href", ""))
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        if href.startswith(("http://", "https://")):
            push(href, "direct_external_link")

    # 2) go/redirect/jump style + url params
    for a in soup.find_all("a", href=True):
        href = _normalize_url(a.get("href", ""))
        if not href:
            continue
        if any(k in href.lower() for k in ("go", "redirect", "jump", "out", "link")) or "url=" in href.lower():
            real = _extract_from_redirect_params(href)
            if real:
                push(real, "redirect_param_url")

    # 3) data-url / data-href
    for tag in soup.find_all(attrs={"data-url": True}):
        push(str(tag.get("data-url")), "data_url")
    for tag in soup.find_all(attrs={"data-href": True}):
        push(str(tag.get("data-href")), "data_href")

    # 4) meta refresh
    for meta in soup.find_all("meta"):
        if (meta.get("http-equiv") or "").lower() != "refresh":
            continue
        content = meta.get("content") or ""
        m = _META_REFRESH_RE.search(content)
        if not m:
            continue
        u = unquote(m.group(1).strip().strip("'\""))
        u = urljoin(page_url, u)
        push(u, "meta_refresh")

    # 5) JS location
    for script in soup.find_all("script"):
        s = script.string or ""
        m = _JS_LOC_RE.search(s)
        if not m:
            continue
        u = _normalize_url(m.group(1))
        u = urljoin(page_url, u)
        push(u, "js_location")

    # 6) text URLs in body
    text = soup.get_text(" ", strip=True)
    for m in _URL_RE.finditer(text):
        push(m.group(0), "text_url")

    return out


def best_real_url(cands: Iterable[RealUrlCandidate]) -> Optional[RealUrlCandidate]:
    for c in cands:
        return c
    return None

