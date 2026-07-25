"""JavBus AJAX resource table parser."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote

from bs4 import BeautifulSoup

from magnet.resource_index.domain.identity import resource_id_for
from magnet.resource_index.domain.models import ParseWarning, RawDocumentEnvelope, ResourceRelease
from magnet.resource_index.errors import (
    MAGNET_INVALID,
    RESOURCE_TABLE_DOM_DRIFT,
    RESOURCE_TABLE_EMPTY,
    ParseError,
    ResourceIndexError,
)
from magnet.resource_index.normalize.dates import parse_date
from magnet.resource_index.normalize.magnets import normalize_magnet_uri
from magnet.resource_index.normalize.sizes import parse_size_bytes
from magnet.resource_index.normalize.text import normalize_whitespace

_SIZE_RE = re.compile(r"^\d+(\.\d+)?\s*(GB|GiB|MB|MiB|KB|TB|B)\b", re.I)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAGNET_IN_ONCLICK = re.compile(r"magnet:\?[^'\"\s)]+", re.I)


def _quality_flags(text: str) -> tuple[bool | None, bool | None, tuple[str, ...]]:
    lower = text.lower()
    tags: list[str] = []
    has_sub = None
    has_hd = None
    if "字幕" in text or "subtitle" in lower or re.search(r"\bsub\b", lower):
        has_sub = True
        tags.append("subtitle")
    if "高清" in text or re.search(r"\bhd\b", lower) or "1080" in lower or "720" in lower or "4k" in lower:
        has_hd = True
        tags.append("hd")
    return has_sub, has_hd, tuple(tags)


def _dn_from_magnet(href: str) -> str | None:
    if not href.startswith("magnet:?"):
        return None
    for key, value in parse_qsl(href[len("magnet:?") :], keep_blank_values=False):
        if key.lower() == "dn" and value:
            try:
                return unquote(value)
            except Exception:
                return value
    return None


def _collect_magnet_hrefs(soup: BeautifulSoup) -> list[tuple[str, object]]:
    """Return (magnet_href, anchor_or_None) pairs, including onclick-only magnets."""
    found: list[tuple[str, object]] = []
    seen: set[str] = set()
    for a in soup.select('a[href^="magnet:"]'):
        href = a.get("href") or ""
        if href.startswith("magnet:?") and href not in seen:
            seen.add(href)
            found.append((href, a))
    # onclick window.open('magnet:...')
    for el in soup.find_all(attrs={"onclick": True}):
        oc = el.get("onclick") or ""
        m = _MAGNET_IN_ONCLICK.search(oc)
        if not m:
            continue
        href = m.group(0)
        if href not in seen:
            seen.add(href)
            found.append((href, el if el.name == "a" else None))
    return found


def _weak_title(text: str | None) -> bool:
    if not text:
        return True
    t = text.strip()
    if not t:
        return True
    if _DATE_RE.match(t):
        return True
    if _SIZE_RE.match(t):
        return True
    if len(t) < 3:
        return True
    return False


def parse_resource_table(
    document: RawDocumentEnvelope,
    *,
    content_id: str,
    fallback_title: str | None = None,
) -> tuple[list[ResourceRelease], list[ParseWarning]]:
    soup = BeautifulSoup(document.body, "html.parser")
    warnings: list[ParseWarning] = []
    magnet_items = _collect_magnet_hrefs(soup)
    if not magnet_items:
        if soup.find("table") or soup.find("tr"):
            warnings.append(
                ParseWarning(RESOURCE_TABLE_EMPTY, "resource table has no magnets", {})
            )
            return [], warnings
        if not document.body.strip():
            warnings.append(
                ParseWarning(RESOURCE_TABLE_EMPTY, "empty resource document", {})
            )
            return [], warnings
        raise ParseError(
            RESOURCE_TABLE_DOM_DRIFT,
            "resource table structure not recognized",
            {},
        )

    best_by_hash: dict[str, ResourceRelease] = {}
    for href, node in magnet_items:
        row_title = ""
        if node is not None and getattr(node, "get_text", None):
            row_title = normalize_whitespace(node.get_text(" ", strip=True))
        tr = node.find_parent("tr") if node is not None and hasattr(node, "find_parent") else None
        size_display = None
        published_raw = None
        if tr is not None:
            for td in tr.find_all("td"):
                txt = normalize_whitespace(td.get_text(" ", strip=True))
                if not txt:
                    continue
                if size_display is None and _SIZE_RE.match(txt):
                    size_display = txt
                elif published_raw is None and _DATE_RE.match(txt):
                    published_raw = txt
                elif _weak_title(row_title) and not _SIZE_RE.match(txt) and not _DATE_RE.match(txt):
                    # use first non-size/date cell text as title candidate
                    if len(txt) > len(row_title or ""):
                        row_title = txt

        dn = _dn_from_magnet(href)
        if _weak_title(row_title):
            display_title = dn or fallback_title or content_id
        else:
            display_title = row_title

        try:
            magnet_uri, info_hash = normalize_magnet_uri(href, fallback_dn=display_title)
        except ResourceIndexError as exc:
            warnings.append(
                ParseWarning(
                    exc.error_code or MAGNET_INVALID,
                    exc.message,
                    {"href_prefix": href[:32]},
                )
            )
            continue

        # prefer dn after normalize if still weak
        if _weak_title(display_title) and dn:
            display_title = dn

        size_bytes = None
        if size_display:
            try:
                size_bytes = parse_size_bytes(size_display)
            except ResourceIndexError as exc:
                warnings.append(
                    ParseWarning(exc.error_code, exc.message, {"size_display": size_display})
                )

        published_at = None
        if published_raw:
            try:
                published_at = parse_date(published_raw)
            except ResourceIndexError as exp:
                warnings.append(
                    ParseWarning(exp.error_code, exp.message, {"published_raw": published_raw})
                )

        has_sub, has_hd, qtags = _quality_flags(display_title + " " + (size_display or ""))
        release = ResourceRelease(
            resource_id=resource_id_for(info_hash),
            content_id=content_id,
            info_hash=info_hash,
            magnet_uri=magnet_uri,
            display_title=display_title,
            size_bytes=size_bytes,
            size_display=size_display,
            published_at=published_at,
            has_subtitle=has_sub,
            has_hd=has_hd,
            quality_tags=qtags,
        )
        existing = best_by_hash.get(info_hash)
        if existing is None:
            best_by_hash[info_hash] = release
        else:
            score_new = sum(
                1 for v in (release.size_bytes, release.published_at, release.display_title) if v
            )
            score_old = sum(
                1 for v in (existing.size_bytes, existing.published_at, existing.display_title) if v
            )
            if score_new >= score_old:
                best_by_hash[info_hash] = release

    if not best_by_hash:
        warnings.append(ParseWarning(RESOURCE_TABLE_EMPTY, "no valid magnets after parse", {}))
    return list(best_by_hash.values()), warnings
