"""Low-frequency live crawler for SixV latest television series."""

from __future__ import annotations

from dataclasses import replace
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
        limit: int = 100,
        max_listing_pages: int = 8,
    ) -> list[MovieListingCandidate]:
        if limit <= 0 or max_listing_pages <= 0:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "limit and max_listing_pages must be positive",
                {"limit": limit, "max_listing_pages": max_listing_pages},
            )
        self.policy.assert_allowed()
        candidates: list[MovieListingCandidate] = []
        seen_urls: set[str] = set()

        def collect(page_url: str, *, referer: str) -> int:
            response = self.client.get(page_url, referer=referer)
            parsed = parse_latest_series_listing(
                decode_sixv_html(response.content),
                page_url=response.url,
                reference_date=self.today,
                rank_offset=len(candidates),
            )
            added = 0
            for item in parsed:
                if item.detail_url in seen_urls:
                    continue
                seen_urls.add(item.detail_url)
                candidates.append(replace(item, rank=len(candidates) + 1))
                added += 1
                if len(candidates) >= limit:
                    break
            return added

        listing_requests = 0
        collect(
            f"{self.origin}/gvod/dsj.html",
            referer=f"{self.origin}/",
        )
        listing_requests += 1

        archive_categories = ("dlz", "rj", "mj")
        exhausted: set[str] = set()
        archive_page = 1
        while len(candidates) < limit and listing_requests < max_listing_pages:
            progressed = False
            for category in archive_categories:
                if category in exhausted or listing_requests >= max_listing_pages:
                    continue
                page_url = (
                    f"{self.origin}/{category}/"
                    if archive_page == 1
                    else f"{self.origin}/{category}/index_{archive_page}.html"
                )
                added = collect(
                    page_url,
                    referer=f"{self.origin}/{category}/",
                )
                listing_requests += 1
                if added == 0:
                    exhausted.add(category)
                else:
                    progressed = True
                if len(candidates) >= limit:
                    break
            if len(exhausted) == len(archive_categories) or not progressed:
                break
            archive_page += 1

        if len(candidates) < limit:
            raise ResourceIndexError(
                LIVE_EMPTY_RESULT,
                "SixV series listings did not contain the requested count",
                {
                    "requested": limit,
                    "found": len(candidates),
                    "listing_requests": listing_requests,
                    "max_listing_pages": max_listing_pages,
                },
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
