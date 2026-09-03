"""Low-frequency live crawler for MJF latest series."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse

from magnet.resource_index.acquisition.http_client import LiveHttpClient, normalized_origin
from magnet.resource_index.acquisition.policy import LiveFetchPolicy, PhysicalRequestBudget
from magnet.resource_index.adapters.mjf.parser import (
    ORIGIN,
    SOURCE_ID,
    latest_resource_page_url,
    parse_latest_listing,
    parse_series_detail,
)
from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate
from magnet.resource_index.errors import CONFIG_ERROR, LIVE_EMPTY_RESULT, LIVE_URL_REJECTED, ResourceIndexError


class MjfSeriesLiveCrawler:
    source_id = SOURCE_ID

    def __init__(
        self,
        *,
        policy: LiveFetchPolicy | None = None,
        origin: str = ORIGIN,
        allowed_origins: tuple[str, ...] | None = None,
        client: LiveHttpClient | None = None,
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
        response = self.client.get(f"{self.origin}/gx.html", referer=f"{self.origin}/")
        candidates = parse_latest_listing(
            response.text,
            page_url=response.url,
            reference_date=date.today(),
        )
        if len(candidates) < limit:
            raise ResourceIndexError(
                LIVE_EMPTY_RESULT,
                "MJF latest-series listing did not contain the requested count",
                {"requested": limit, "found": len(candidates)},
            )
        return candidates[:limit]

    def crawl_movie_detail(self, candidate: MovieListingCandidate) -> MovieDetail:
        self.policy.assert_allowed()
        parsed = urlparse(candidate.detail_url)
        if normalized_origin(candidate.detail_url) not in self.allowed_origins:
            raise ResourceIndexError(
                LIVE_URL_REJECTED,
                "MJF detail URL is outside the registered origin",
                {"detail_url": candidate.detail_url},
            )
        if not re.fullmatch(r"/jianjie/\d+\.html", parsed.path):
            raise ResourceIndexError(
                LIVE_URL_REJECTED,
                "MJF detail URL is outside the allowed series path",
                {"detail_url": candidate.detail_url},
            )
        detail_response = self.client.get(candidate.detail_url, referer=f"{self.origin}/gx.html")
        resource_url = latest_resource_page_url(detail_response.text, page_url=detail_response.url)
        if resource_url is None:
            raise ResourceIndexError(
                LIVE_EMPTY_RESULT,
                "MJF series detail contains no public BT resource page",
                {"detail_url": candidate.detail_url},
            )
        resource_path = urlparse(resource_url).path
        if normalized_origin(resource_url) not in self.allowed_origins or not re.fullmatch(r"/bt/\d+\.html", resource_path):
            raise ResourceIndexError(
                LIVE_URL_REJECTED,
                "MJF resource URL is outside the allowed BT path",
                {"resource_url": resource_url},
            )
        resource_response = self.client.get(resource_url, referer=detail_response.url)
        return parse_series_detail(
            detail_response.text,
            candidate=candidate,
            resource_html=resource_response.text,
            raw_content=detail_response.content,
        )
