# -*- coding: utf-8 -*-
"""Conservative cross-provider title/year gates for rating matches."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from difflib import SequenceMatcher
from urllib.parse import unquote, urlparse

from magnet.rating_resolver.models import LookupQuery, RatingValue
from magnet.rating_resolver.normalize import normalize_title, strip_year_from_title

_NON_TITLE = re.compile(r"[^0-9a-z\u3400-\u9fff]+", re.I)
_CJK = re.compile(r"[\u3400-\u9fff]")


def canonical_title(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", strip_year_from_title(value or "") or normalize_title(value or ""))
    return _NON_TITLE.sub("", text.casefold())


def _url_title(value: RatingValue) -> str | None:
    if not value.url:
        return None
    path = unquote(urlparse(value.url).path).rstrip("/")
    if not path:
        return None
    tail = path.rsplit("/", 1)[-1].replace("_", " ").replace("-", " ")
    return tail or None


def titles_equivalent(query_title: str | None, matched_title: str | None) -> bool:
    query = canonical_title(query_title)
    matched = canonical_title(matched_title)
    if not query or not matched:
        return False
    if query == matched:
        return True

    shorter = min(len(query), len(matched))
    if query in matched or matched in query:
        # Long exact substrings support bilingual subjects such as
        # “中文名 The English Title”. Very short Chinese titles such as
        # “侦探” remain too ambiguous; exact equality was handled above.
        return shorter >= 5

    query_has_cjk = bool(_CJK.search(query))
    matched_has_cjk = bool(_CJK.search(matched))
    if query_has_cjk != matched_has_cjk:
        return False

    ratio = SequenceMatcher(None, query, matched).ratio()
    return ratio >= (0.78 if query_has_cjk else 0.82)


def rejection_reason(query: LookupQuery, value: RatingValue) -> str | None:
    if value.status != "ok" or value.score is None:
        return None

    query_imdb = (query.imdb_id or "").strip().casefold()
    matched_id = (value.external_id or "").strip().casefold()
    if value.source == "imdb" and query_imdb:
        if matched_id == query_imdb:
            return None
        return "imdb_id_mismatch"

    if query.year is not None and value.matched_year is not None:
        if abs(int(query.year) - int(value.matched_year)) > 1:
            return "year_mismatch"

    matched_title = value.matched_title or _url_title(value)
    candidates = [query.title, query.original_title]
    if not any(titles_equivalent(candidate, matched_title) for candidate in candidates if candidate):
        return "title_mismatch" if matched_title else "matched_title_missing"

    canonical_matched = canonical_title(matched_title)
    if (
        query.year is not None
        and value.matched_year is None
        and len(canonical_matched) <= 4
        and not query_imdb
    ):
        return "short_title_without_year"
    return None


def enforce_match(query: LookupQuery, value: RatingValue) -> RatingValue:
    reason = rejection_reason(query, value)
    if reason is None:
        return value
    provider_note = (value.note or "").strip()
    note = f"match_gate:{reason}"
    if provider_note:
        note = f"{note}; provider_note={provider_note}"
    return replace(
        value,
        status="no_match",
        score=None,
        score_text=None,
        confidence=0.0,
        note=note,
    )
