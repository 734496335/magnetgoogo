"""Same-brand mirror failover and stable identity contracts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate, MovieResource
from magnet.resource_index.errors import CONFIG_ERROR, LIVE_HTTP_ERROR, ResourceIndexError
from magnet.resource_index.pipeline.latest_crawl import LatestCrawlPaths
from magnet.resource_index.pipeline.movie_latest import MovieLatestRunner
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _candidate(
    origin: str,
    *,
    rank: int = 1,
    path: str = "/dy/test.html",
    content_kind: str = "movie",
) -> MovieListingCandidate:
    return MovieListingCandidate(
        rank=rank,
        detail_url=f"{origin}{path}",
        source_item_key=path.split("?", 1)[0],
        content_code=f"TEST-{rank}",
        listing_title="2026剧情《镜像测试》1080p.HD中字",
        update_date=date(2026, 7, 26),
        recommended=False,
        highlight_labels=(),
        quality_tags=("1080p", "HD", "中字"),
        content_kind=content_kind,
    )


def _detail(candidate: MovieListingCandidate) -> MovieDetail:
    return MovieDetail(
        source_id="sixv",
        source_item_key=candidate.source_item_key,
        content_code=candidate.content_code,
        detail_url=candidate.detail_url,
        listing_title=candidate.listing_title,
        title="镜像测试",
        original_title=None,
        year=2026,
        update_date=candidate.update_date,
        release_date=None,
        duration_minutes=None,
        countries=("中国",),
        genres=("剧情",),
        languages=("国语",),
        directors=(),
        actors=(),
        imdb_id=None,
        douban_rating=None,
        douban_rating_text=None,
        douban_url=None,
        cover_source_url="https://img.example/test.jpg",
        synopsis="用于验证镜像切换不会重抓详情。",
        recommended=False,
        highlight_labels=(),
        quality_tags=candidate.quality_tags,
        parser_version="test/1",
        raw_document_hash="a" * 64,
        resources=(
            MovieResource(
                resource_type="magnet",
                provider="magnet",
                resource_url="magnet:?xt=urn:btih:97430cd2a109439fc6e7da6b7ace7c4e6d53127c",
                info_hash="97430CD2A109439FC6E7DA6B7ACE7C4E6D53127C",
                display_title="1080p",
                extraction_code=None,
                quality_tags=("1080p",),
            ),
        ),
    )


class _MirrorCrawler:
    def __init__(self, origin: str, phase: dict[str, object]) -> None:
        self.origin = origin.rstrip("/")
        self.phase = phase
        self.http_requests = 0

    def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
        self.http_requests += 1
        if self.phase["mode"] == "fail-primary" and self.origin == "https://www.6v520.com":
            raise ResourceIndexError(LIVE_HTTP_ERROR, "primary unavailable", {})
        self.phase["listing_origins"].append(self.origin)
        return [_candidate(self.origin)]

    def crawl_movie_detail(self, candidate: MovieListingCandidate):
        self.http_requests += 1
        self.phase["detail_calls"] += 1
        return _detail(candidate)


def test_mirror_switch_reuses_source_item_key_without_detail_replay(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="sixv",
        target_count=1,
    )
    repo = SqliteResourceRepository(paths.db_path)
    phase: dict[str, object] = {
        "mode": "primary",
        "listing_origins": [],
        "detail_calls": 0,
    }

    def builder(_policy, *, origin=None, allowed_origins=None):
        assert allowed_origins == (
            "https://www.6v520.cc",
            "https://www.6v520.com",
            "https://www.6v520.net",
        )
        return _MirrorCrawler(origin, phase)

    runner = MovieLatestRunner(
        repo=repo,
        paths=paths,
        source_id="sixv",
        target_count=1,
        batch_size=1,
        snapshot_max_requests=3,
        batch_max_requests=1,
        max_listing_pages=1,
        crawler_builder=builder,
        clock=lambda: NOW,
    )
    first = runner.run(refresh=True)
    assert first.status == "success"
    assert phase["detail_calls"] == 1
    assert repo.conn.execute("SELECT detail_url FROM movie_items").fetchone()[0] == (
        "https://www.6v520.com/dy/test.html"
    )

    phase["mode"] = "fail-primary"
    phase["listing_origins"] = []
    second = runner.run(refresh=True)
    assert second.status == "success"
    assert second.invocation_http_requests == 2
    assert phase["detail_calls"] == 1
    row = repo.conn.execute(
        "SELECT detail_url, endpoint_origin, source_item_key FROM movie_items"
    ).fetchone()
    assert tuple(row) == (
        "https://www.6v520.net/dy/test.html",
        "https://www.6v520.net",
        "/dy/test.html",
    )
    assert phase["listing_origins"] == ["https://www.6v520.net"]
    repo.close()


class _LargeSnapshotCrawler:
    def __init__(self, origin: str, max_pages: int, *, fail_primary: bool) -> None:
        self.origin = origin.rstrip("/")
        self.max_pages = max_pages
        self.fail_primary = fail_primary
        self.http_requests = 0

    def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
        if self.fail_primary and self.origin == "https://www.6v520.com":
            self.http_requests = 1
            raise ResourceIndexError(LIVE_HTTP_ERROR, "primary unavailable", {})
        required_pages = 4
        if self.max_pages < required_pages:
            self.http_requests = self.max_pages
            raise ResourceIndexError(LIVE_HTTP_ERROR, "insufficient mirror budget", {})
        self.http_requests = required_pages
        return [
            _candidate(self.origin, rank=index, path=f"/dy/{index:03d}.html")
            for index in range(1, limit + 1)
        ]

    def crawl_movie_detail(self, candidate: MovieListingCandidate):
        raise AssertionError("details must not run in this snapshot-only test")


def test_large_snapshot_budget_allows_primary_failure_and_full_mirror_capture(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(tmp_path / "out", source_id="sixv", target_count=100)
    repo = SqliteResourceRepository(paths.db_path)

    def builder(policy, *, origin=None, allowed_origins=None):
        return _LargeSnapshotCrawler(origin, policy.max_pages, fail_primary=True)

    runner = MovieLatestRunner(
        repo=repo,
        paths=paths,
        source_id="sixv",
        target_count=100,
        batch_size=5,
        snapshot_max_requests=12,
        batch_max_requests=5,
        max_listing_pages=4,
        crawler_builder=builder,
        clock=lambda: NOW,
    )
    result = runner.run(refresh=True, max_batches=0)
    assert result.status == "pending"
    assert result.covered_count == 0
    assert result.invocation_http_requests == 5
    snapshot = paths.snapshot_path.read_text(encoding="utf-8")
    assert '"origin": "https://www.6v520.net"' in snapshot
    repo.close()


class _InvalidSnapshotCrawler:
    def __init__(self, candidates: list[MovieListingCandidate]) -> None:
        self.candidates = candidates
        self.http_requests = 1

    def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
        return self.candidates

    def crawl_movie_detail(self, candidate: MovieListingCandidate):
        raise AssertionError("invalid snapshots must stop before detail requests")


def test_snapshot_rejects_duplicate_stable_keys_even_when_urls_differ(tmp_path: Path) -> None:
    origin = "https://www.6v520.com"
    candidates = [
        _candidate(origin, rank=1, path="/dy/same.html?a=1"),
        _candidate(origin, rank=2, path="/dy/same.html?a=2"),
    ]
    paths = LatestCrawlPaths.for_output_dir(tmp_path / "out", source_id="sixv", target_count=2)
    repo = SqliteResourceRepository(paths.db_path)
    runner = MovieLatestRunner(
        repo=repo,
        paths=paths,
        source_id="sixv",
        target_count=2,
        batch_size=1,
        snapshot_max_requests=3,
        batch_max_requests=1,
        max_listing_pages=1,
        crawler_builder=lambda _policy, **_kwargs: _InvalidSnapshotCrawler(candidates),
        clock=lambda: NOW,
    )
    with pytest.raises(ResourceIndexError) as exc_info:
        runner.run(refresh=True, max_batches=0)
    assert exc_info.value.error_code == CONFIG_ERROR
    assert "source key" in exc_info.value.message
    repo.close()


def test_snapshot_rejects_content_kind_contract_mismatch(tmp_path: Path) -> None:
    candidate = _candidate("https://www.6v520.com", content_kind="series")
    paths = LatestCrawlPaths.for_output_dir(tmp_path / "out", source_id="sixv", target_count=1)
    repo = SqliteResourceRepository(paths.db_path)
    runner = MovieLatestRunner(
        repo=repo,
        paths=paths,
        source_id="sixv",
        target_count=1,
        batch_size=1,
        snapshot_max_requests=3,
        batch_max_requests=1,
        max_listing_pages=1,
        crawler_builder=lambda _policy, **_kwargs: _InvalidSnapshotCrawler([candidate]),
        clock=lambda: NOW,
    )
    with pytest.raises(ResourceIndexError) as exc_info:
        runner.run(refresh=True, max_batches=0)
    assert exc_info.value.error_code == CONFIG_ERROR
    assert "content kind" in exc_info.value.message
    repo.close()
