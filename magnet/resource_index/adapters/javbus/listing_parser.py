"""JavBus listing page parser."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from magnet.resource_index.adapters.javbus import selectors as sel
from magnet.resource_index.domain.models import ContentCandidate, RawDocumentEnvelope
from magnet.resource_index.errors import (
    ACCESS_CHALLENGE,
    AGE_GATE_PAGE,
    LISTING_DOM_DRIFT,
    LISTING_EMPTY,
    ParseError,
)
from magnet.resource_index.normalize.content_code import normalize_content_code
from magnet.resource_index.normalize.text import normalize_whitespace
from magnet.resource_index.normalize.urls import absolutize, path_key


def _page_kind(body: str) -> str | None:
    lower = body.lower()
    for marker in sel.AGE_GATE_MARKERS:
        if marker.lower() in lower or marker in body:
            return AGE_GATE_PAGE
    for marker in sel.CHALLENGE_MARKERS:
        if marker in lower:
            return ACCESS_CHALLENGE
    return None


def parse_listing(document: RawDocumentEnvelope) -> list[ContentCandidate]:
    kind = _page_kind(document.body)
    if kind == AGE_GATE_PAGE:
        raise ParseError(AGE_GATE_PAGE, "age verification page", {"url": document.source_url})
    if kind == ACCESS_CHALLENGE:
        raise ParseError(ACCESS_CHALLENGE, "access challenge page", {"url": document.source_url})

    soup = BeautifulSoup(document.body, "html.parser")
    items = soup.select(sel.LISTING_ITEM)
    if not items:
        # Distinguish empty-but-valid vs drift
        if soup.select("div.movie-box") or "movie-box" in document.body:
            raise ParseError(
                LISTING_DOM_DRIFT,
                "movie-box structure present but selector missed",
                {},
            )
        # valid empty listing container?
        if soup.select(".alert") or "沒有結果" in document.body or "没有结果" in document.body:
            raise ParseError(LISTING_EMPTY, "listing has no candidates", {})
        # If page has common site chrome without boxes → empty or drift
        if soup.find("body") and len(document.body) < 200:
            raise ParseError(LISTING_DOM_DRIFT, "page too small / unexpected", {})
        raise ParseError(LISTING_EMPTY, "no listing candidates found", {})

    seen_urls: set[str] = set()
    candidates: list[ContentCandidate] = []
    position = 0
    for el in items:
        href = el.get("href")
        detail_url = absolutize(document.source_url, href)
        if not detail_url:
            continue
        if detail_url in seen_urls:
            continue
        seen_urls.add(detail_url)
        position += 1

        img = el.find("img")
        cover = None
        if img is not None:
            cover = absolutize(document.source_url, img.get("src") or img.get("data-src"))

        raw_title = None
        span = el.select_one("div.photo-info span, span")
        if span is not None:
            raw_title = normalize_whitespace(span.get_text(" ", strip=True))
        if not raw_title and img is not None:
            raw_title = normalize_whitespace(img.get("title") or img.get("alt") or "")

        # date node often holds code or date
        date_el = el.select_one("date")
        date_text = normalize_whitespace(date_el.get_text()) if date_el else ""

        raw_code = None
        # Prefer date text if it looks like a code
        if date_text and normalize_content_code(date_text):
            raw_code = date_text
        if raw_title:
            m = re.match(r"^([A-Za-z0-9]+[-_]?[0-9]+)", raw_title)
            if m and not raw_code:
                raw_code = m.group(1)
        # path fallback
        path = path_key(detail_url)
        path_tail = path.rsplit("/", 1)[-1]
        if not raw_code and normalize_content_code(path_tail):
            raw_code = path_tail

        content_code = normalize_content_code(raw_code) if raw_code else None
        source_item_key = path if path != "/" else detail_url

        candidates.append(
            ContentCandidate(
                raw_title=raw_title or None,
                raw_content_code=raw_code,
                content_code=content_code,
                detail_url=detail_url,
                cover_source_url=cover,
                list_position=position,
                source_item_key=source_item_key,
            )
        )

    if not candidates:
        raise ParseError(LISTING_EMPTY, "listing items present but none usable", {})
    return candidates
