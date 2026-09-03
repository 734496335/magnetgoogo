"""DYTT latest-series listing parser and shared-detail wrapper."""

from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import urlparse

from magnet.resource_index.adapters.dytt.parser import extract_quality_tags, parse_latest_listing as parse_movie_listing, parse_movie_detail
from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate
from magnet.resource_index.normalize.text import normalize_whitespace

SOURCE_ID = "dytt8899-series"
PARSER_VERSION = "dytt-series-parser/1.0.0"
ORIGIN = "https://www.dytt8899.com"


def _series_title(value: str) -> str:
    match = re.search(r"《([^》]+)》", value)
    if match:
        return normalize_whitespace(match.group(1))
    text = re.sub(r"^(?:19|20)\d{2}年\S*?电视剧", "", value)
    text = re.sub(r"(?:连载至|更新至|全第|全)\s*\d+\s*集.*$", "", text)
    return normalize_whitespace(text)


def _season_number(value: str) -> int | None:
    values = [int(item) for item in re.findall(r"第\s*(\d{1,2})\s*季", value)]
    values.extend(int(item) for item in re.findall(r"(?i)\bS(\d{1,2})(?:E\d+)?\b", value))
    chinese = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    values.extend(chinese[item] for item in re.findall(r"第([一二三四五六七八九十])季", value) if item in chinese)
    return max(values) if values else None


def _episode_number(value: str) -> int | None:
    values: list[int] = []
    for pattern in (
        r"(?:连载至|更新至)第?\s*0*(\d{1,4})\s*集",
        r"全第?\s*0*(\d{1,4})\s*集",
        r"第\s*0*(\d{1,4})\s*集",
        r"(?i)\bS\d{1,2}E0*(\d{1,4})\b",
    ):
        values.extend(int(item) for item in re.findall(pattern, value))
    return max(values) if values else None


def _update_status(value: str) -> str | None:
    match = re.search(r"((?:连载至|更新至|全第|全)\s*\d+\s*集.*)$", value)
    return normalize_whitespace(match.group(1)) if match else None


def parse_latest_listing(
    html: str,
    *,
    page_url: str,
    rank_offset: int = 0,
) -> list[MovieListingCandidate]:
    output: list[MovieListingCandidate] = []
    for item in parse_movie_listing(html, page_url=page_url, rank_offset=rank_offset):
        status = _update_status(item.listing_title)
        output.append(
            replace(
                item,
                rank=rank_offset + len(output) + 1,
                quality_tags=extract_quality_tags(item.listing_title),
                content_kind="series",
                series_title=_series_title(item.listing_title),
                season_number=_season_number(item.listing_title),
                episode_number=_episode_number(item.listing_title),
                episode_label=status,
                update_status=status,
                brand_id="dytt8899",
                endpoint_origin=f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}",
            )
        )
    return output


def parse_series_detail(
    html: str,
    *,
    candidate: MovieListingCandidate,
    raw_content: bytes | None = None,
) -> MovieDetail:
    detail = parse_movie_detail(html, candidate=candidate, raw_content=raw_content)
    return replace(
        detail,
        source_id=SOURCE_ID,
        parser_version=PARSER_VERSION,
        content_kind="series",
        series_title=candidate.series_title or detail.title,
        season_number=candidate.season_number or _season_number(detail.title + " " + (detail.original_title or "")),
        episode_number=candidate.episode_number,
        episode_label=candidate.episode_label,
        update_status=candidate.update_status,
        brand_id="dytt8899",
        endpoint_origin=candidate.endpoint_origin or ORIGIN,
    )
