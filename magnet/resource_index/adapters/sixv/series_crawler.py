"""Low-frequency live crawler for SixV latest television series."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from magnet.resource_index.acquisition.http_client import LiveHttpClient, normalized_origin
from magnet.resource_index.acquisition.policy import LiveFetchPolicy, PhysicalRequestBudget
from magnet.resource_index.adapters.sixv.parser import decode_sixv_html
from magnet.resource_index.adapters.sixv.series_parser import (
    ORIGIN,
    SOURCE_ID,
    parse_latest_series_listing,
    parse_series_detail,
)
from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate
from magnet.resource_index.errors import CONFIG_ERROR, LIVE_EMPTY_RESULT, LIVE_URL_REJECTED, ResourceIndexError


class SixVSeriesLiveCrawler:
    source_id = SOURCE_ID

    def __init__(
        self,
        *,
        policy: LiveFetchPolicy | None = None,
        origin: str = ORIGIN,
        allowed_origins: tuple[str, ...] | None = None,
        client: LiveHttpClient | None = None,
        today: date | None = None,
    ) -> None:
        self.origin = origin.rstrip("/")
        self.policy = policy or LiveFetchPolicy.from_flags()
        self.request_budget = PhysicalRequestBudget(self.policy.max_pages)
        self.allowed_origins = {
            normalized_origin(value)
            for value in (allowed_origins or (self.origin,))
        }
        self.client = client or LiveHttpClient(
            request_delay_seconds=self.policy.request_delay_seconds,
            allowed_origins=self.allowed_origins,
            request_budget=self.request_budget,
        )
        self.today = today or date.today()

    @property
    def http_requests(self) -> int:
        return int(self.request_budget.used)

    def crawl_latest_candidates(
        self,
        *,
        limit: int = 50,
        max_listing_pages: int = 1,
    ) -> list[MovieListingCandidate]:
        if limit <= 0 or max_listing_pages <= 0:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "limit and max_listing_pages must be positive",
                {"limit": limit, "max_listing_pages": max_listing_pages},
            )
        self.policy.assert_allowed()
        response = self.client.get(
            f"{self.origin}/gvod/dsj.html",
            referer=f"{self.origin}/",
        )
        html = decode_sixv_html(response.content)
        candidates = parse_latest_series_listing(
            html,
            page_url=response.url,
            reference_date=self.today,
        )
        if len(candidates) < limit:
            raise ResourceIndexError(
                LIVE_EMPTY_RESULT,
                "SixV latest-series page did not contain the requested count",
                {"requested": limit, "found": len(candidates)},
            )
        return candidates[:limit]

    def crawl_movie_detail(self, candidate: MovieListingCandidate) -> MovieDetail:
        self.policy.assert_allowed()
        parsed = urlparse(candidate.detail_url)
        if normalized_origin(candidate.detail_url) not in self.allowed_origins:
            raise ResourceIndexError(
                LIVE_URL_REJECTED,
                "SixV series detail URL is outside the registered brand origins",
                {"detail_url": candidate.detail_url},
            )
        if not any(parsed.path.startswith(prefix) for prefix in ("/dlz/", "/rj/", "/mj/")):
            raise ResourceIndexError(
                LIVE_URL_REJECTED,
                "SixV series detail URL is outside the public series paths",
                {"detail_url": candidate.detail_url},
            )
        response = self.client.get(
            candidate.detail_url,
            referer=f"{self.origin}/gvod/dsj.html",
        )
        return parse_series_detail(
            decode_sixv_html(response.content),
            candidate=candidate,
            raw_content=response.content,
        )
