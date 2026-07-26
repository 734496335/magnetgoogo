"""Low-frequency live crawler for DYTT movie pages."""

from __future__ import annotations

from urllib.parse import urlparse

from magnet.resource_index.acquisition.http_client import LiveHttpClient, normalized_origin
from magnet.resource_index.acquisition.policy import LiveFetchPolicy, PhysicalRequestBudget
from magnet.resource_index.adapters.dytt.parser import (
    ORIGIN,
    SOURCE_ID,
    parse_latest_listing,
    parse_movie_detail,
)
from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate
from magnet.resource_index.errors import CONFIG_ERROR, LIVE_EMPTY_RESULT, LIVE_URL_REJECTED, ResourceIndexError


class DyttLiveCrawler:
    source_id = SOURCE_ID

    def __init__(
        self,
        *,
        policy: LiveFetchPolicy | None = None,
        origin: str = ORIGIN,
        client: LiveHttpClient | None = None,
    ) -> None:
        self.origin = origin.rstrip("/")
        self.policy = policy or LiveFetchPolicy.from_flags()
        self.request_budget = PhysicalRequestBudget(self.policy.max_pages)
        self.client = client or LiveHttpClient(
            request_delay_seconds=self.policy.request_delay_seconds,
            allowed_origins={normalized_origin(self.origin)},
            request_budget=self.request_budget,
        )

    @property
    def http_requests(self) -> int:
        return int(self.request_budget.used)

    def crawl_latest_candidates(
        self,
        *,
        limit: int = 25,
        max_listing_pages: int = 2,
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
        for page in range(1, max_listing_pages + 1):
            page_url = (
                f"{self.origin}/html/gndy/dyzz/index.html"
                if page == 1
                else f"{self.origin}/html/gndy/dyzz/index_{page}.html"
            )
            response = self.client.get(page_url, referer=f"{self.origin}/index.html")
            parsed = parse_latest_listing(
                response.text,
                page_url=response.url,
                rank_offset=len(candidates),
            )
            for item in parsed:
                if item.detail_url in seen_urls:
                    continue
                seen_urls.add(item.detail_url)
                candidates.append(item)
                if len(candidates) >= limit:
                    return candidates[:limit]
            if not parsed:
                break
        if not candidates:
            raise ResourceIndexError(
                LIVE_EMPTY_RESULT,
                "DYTT latest-movie listing returned no candidates",
                {"origin": self.origin},
            )
        if len(candidates) < limit:
            raise ResourceIndexError(
                LIVE_EMPTY_RESULT,
                "DYTT latest-movie listing did not contain the requested count",
                {"requested": limit, "found": len(candidates)},
            )
        return candidates[:limit]

    def crawl_movie_detail(self, candidate: MovieListingCandidate) -> MovieDetail:
        self.policy.assert_allowed()
        parsed = urlparse(candidate.detail_url)
        if parsed.scheme != "https" or parsed.netloc.casefold() != urlparse(self.origin).netloc.casefold():
            raise ResourceIndexError(
                LIVE_URL_REJECTED,
                "DYTT detail URL is outside the source origin",
                {"detail_url": candidate.detail_url},
            )
        if not parsed.path.startswith("/i/") or not parsed.path.endswith(".html"):
            raise ResourceIndexError(
                LIVE_URL_REJECTED,
                "DYTT detail URL is outside the allowed public movie path",
                {"detail_url": candidate.detail_url},
            )
        response = self.client.get(
            candidate.detail_url,
            referer=f"{self.origin}/html/gndy/dyzz/index.html",
        )
        return parse_movie_detail(
            response.text,
            candidate=candidate,
            raw_content=response.content,
        )
