"""Live crawler for the 6V latest-movie category."""

from __future__ import annotations

from magnet.resource_index.acquisition.http_client import LiveHttpClient, normalized_origin
from magnet.resource_index.acquisition.policy import LiveFetchPolicy, PhysicalRequestBudget
from magnet.resource_index.adapters.sixv.models import SixVListingCandidate, SixVMovieDetail
from magnet.resource_index.adapters.sixv.parser import ORIGIN, SOURCE_ID, parse_latest_listing, parse_movie_detail
from magnet.resource_index.errors import CONFIG_ERROR, LIVE_EMPTY_RESULT, ResourceIndexError


class SixVLiveCrawler:
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
        limit: int = 50,
        max_listing_pages: int = 4,
    ) -> list[SixVListingCandidate]:
        if limit <= 0 or max_listing_pages <= 0:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "limit and max_listing_pages must be positive",
                {"limit": limit, "max_listing_pages": max_listing_pages},
            )
        self.policy.assert_allowed()
        candidates: list[SixVListingCandidate] = []
        seen_urls: set[str] = set()
        for page in range(1, max_listing_pages + 1):
            page_url = (
                f"{self.origin}/dy/"
                if page == 1
                else f"{self.origin}/dy/index_{page}.html"
            )
            response = self.client.get(page_url, referer=f"{self.origin}/")
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
                "6V latest-movie listing returned no candidates",
                {"origin": self.origin},
            )
        if len(candidates) < limit:
            raise ResourceIndexError(
                LIVE_EMPTY_RESULT,
                "6V latest-movie listing did not contain the requested count",
                {"requested": limit, "found": len(candidates)},
            )
        return candidates[:limit]

    def crawl_movie_detail(self, candidate: SixVListingCandidate) -> SixVMovieDetail:
        self.policy.assert_allowed()
        response = self.client.get(
            candidate.detail_url,
            referer=f"{self.origin}/dy/",
        )
        return parse_movie_detail(
            response.text,
            candidate=candidate,
            raw_content=response.content,
        )
