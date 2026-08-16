"""Parser layer — converts HTML/JSON → list[SearchResult].

Reuses crawler_v2's Smart List Detector (battle-tested, bake-off winner).
This module is the single seam for parsing: all Tiers funnel through it.
"""
from __future__ import annotations

import html as html_lib
import logging
import re
import urllib.parse
from typing import Any

from ..tiers.base import SearchResult

log = logging.getLogger(__name__)

# Defer heavy imports
try:
    from magnet.crawler_v2.smart_list import detect_list_rows  # type: ignore
    _HAS_SMART_LIST = True
except ImportError:
    detect_list_rows = None
    _HAS_SMART_LIST = False

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    BeautifulSoup = None


MAGNET_RE = re.compile(
    r"magnet:\?xt=urn:btih:(?:[0-9A-Fa-f]{40}|[A-Z2-7]{32})(?=$|[^A-Za-z0-9])[^\s\"'<>]*",
    re.I,
)
INFO_HASH_HEX_RE = re.compile(r"\b([A-Fa-f0-9]{40})\b")
INFO_HASH_B32_RE = re.compile(r"\b([A-Za-z2-7]{32})\b")


def derive_magnet_from_url(url: str | None) -> str | None:
    """Trivially derive magnet link from detail URL containing info_hash."""
    if not url:
        return None
    m = INFO_HASH_HEX_RE.search(url)
    if m:
        return f"magnet:?xt=urn:btih:{m.group(1).upper()}"
    m = INFO_HASH_B32_RE.search(url)
    if m:
        return f"magnet:?xt=urn:btih:{m.group(1).upper()}"
    return None


def extract_results_from_html(
    html: str,
    *,
    source: dict,
    base_url: str | None = None,
) -> list[SearchResult]:
    """Extract SearchResult list from a search-page HTML.

    Strategy:
    1. If sources.json has explicit `selectors`, use those (precise path).
    2. Else fall back to Smart List Detector (crawler_v2/smart_list.py).
    3. Always post-process to attach magnet links (in-page or via detail follow).

    Detail-following is NOT done here — it's a Tier-level concern. We only
    surface magnets that are present in the search-page HTML or trivially
    derivable (e.g. info_hash in URL).
    """
    if not html:
        return []

    selectors = (
        source.get("selectors")
        or ((source.get("search") or {}).get("parse_metadata") or {}).get("selectors")
        or {}
    )
    if selectors and BeautifulSoup is not None:
        results = _extract_via_selectors(html, selectors, base_url=base_url)
        if results:
            return results

    if _HAS_SMART_LIST and BeautifulSoup is not None:
        try:
            rows = detect_list_rows(html, base_url=base_url or "")
            return _rows_to_results(rows, html=html)
        except Exception as e:
            log.warning("smart_list detector failed: %s", e)

    # Last-resort: brute regex magnet scan
    return _bruteforce_magnet_scan(html)


def _extract_via_selectors(html: str, selectors: dict, *, base_url: str | None) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    list_sel = selectors.get("list_item") or selectors.get("row")
    if not list_sel:
        return []

    results: list[SearchResult] = []
    title_sel = selectors.get("title")
    magnet_sel = selectors.get("magnet")
    detail_sel = selectors.get("detail_link")
    size_sel = selectors.get("size")
    seeders_sel = selectors.get("seeders")

    for node in soup.select(list_sel):
        title_el = node.select_one(title_sel) if title_sel else node
        title = (title_el.get_text(strip=True) if title_el else "").strip()
        if not title:
            continue

        magnet = ""
        if magnet_sel:
            m_el = node.select_one(magnet_sel)
            if m_el:
                href = m_el.get("href", "")
                val = m_el.get("value", "")
                data_mag = m_el.get("data-magnet", "")
                if href.startswith("magnet:"):
                    magnet = href
                elif val.startswith("magnet:"):
                    magnet = val
                elif data_mag.startswith("magnet:"):
                    magnet = data_mag
        if not magnet:
            # in-row regex fallback
            m = MAGNET_RE.search(str(node))
            if m:
                magnet = m.group(0)

        detail_url = None
        if detail_sel:
            d_el = node.select_one(detail_sel)
            if d_el and d_el.get("href"):
                detail_url = urllib.parse.urljoin(base_url or "", d_el["href"])

        if not magnet and detail_url:
            derived = derive_magnet_from_url(detail_url)
            if derived:
                magnet = derived

        if not (magnet or detail_url):
            continue

        size = (node.select_one(size_sel).get_text(strip=True) if size_sel and node.select_one(size_sel) else None)
        seeders = None
        if seeders_sel:
            s_el = node.select_one(seeders_sel)
            if s_el:
                txt = s_el.get_text(strip=True)
                try:
                    seeders = int(re.sub(r"[^\d]", "", txt) or "0")
                except ValueError:
                    pass

        results.append(SearchResult(
            title=title,
            magnet=magnet,
            size=size,
            seeders=seeders,
            detail_url=detail_url,
        ))

    return results


def _rows_to_results(rows: list[dict], *, html: str) -> list[SearchResult]:
    out: list[SearchResult] = []
    for r in rows:
        title = (r.get("title") or "").strip()
        detail_url = r.get("detail_url")
        magnet = ""
        # rows from smart_list don't carry magnet; try inline regex on outer HTML if available
        outer = r.get("outer_html") or ""
        m = MAGNET_RE.search(outer)
        if m:
            magnet = m.group(0)
        if not title:
            continue
        if not (magnet or detail_url):
            continue
        out.append(SearchResult(title=title, magnet=magnet, detail_url=detail_url))
    return out


def _bruteforce_magnet_scan(html: str) -> list[SearchResult]:
    """Last-resort scan that accepts only self-describing magnets.

    A page-global hash is not search evidence. The magnet itself must carry a
    non-hash `dn` title so title and info-hash remain bound in one URI.
    """
    seen: set[str] = set()
    out: list[SearchResult] = []
    for m in MAGNET_RE.finditer(html_lib.unescape(html)):
        link = m.group(0)
        if link in seen:
            continue
        seen.add(link)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)
        title = (params.get("dn") or [""])[0].strip()
        if not title:
            continue
        if INFO_HASH_HEX_RE.fullmatch(title) or INFO_HASH_B32_RE.fullmatch(title):
            continue
        out.append(SearchResult(title=title, magnet=link))
    return out
