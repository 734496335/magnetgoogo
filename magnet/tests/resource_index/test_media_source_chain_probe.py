from __future__ import annotations

from types import SimpleNamespace

import pytest

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline.media_source_chain_probe import (
    probe_media_source,
    probe_media_sources,
)


def _spec(factory, *, source_id: str = "sixv", delay: float = 15.0, listing_pages: int = 8, detail_upper: int = 1):
    return SimpleNamespace(
        source_id=source_id,
        minimum_delay_seconds=delay,
        max_listing_pages=listing_pages,
        detail_requests_per_item_upper_bound=detail_upper,
        allowed_origins=("https://example.test",),
        crawler_factory=factory,
    )


def _candidate(rank: int):
    return SimpleNamespace(rank=rank, source_item_key=f"item-{rank}")


def _detail(*, magnet: bool):
    resources = ()
    if magnet:
        resources = (
            SimpleNamespace(
                resource_type="magnet",
                resource_url=f"magnet:?xt=urn:btih:{'a' * 40}",
                info_hash="a" * 40,
            ),
        )
    return SimpleNamespace(resources=resources)


def test_probe_media_source_requires_real_detail_magnet_and_bounds_policy() -> None:
    captured = {}

    class Crawler:
        http_requests = 0

        def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
            self.http_requests += 1
            captured["limit"] = limit
            captured["listing_pages"] = max_listing_pages
            return [_candidate(1), _candidate(2), _candidate(3)]

        def crawl_movie_detail(self, candidate):
            self.http_requests += 1
            return _detail(magnet=candidate.rank == 2)

    def factory(**kwargs):
        captured.update(kwargs)
        return Crawler()

    result = probe_media_source(
        "sixv",
        candidate_limit=3,
        spec_loader=lambda _source_id: _spec(factory),
    )

    assert result["status"] == "pass"
    assert result["stage"] == "detail-magnet"
    assert result["detail_attempts"] == 2
    assert result["magnet_count"] == 1
    assert result["http_requests"] == 3
    assert result["request_budget"] == 5
    assert result["request_delay_seconds"] == 15.0
    assert captured["policy"].enabled is True
    assert captured["policy"].acknowledged is True
    assert captured["policy"].max_pages == 5
    assert captured["policy"].request_delay_seconds == 15.0
    assert captured["origin"] == "https://example.test"
    assert captured["allowed_origins"] == ("https://example.test",)
    assert captured["listing_pages"] == 2


def test_probe_media_source_accounts_for_two_request_detail_sources() -> None:
    captured = {}

    class Crawler:
        http_requests = 0

        def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
            self.http_requests += 1
            return [_candidate(1), _candidate(2), _candidate(3)]

        def crawl_movie_detail(self, _candidate_value):
            self.http_requests += 2
            return _detail(magnet=True)

    def factory(**kwargs):
        captured.update(kwargs)
        return Crawler()

    result = probe_media_source(
        "mjf-series",
        candidate_limit=3,
        spec_loader=lambda _source_id: _spec(
            factory,
            source_id="mjf-series",
            delay=10.0,
            listing_pages=1,
            detail_upper=2,
        ),
    )

    assert result["status"] == "pass"
    assert result["request_budget"] == 7
    assert captured["policy"].max_pages == 7


def test_probe_media_source_fails_when_all_details_have_no_valid_magnet() -> None:
    class Crawler:
        http_requests = 0

        def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
            self.http_requests += 1
            return [_candidate(index + 1) for index in range(limit)]

        def crawl_movie_detail(self, _candidate_value):
            self.http_requests += 1
            return _detail(magnet=False)

    result = probe_media_source(
        "sixv",
        candidate_limit=3,
        spec_loader=lambda _source_id: _spec(lambda **_kwargs: Crawler()),
    )

    assert result["status"] == "failed"
    assert result["stage"] == "detail-magnet"
    assert result["magnet_count"] == 0
    assert result["detail_attempts"] == 3
    assert [item["error"]["error_code"] for item in result["detail_failures"]] == [
        "MAGNET_NOT_FOUND",
        "MAGNET_NOT_FOUND",
        "MAGNET_NOT_FOUND",
    ]


def test_probe_media_sources_runs_all_sources_and_reports_failures() -> None:
    class Crawler:
        def __init__(self, source_id: str) -> None:
            self.source_id = source_id
            self.http_requests = 0

        def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
            self.http_requests += 1
            return [_candidate(index + 1) for index in range(limit)]

        def crawl_movie_detail(self, _candidate_value):
            self.http_requests += 1
            return _detail(magnet=self.source_id != "bad")

    def load(source_id: str):
        return _spec(
            lambda **_kwargs: Crawler(source_id),
            source_id=source_id,
            delay=10.0,
            listing_pages=1,
        )

    result = probe_media_sources(("good-a", "bad", "good-b"), candidate_limit=1, spec_loader=load)

    assert result["status"] == "failed"
    assert result["source_count"] == 3
    assert result["passed_count"] == 2
    assert result["failed_sources"] == ["bad"]
    assert [item["source_id"] for item in result["results"]] == ["good-a", "bad", "good-b"]


def test_probe_media_source_rejects_unbounded_candidate_limit() -> None:
    with pytest.raises(ResourceIndexError, match="candidate_limit"):
        probe_media_source("sixv", candidate_limit=6, spec_loader=lambda _source_id: None)
