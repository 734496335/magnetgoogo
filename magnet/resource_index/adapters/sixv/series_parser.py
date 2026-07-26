"""SixV latest-series listing parser and shared-detail wrapper."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from magnet.resource_index.adapters.sixv.parser import (
    extract_quality_tags,
    parse_movie_detail,
)
from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate
from magnet.resource_index.normalize.text import normalize_whitespace

SOURCE_ID = "sixv-series"
PARSER_VERSION = "sixv-series-parser/1.0.0"
ORIGIN = "https://www.6v520.com"

_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _chinese_number(value: str) -> int | None:
    if not value:
        return None
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        tens = _DIGITS.get(left, 1) if left else 1
        ones = _DIGITS.get(right, 0) if right else 0
        number = tens * 10 + ones
        return number if number > 0 else None
    if all(character in _DIGITS for character in value):
        number = int("".join(str(_DIGITS[character]) for character in value))
        return number if number > 0 else None
    return None


def _season_number(value: str) -> int | None:
    numbers: list[int] = []
    for match in re.finditer(r"第\s*(\d+)\s*(?:-|至|到)?\s*(\d+)?\s*季", value):
        numbers.extend(int(group) for group in match.groups() if group)
    for match in re.finditer(r"第([零〇一二两三四五六七八九十]+)(?:至|到)?([零〇一二两三四五六七八九十]+)?季", value):
        numbers.extend(
            number
            for number in (_chinese_number(group) for group in match.groups() if group)
            if number is not None
        )
    return max(numbers) if numbers else None


def _episode_number(value: str) -> int | None:
    patterns = (
        r"更新\s*0*(\d{1,4})",
        r"第\s*0*(\d{1,4})\s*集",
        r"(?i)\bS\d{1,2}E0*(\d{1,4})\b",
        r"第[零〇一二两三四五六七八九十]+季\s*0*(\d{1,4})(?:\D|$)",
    )
    values: list[int] = []
    for pattern in patterns:
        values.extend(int(item) for item in re.findall(pattern, value))
    return max(values) if values else None


def _series_title(listing_title: str) -> str:
    bracketed = re.search(r"《([^》]+)》", listing_title)
    if bracketed:
        return normalize_whitespace(bracketed.group(1))
    text = re.sub(r"^(?:国剧|韩剧|日剧|美剧|英剧|欧美剧)\s*", "", listing_title)
    text = re.sub(
        r"(?:更新\s*\d+|全集|全\d+集|第[零〇一二两三四五六七八九十\d\-至到]+季.*)$",
        "",
        text,
    )
    return normalize_whitespace(text)


def _update_status(listing_title: str) -> str | None:
    bracketed = re.search(r"》\s*(.+)$", listing_title)
    if bracketed:
        return normalize_whitespace(bracketed.group(1)) or None
    match = re.search(
        r"(更新\s*\d+|全集|全\d+集|第[零〇一二两三四五六七八九十\d\-至到]+季.*)$",
        listing_title,
    )
    return normalize_whitespace(match.group(1)) if match else None


def _update_date(value: str, *, reference_date: date) -> date | None:
    match = re.search(r"(\d{1,2})-(\d{1,2})", value)
    if not match:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    year = reference_date.year
    if reference_date.month == 1 and month == 12:
        year -= 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_latest_series_listing(
    html: str,
    *,
    page_url: str,
    reference_date: date,
    rank_offset: int = 0,
) -> list[MovieListingCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    page_origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    output: list[MovieListingCandidate] = []
    for row in soup.select("#main ul.list > li, ul.list > li"):
        anchor = row.select_one("a[href]")
        if anchor is None:
            continue
        detail_url = urljoin(page_url, str(anchor.get("href") or ""))
        parsed = urlparse(detail_url)
        if not any(parsed.path.startswith(prefix) for prefix in ("/dlz/", "/rj/", "/mj/")):
            continue
        code_match = re.search(r"/([^/]+)\.html$", parsed.path)
        if code_match is None:
            continue
        listing_title = normalize_whitespace(anchor.get_text(" ", strip=True))
        if not listing_title:
            continue
        row_text = normalize_whitespace(row.get_text(" ", strip=True))
        update_status = _update_status(listing_title)
        season_number = _season_number(update_status or listing_title)
        episode_number = _episode_number(update_status or listing_title)
        output.append(
            MovieListingCandidate(
                rank=rank_offset + len(output) + 1,
                detail_url=detail_url,
                source_item_key=parsed.path,
                content_code=code_match.group(1),
                listing_title=listing_title,
                update_date=_update_date(row_text, reference_date=reference_date),
                recommended=False,
                highlight_labels=(),
                quality_tags=extract_quality_tags(listing_title),
                content_kind="series",
                series_title=_series_title(listing_title),
                season_number=season_number,
                episode_number=episode_number,
                episode_label=update_status,
                update_status=update_status,
                brand_id="sixv",
                endpoint_origin=page_origin,
            )
        )
    return output


def parse_series_detail(
    html: str,
    *,
    candidate: MovieListingCandidate,
    raw_content: bytes | None = None,
) -> MovieDetail:
    detail = parse_movie_detail(
        html,
        candidate=candidate,
        raw_content=raw_content,
    )
    return replace(
        detail,
        source_id=SOURCE_ID,
        parser_version=PARSER_VERSION,
        content_kind="series",
        series_title=candidate.series_title or detail.title,
        season_number=candidate.season_number,
        episode_number=candidate.episode_number,
        episode_label=candidate.episode_label,
        update_status=candidate.update_status,
        brand_id="sixv",
        endpoint_origin=candidate.endpoint_origin or ORIGIN,
    )
