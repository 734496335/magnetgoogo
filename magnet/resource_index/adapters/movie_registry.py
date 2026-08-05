"""Registry for independently parsed movie sites sharing one runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

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
    crawler_factory: Callable[..., MovieCrawler]
    brand_id: str | None = None
    content_kind: str = "movie"
    parser_variant: str | None = None
    catalog_role: str = "supplemental"
    metadata_priority: int = 0
    publish_count: int | None = None


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
            "brand_id": spec.brand_id,
            "content_kind": spec.content_kind,
            "parser_variant": spec.parser_variant,
            "catalog_role": spec.catalog_role,
            "metadata_priority": spec.metadata_priority,
            "publish_count": spec.publish_count,
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
                default_count=100,
                minimum_delay_seconds=10.0,
                minimum_check_interval_hours=12,
                daily_request_budget=100,
                default_batch_size=5,
                automatic_max_batches=6,
                snapshot_max_requests=12,
                batch_max_requests=12,
                max_listing_pages=4,
                robots_url=None,
                allowed_origins=("https://www.6v520.com",),
                allowed_path_prefixes=("/dy/",),
                crawler_factory=lambda policy, origin=None, allowed_origins=None: SixVLiveCrawler(
                    policy=policy,
                    origin=origin or "https://www.6v520.com",
                    allowed_origins=allowed_origins,
                ),
                brand_id="sixv",
                content_kind="movie",
                parser_variant="sixv_legacy",
                catalog_role="primary",
                metadata_priority=300,
            )
        )
    if "sixv-series" not in _SPECS:
        from magnet.resource_index.adapters.sixv.series_crawler import SixVSeriesLiveCrawler

        register_movie_source(
            MovieSourceSpec(
                source_id="sixv-series",
                snapshot_schema="media-latest/sixv-series/1",
                default_count=100,
                minimum_delay_seconds=10.0,
                minimum_check_interval_hours=12,
                daily_request_budget=120,
                default_batch_size=10,
                automatic_max_batches=5,
                snapshot_max_requests=8,
                batch_max_requests=12,
                max_listing_pages=8,
                robots_url=None,
                allowed_origins=(
                    "https://www.6v520.com",
                    "https://www.6v520.net",
                    "https://www.6v520.cc",
                ),
                allowed_path_prefixes=("/gvod/", "/dlz/", "/rj/", "/mj/"),
                crawler_factory=lambda policy, origin=None, allowed_origins=None: SixVSeriesLiveCrawler(
                    policy=policy,
                    origin=origin or "https://www.6v520.com",
                    allowed_origins=allowed_origins,
                ),
                brand_id="sixv",
                content_kind="series",
                parser_variant="sixv_legacy",
                catalog_role="supplemental",
                metadata_priority=200,
            )
        )
    if "meijumi" not in _SPECS:
        from magnet.resource_index.adapters.meijumi.live_crawler import MeijumiLiveCrawler

        register_movie_source(
            MovieSourceSpec(
                source_id="meijumi",
                snapshot_schema="media-latest/meijumi/1",
                default_count=100,
                minimum_delay_seconds=12.0,
                minimum_check_interval_hours=12,
                daily_request_budget=120,
                default_batch_size=10,
                automatic_max_batches=5,
                snapshot_max_requests=2,
                batch_max_requests=12,
                max_listing_pages=1,
                robots_url="https://www.meijumi.net/robots.txt",
                allowed_origins=("https://www.meijumi.net",),
                allowed_path_prefixes=("/news/", "/"),
                crawler_factory=lambda policy, origin=None, allowed_origins=None: MeijumiLiveCrawler(
                    policy=policy,
                    origin=origin or "https://www.meijumi.net",
                    allowed_origins=allowed_origins,
                ),
                brand_id="meijumi",
                content_kind="series",
                parser_variant="meijumi_wordpress",
                catalog_role="primary",
                metadata_priority=300,
            )
        )
    if "dytt8899" not in _SPECS:
        from magnet.resource_index.adapters.dytt.live_crawler import DyttLiveCrawler

        register_movie_source(
            MovieSourceSpec(
                source_id="dytt8899",
                snapshot_schema="movie-latest/dytt8899/1",
                default_count=250,
                minimum_delay_seconds=15.0,
                minimum_check_interval_hours=12,
                daily_request_budget=300,
                default_batch_size=10,
                automatic_max_batches=5,
                snapshot_max_requests=12,
                batch_max_requests=12,
                max_listing_pages=10,
                robots_url="https://www.dytt8899.com/robots.txt",
                allowed_origins=("https://www.dytt8899.com",),
                allowed_path_prefixes=("/html/gndy/dyzz/", "/i/"),
                crawler_factory=lambda policy, origin=None, allowed_origins=None: DyttLiveCrawler(
                    policy=policy,
                    origin=origin or "https://www.dytt8899.com",
                    allowed_origins=allowed_origins,
                ),
                brand_id="dytt8899",
                content_kind="movie",
                parser_variant="dytt_empire",
                catalog_role="supplemental",
                metadata_priority=200,
                publish_count=100,
            )
        )
