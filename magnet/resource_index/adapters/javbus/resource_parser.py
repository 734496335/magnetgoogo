"""JavBus AJAX resource table parser."""

from __future__ import annotations

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


def _quality_flags(text: str) -> tuple[bool | None, bool | None, tuple[str, ...]]:
    lower = text.lower()
    tags: list[str] = []
    has_sub = None
    has_hd = None
    if "字幕" in text or "subtitle" in lower or "sub" in lower:
        has_sub = True
        tags.append("subtitle")
    if "高清" in text or "hd" in lower or "1080" in lower or "720" in lower or "4k" in lower:
        has_hd = True
        tags.append("hd")
    return has_sub, has_hd, tuple(tags)


def parse_resource_table(
    document: RawDocumentEnvelope,
    *,
    content_id: str,
    fallback_title: str | None = None,
) -> tuple[list[ResourceRelease], list[ParseWarning]]:
    soup = BeautifulSoup(document.body, "html.parser")
    warnings: list[ParseWarning] = []
    magnets = soup.select('a[href^="magnet:"]')
    if not magnets:
        # empty table still valid content
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
    for a in magnets:
        href = a.get("href") or ""
        row_title = normalize_whitespace(a.get_text(" ", strip=True))
        tr = a.find_parent("tr")
        size_display = None
        published_raw = None
        if tr is not None:
            cells = tr.find_all("td")
            if len(cells) >= 2:
                size_display = normalize_whitespace(cells[1].get_text(" ", strip=True)) or None
            if len(cells) >= 3:
                published_raw = normalize_whitespace(cells[2].get_text(" ", strip=True)) or None

        display_title = row_title or fallback_title or content_id
        try:
            magnet_uri, info_hash = normalize_magnet_uri(href, fallback_dn=display_title)
        except ResourceIndexError as exc:
            warnings.append(
                ParseWarning(exc.error_code or MAGNET_INVALID, exc.message, {"href_prefix": href[:32]})
            )
            continue

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

        has_sub, has_hd, qtags = _quality_flags(display_title)
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
            # Prefer more complete fields
            score_new = sum(
                1
                for v in (release.size_bytes, release.published_at, release.display_title)
                if v
            )
            score_old = sum(
                1
                for v in (existing.size_bytes, existing.published_at, existing.display_title)
                if v
            )
            if score_new >= score_old:
                best_by_hash[info_hash] = release

    if not best_by_hash:
        warnings.append(ParseWarning(RESOURCE_TABLE_EMPTY, "no valid magnets after parse", {}))
    return list(best_by_hash.values()), warnings
