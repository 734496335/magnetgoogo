"""Low-frequency live crawler for Meijumi latest series."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from magnet.resource_index.acquisition.http_client import LiveHttpClient, normalized_origin
from magnet.resource_index.acquisition.policy import LiveFetchPolicy, PhysicalRequestBudget
from magnet.resource_index.adapters.meijumi.parser import (
    ORIGIN,
    SOURCE_ID,
    parse_latest_listing,
    parse_series_detail,
)
from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate
from magnet.resource_index.errors import CONFIG_ERROR, LIVE_EMPTY_RESULT, LIVE_URL_REJECTED, ResourceIndexError


class MeijumiLiveCrawler:
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
        self.client = client or LiveHttpClient(
            request_delay_seconds=self.policy.request_delay_seconds,
            allowed_origins={
                normalized_origin(value)
                for value in (allowed_origins or (self.origin,))
            },
            request_budget=self.request_budget,
        )

    @property
    def http_requests(self) -> int:
        return int(self.request_budget.used)

    def crawl_latest_candidates(
        self,
        *,
        limit: int = 100,
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
            f"{self.origin}/news/",
            referer=f"{self.origin}/",
        )
        candidates = parse_latest_listing(response.text, page_url=response.url)
        if len(candidates) < limit:
            raise ResourceIndexError(
                LIVE_EMPTY_RESULT,
                "Meijumi latest-series list did not contain the requested count",
                {"requested": limit, "found": len(candidates)},
            )
        return candidates[:limit]

    def crawl_movie_detail(self, candidate: MovieListingCandidate) -> MovieDetail:
        self.policy.assert_allowed()
        parsed = urlparse(candidate.detail_url)
        expected_host = urlparse(self.origin).hostname
        if (
            parsed.scheme != "https"
            or parsed.hostname != expected_host
            or not re.fullmatch(r"/\d+\.html", parsed.path)
        ):
            raise ResourceIndexError(
                LIVE_URL_REJECTED,
                "Meijumi detail URL is outside the allowed public series path",
                {"detail_url": candidate.detail_url},
            )
        response = self.client.get(
            candidate.detail_url,
            referer=f"{self.origin}/news/",
        )
        return parse_series_detail(
            response.text,
            candidate=candidate,
            raw_content=response.content,
        )
