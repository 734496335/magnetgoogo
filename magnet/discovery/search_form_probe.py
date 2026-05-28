"""Search-URL pattern discovery for new candidate domains.

When `brand_rediscovery` finds a new host (e.g. `clb.im`), we still don't
know its search endpoint. This module figures it out by trying three
strategies, then validates each candidate by issuing an actual search and
checking for magnet hashes:

  A. **form_action** — parse the homepage, look for `<form>` containing
     a text input named `q` / `keyword` / `s` / `search` / `wd`,
     extract `form.action` + the input name, render `?<name>={query}`.
  B. **anchor_pattern** — scan all `<a href>` on the homepage for hrefs
     containing `/search` or `?q=` / `?s=` / `?kw=`. Generalise the URL by
     replacing the existing keyword (if any) with `{query}`.
  C. **common_guess** — try the seven endpoints most BT/magnet sites use:
     `/search?q={query}`, `/search/{query}`, `/?s={query}`, `/?q={query}`,
     `/s/{query}`, `/?keyword={query}`, `/search-{query}.html`.

Each candidate is validated by issuing the rendered URL with a bait
keyword and counting magnet URIs on the response (regex). Result with
≥ 1 magnet wins. If multiple win, prefer A > B > C (more semantic).

Public API
----------
- SearchPattern dataclass: {request_template, method, magnets_seen, sample_url, source_url}
- probe_search_url(host_or_url, baits=...) -> Optional[SearchPattern]

Returns `None` when nothing works — caller should fall back to a manual
investigation (the candidate is probably JS-rendered SPA or behind a
WAF; reach for `crawler_v2.ai.synthesize_selectors_for_url`).
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional, List, Iterable
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse, quote

MAGNET_HASH_RE = re.compile(r"magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}", re.I)

# Default bait keywords; order is tried for each candidate until magnets seen.
DEFAULT_BAITS = ("Avengers", "复仇者联盟", "one piece", "1080p")

# Common HTTP form input names for search boxes (case-insensitive).
SEARCH_INPUT_NAMES = {"q", "s", "wd", "search", "keyword", "kw", "key", "name", "word"}

COMMON_GUESSES = (
    "/search?q={query}",
    "/?s={query}",
    "/?q={query}",
    "/search/{query}",
    "/s/{query}",
    "/?keyword={query}",
    "/search-{query}.html",
    "/search-{query}-1.html",
)


@dataclass
class SearchPattern:
    request_template: str        # e.g. "/search?q={query}" — relative path with {query} placeholder
    method: str                  # "form_action" | "anchor_pattern" | "common_guess"
    magnets_seen: int = 0        # magnet hashes on the validation response
    detail_links_seen: int = 0   # detail-page links on response (when 0 magnets, signals detail_follow type)
    parse_strategy: str = "list_page"  # "list_page" | "detail_follow" — how to harvest magnets from this URL
    sample_url: str = ""         # full URL we successfully fetched (for proof)
    source_url: str = ""         # the homepage / discovery URL we started from
    bait_used: str = ""
    # Up to 6 detail-page URLs actually seen on the validation response.
    # Onboarder uses these to derive a precise detail_link selector.
    detail_link_samples: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "request_template": self.request_template,
            "method": self.method,
            "magnets_seen": self.magnets_seen,
            "detail_links_seen": self.detail_links_seen,
            "parse_strategy": self.parse_strategy,
            "sample_url": self.sample_url,
            "source_url": self.source_url,
            "bait_used": self.bait_used,
            "detail_link_samples": self.detail_link_samples[:6],
        }


# Path fragments that strongly suggest a detail page (mirrors crawler_v2.healer)
_DETAIL_PATH_HINTS = ("/movie/", "/detail/", "/torrent/", "/view/", "/doc/",
                      "/info/", "/post/", "/topic/", "/show/", "/dy/",
                      "/film/", "/item/")


def _collect_detail_links(html: str, base_url: str) -> List[str]:
    """Return list of absolute detail-page URLs found on the page (deduped,
    same-host)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).hostname or ""
    found = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not any(p in href for p in _DETAIL_PATH_HINTS):
            continue
        absu = urljoin(base_url, href)
        h = urlparse(absu).hostname or ""
        if h and base_host and h.split(".")[-2:] != base_host.split(".")[-2:]:
            continue  # cross-domain, skip
        if absu in seen:
            continue
        seen.add(absu)
        found.append(absu)
    return found


def derive_detail_selector(sample_urls: List[str]) -> str:
    """Given sample detail URLs, return a sources.json `detail_link` CSS
    selector. We extract the path's first segment (e.g. /movie/...) and
    return `a[href*="/<segment>/"]`. Falls back to a permissive
    `a[href*="/detail/"]` if nothing dominant emerges.
    """
    from collections import Counter
    segments = []
    for u in sample_urls:
        path = urlparse(u).path
        parts = [p for p in path.split("/") if p]
        if parts:
            segments.append(parts[0])
    if not segments:
        return 'a[href*="/detail/"]'
    most_common, count = Counter(segments).most_common(1)[0]
    # Require dominance: ≥ 50% of samples
    if count / len(sample_urls) < 0.5:
        return 'a[href*="/detail/"]'
    return f'a[href*="/{most_common}/"]'


# ── Helpers ───────────────────────────────────────────────────────────

def _normalise_host_to_url(host_or_url: str) -> str:
    if host_or_url.startswith(("http://", "https://")):
        return host_or_url
    return f"https://{host_or_url.lstrip('/')}"


def _fetch(url: str, proxy: Optional[str] = None, timeout: int = 12) -> Optional[str]:
    """HTTP GET → str | None.

    Order: requests first (cheap, lenient redirect handling), then Scrapling
    Fetcher as fallback (TLS impersonation, breaks WAF). Scrapling's
    curl-impersonate backend has SSRF protection that rejects redirects to
    127.0.0.1 — fine for healthy public sites, but some Chinese magnet sites
    (e.g. clb.im) redirect through proxy-internal addresses, so we want
    requests to try first.
    """
    try:
        import requests
        r = requests.get(
            url, timeout=timeout, allow_redirects=True, verify=False,
            proxies={"http": proxy, "https": proxy} if proxy else None,
            headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/124.0.0.0 Safari/537.36"),
                "Accept": ("text/html,application/xhtml+xml,application/xml;"
                           "q=0.9,*/*;q=0.8"),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        if r.status_code in (200, 304) and r.text:
            return r.text
    except Exception:
        pass

    # Silence Scrapling's verbose retry logs — we don't care if it fails
    import logging
    logging.getLogger("scrapling").setLevel(logging.CRITICAL)
    try:
        from scrapling.fetchers import Fetcher
        page = Fetcher.get(url, timeout=timeout, proxy=proxy)
        status = getattr(page, "status", 0)
        if status in (200, 304):
            return page.html_content if hasattr(page, "html_content") else str(page)
    except Exception:
        pass
    return None


def _to_relative_template(absolute_url: str, base_origin: str) -> str:
    """Convert an absolute search URL into a path-relative template
    (caller's `request_template` is appended to `site.origin`)."""
    parsed = urlparse(absolute_url)
    if parsed.netloc and parsed.netloc != urlparse(base_origin).netloc:
        # Cross-domain — keep absolute. Most callers handle either.
        return absolute_url
    path_query = parsed.path or "/"
    if parsed.query:
        path_query += "?" + parsed.query
    return path_query


# ── Strategy A: form action ──────────────────────────────────────────

def _extract_form_pattern(html: str, base_url: str) -> Optional[str]:
    """Return an absolute search URL with {query} placeholder, or None."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    for form in soup.find_all("form"):
        # find the search-like text input
        target_input = None
        for inp in form.find_all("input"):
            name = (inp.get("name") or "").lower()
            inp_type = (inp.get("type") or "text").lower()
            if name in SEARCH_INPUT_NAMES and inp_type in ("text", "search", ""):
                target_input = name
                break
        if not target_input:
            continue
        action = (form.get("action") or "").strip()
        method = (form.get("method") or "get").lower()
        if method != "get":
            continue  # POST search is uncommon for static sites; skip
        action_url = urljoin(base_url, action) if action else base_url
        # Inject {query} placeholder via the input name
        parsed = urlparse(action_url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs[target_input] = ["{query}"]
        # Reconstruct
        new_query = urlencode(qs, doseq=True, safe="{}")
        rebuilt = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/",
                              parsed.params, new_query, parsed.fragment))
        return rebuilt
    return None


# ── Strategy B: anchor scanning ──────────────────────────────────────

_KEYWORD_PARAM_RE = re.compile(r"[?&](q|s|wd|keyword|kw|key|name|word)=([^&#]+)", re.I)
_SEARCH_PATH_RE = re.compile(r"/(search|s)(/[^?#]*)?(\?|$)", re.I)


def _extract_anchor_pattern(html: str, base_url: str) -> Optional[str]:
    """Find a search-like anchor href and convert it to a {query} template."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        abs_url = urljoin(base_url, href)

        # Pattern B1: ?q=... / ?s=... / ?keyword=...
        m = _KEYWORD_PARAM_RE.search(abs_url)
        if m:
            # Replace the value with {query}
            return _KEYWORD_PARAM_RE.sub(
                lambda mm: f"{abs_url[mm.start()]}{mm.group(1)}={{query}}", abs_url, count=1
            )

        # Pattern B2: /search/<keyword> or /s/<keyword>
        m2 = _SEARCH_PATH_RE.search(abs_url)
        if m2 and m2.group(2):  # has a trailing path component to replace
            # Heuristic: only treat as pattern if path looks like /search/something-not-too-long
            tail = m2.group(2).strip("/")
            if 0 < len(tail) <= 60 and "/" not in tail:
                # Replace just the keyword segment with {query}
                before = abs_url[:m2.start()]
                return f"{before}/{m2.group(1).lower()}/{{query}}"
    return None


# ── Validation ───────────────────────────────────────────────────────

def _validate_pattern(pattern_url: str, baits: Iterable[str],
                      proxy: Optional[str] = None,
                      min_detail_links: int = 3) -> tuple:
    """Render {query}, fetch, then check for either:
      (a) ≥ 1 magnet hash on the response → list_page strategy
      (b) ≥ min_detail_links detail-page anchors → detail_follow strategy

    Returns (magnets, detail_links, strategy, full_url, bait, det_samples).
    All zero/empty when no bait works. Strategy is 'list_page'|'detail_follow'|''.
    Tries each bait; first one that produces a positive signal wins.
    """
    for bait in baits:
        full_url = pattern_url.replace("{query}", quote(bait))
        body = _fetch(full_url, proxy=proxy)
        if not body:
            continue
        magnets = len(set(MAGNET_HASH_RE.findall(body)))
        if magnets >= 1:
            return (magnets, 0, "list_page", full_url, bait, [])
        det_samples = _collect_detail_links(body, full_url)
        if len(det_samples) >= min_detail_links:
            return (0, len(det_samples), "detail_follow", full_url, bait, det_samples[:6])
        time.sleep(0.5)
    return (0, 0, "", "", "", [])


# ── Public entry ─────────────────────────────────────────────────────

def probe_search_url(host_or_url: str,
                     baits: Iterable[str] = DEFAULT_BAITS,
                     proxy: Optional[str] = None,
                     extra_guesses: Iterable[str] = ()) -> Optional[SearchPattern]:
    """Discover the search URL pattern for `host_or_url`.

    Returns a `SearchPattern` whose `magnets_seen >= 1` (validation passed),
    or `None` if nothing worked.
    """
    base = _normalise_host_to_url(host_or_url)
    home_html = _fetch(base, proxy=proxy)
    if not home_html:
        return None

    candidates = []  # list of (priority_score, method, absolute_pattern_url)

    # A. form action
    a_pat = _extract_form_pattern(home_html, base)
    if a_pat and "{query}" in a_pat:
        candidates.append((3, "form_action", a_pat))

    # B. anchor scanning
    b_pat = _extract_anchor_pattern(home_html, base)
    if b_pat and "{query}" in b_pat:
        candidates.append((2, "anchor_pattern", b_pat))

    # C. common guesses (always tried)
    for g in list(COMMON_GUESSES) + list(extra_guesses):
        candidates.append((1, "common_guess", base.rstrip("/") + g))

    # Dedupe by absolute URL (preserve highest-priority method)
    seen, deduped = {}, []
    for prio, method, abs_url in sorted(candidates, key=lambda x: -x[0]):
        if abs_url in seen:
            continue
        seen[abs_url] = True
        deduped.append((prio, method, abs_url))

    # Validate each (in priority order) — stop at first positive signal
    for prio, method, abs_url in deduped:
        magnets, det_links, strategy, full_url, bait, det_samples = _validate_pattern(
            abs_url, baits, proxy=proxy)
        if strategy:
            return SearchPattern(
                request_template=_to_relative_template(abs_url, base),
                method=method,
                magnets_seen=magnets,
                detail_links_seen=det_links,
                parse_strategy=strategy,
                sample_url=full_url,
                source_url=base,
                bait_used=bait,
                detail_link_samples=det_samples,
            )

    return None
