"""Site-agnostic movie source models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MovieListingCandidate:
    rank: int
    detail_url: str
    source_item_key: str
    content_code: str
    listing_title: str
    update_date: date | None
    recommended: bool
    highlight_labels: tuple[str, ...]
    quality_tags: tuple[str, ...]
    content_kind: str = "movie"
    series_title: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    episode_label: str | None = None
    update_status: str | None = None
    brand_id: str | None = None
    endpoint_origin: str | None = None


@dataclass(frozen=True)
class MovieResource:
    resource_type: str
    provider: str
    resource_url: str
    info_hash: str | None
    display_title: str
    extraction_code: str | None
    quality_tags: tuple[str, ...]


@dataclass(frozen=True)
class MovieDetail:
    source_id: str
    source_item_key: str
    content_code: str
    detail_url: str
    listing_title: str
    title: str
    original_title: str | None
    year: int | None
    update_date: date | None
    release_date: date | None
    duration_minutes: int | None
    countries: tuple[str, ...]
    genres: tuple[str, ...]
    languages: tuple[str, ...]
    directors: tuple[str, ...]
    actors: tuple[str, ...]
    imdb_id: str | None
    douban_rating: float | None
    douban_rating_text: str | None
    douban_url: str | None
    cover_source_url: str | None
    synopsis: str | None
    recommended: bool
    highlight_labels: tuple[str, ...]
    quality_tags: tuple[str, ...]
    parser_version: str
    raw_document_hash: str
    resources: tuple[MovieResource, ...]
    content_kind: str = "movie"
    series_title: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    episode_label: str | None = None
    update_status: str | None = None
    brand_id: str | None = None
    endpoint_origin: str | None = None
