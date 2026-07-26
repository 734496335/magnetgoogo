"""Registry for independently parsed movie sites sharing one runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate
from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError


class MovieCrawler(Protocol):
    source_id: str

    @property
    def http_requests(self) -> int: ...

    def crawl_latest_candidates(
        self,
        *,
        limit: int,
        max_listing_pages: int,
    ) -> list[MovieListingCandidate]: ...

    def crawl_movie_detail(self, candidate: MovieListingCandidate) -> MovieDetail: ...


@dataclass(frozen=True)
class MovieSourceSpec:
    source_id: str
    snapshot_schema: str
    default_count: int
    minimum_delay_seconds: float
    minimum_check_interval_hours: int
    daily_request_budget: int
    default_batch_size: int
    automatic_max_batches: int
    snapshot_max_requests: int
    batch_max_requests: int
    max_listing_pages: int
    robots_url: str | None
    allowed_origins: tuple[str, ...]
    allowed_path_prefixes: tuple[str, ...]
    crawler_factory: Callable[[LiveFetchPolicy], MovieCrawler]


_SPECS: dict[str, MovieSourceSpec] = {}


def register_movie_source(spec: MovieSourceSpec) -> None:
    _SPECS[spec.source_id] = spec


def get_movie_source(source_id: str) -> MovieSourceSpec:
    _ensure_builtin_movie_sources()
    spec = _SPECS.get(source_id)
    if spec is None:
        raise ResourceIndexError(
            CONFIG_ERROR,
            f"unknown movie source_id={source_id}",
            {"known": sorted(_SPECS)},
        )
    return spec


def list_movie_sources() -> dict[str, dict[str, object]]:
    _ensure_builtin_movie_sources()
    return {
        source_id: {
            "default_count": spec.default_count,
            "minimum_delay_seconds": spec.minimum_delay_seconds,
            "minimum_check_interval_hours": spec.minimum_check_interval_hours,
            "daily_request_budget": spec.daily_request_budget,
            "robots_url": spec.robots_url,
        }
        for source_id, spec in sorted(_SPECS.items())
    }


def _ensure_builtin_movie_sources() -> None:
    if "sixv" not in _SPECS:
        from magnet.resource_index.adapters.sixv.live_crawler import SixVLiveCrawler

        register_movie_source(
            MovieSourceSpec(
                source_id="sixv",
                snapshot_schema="sixv-latest-movies/1",
                default_count=50,
                minimum_delay_seconds=10.0,
                minimum_check_interval_hours=12,
                daily_request_budget=80,
                default_batch_size=5,
                automatic_max_batches=2,
                snapshot_max_requests=4,
                batch_max_requests=5,
                max_listing_pages=4,
                robots_url=None,
                allowed_origins=("https://www.6v520.com",),
                allowed_path_prefixes=("/dy/",),
                crawler_factory=lambda policy: SixVLiveCrawler(policy=policy),
            )
        )
    if "dytt8899" not in _SPECS:
        from magnet.resource_index.adapters.dytt.live_crawler import DyttLiveCrawler

        register_movie_source(
            MovieSourceSpec(
                source_id="dytt8899",
                snapshot_schema="movie-latest/dytt8899/1",
                default_count=25,
                minimum_delay_seconds=15.0,
                minimum_check_interval_hours=12,
                daily_request_budget=50,
                default_batch_size=5,
                automatic_max_batches=2,
                snapshot_max_requests=2,
                batch_max_requests=5,
                max_listing_pages=2,
                robots_url="https://www.dytt8899.com/robots.txt",
                allowed_origins=("https://www.dytt8899.com",),
                allowed_path_prefixes=("/html/gndy/dyzz/", "/i/"),
                crawler_factory=lambda policy: DyttLiveCrawler(policy=policy),
            )
        )
