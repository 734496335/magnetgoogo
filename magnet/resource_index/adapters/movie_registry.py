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
    detail_requests_per_item_upper_bound: int | None = None
    parser_epoch: str = "unknown"


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
            "detail_requests_per_item_upper_bound": spec.detail_requests_per_item_upper_bound,
            "parser_epoch": spec.parser_epoch,
        }
        for source_id, spec in sorted(_SPECS.items())
    }


def _ensure_builtin_movie_sources() -> None:
    if "sixv" not in _SPECS:
        from magnet.resource_index.adapters.sixv.live_crawler import SixVLiveCrawler
        from magnet.resource_index.adapters.sixv.parser import PARSER_VERSION as SIXV_PARSER_VERSION

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
                max_listing_pages=5,
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
                detail_requests_per_item_upper_bound=1,
                parser_epoch=SIXV_PARSER_VERSION,
            )
        )
    if "sixv-series" not in _SPECS:
        from magnet.resource_index.adapters.sixv.parser import PARSER_VERSION as SIXV_BASE_PARSER_VERSION
        from magnet.resource_index.adapters.sixv.series_crawler import SixVSeriesLiveCrawler
        from magnet.resource_index.adapters.sixv.series_parser import PARSER_VERSION as SIXV_SERIES_PARSER_VERSION

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
                detail_requests_per_item_upper_bound=1,
                parser_epoch=f"{SIXV_SERIES_PARSER_VERSION}+{SIXV_BASE_PARSER_VERSION}",
            )
        )
    if "dytt8899-series" not in _SPECS:
        from magnet.resource_index.adapters.dytt.series_crawler import DyttSeriesLiveCrawler
        from magnet.resource_index.adapters.dytt.series_parser import PARSER_VERSION as DYTT_SERIES_PARSER_VERSION

        register_movie_source(
            MovieSourceSpec(
                source_id="dytt8899-series",
                snapshot_schema="media-latest/dytt8899-series/1",
                default_count=100,
                minimum_delay_seconds=12.0,
                minimum_check_interval_hours=12,
                daily_request_budget=140,
                default_batch_size=10,
                automatic_max_batches=10,
                snapshot_max_requests=6,
                batch_max_requests=10,
                max_listing_pages=6,
                robots_url="https://www.dytt8899.com/robots.txt",
                allowed_origins=("https://www.dytt8899.com",),
                allowed_path_prefixes=("/html/tv/", "/i/"),
                crawler_factory=lambda policy, origin=None, allowed_origins=None: DyttSeriesLiveCrawler(
                    policy=policy,
                    origin=origin or "https://www.dytt8899.com",
                    allowed_origins=allowed_origins,
                ),
                brand_id="dytt8899",
                content_kind="series",
                parser_variant="dytt_empire",
                catalog_role="supplemental",
                metadata_priority=220,
                detail_requests_per_item_upper_bound=1,
                parser_epoch=DYTT_SERIES_PARSER_VERSION,
            )
        )
    if "meijumi" not in _SPECS:
        from magnet.resource_index.adapters.meijumi.live_crawler import MeijumiLiveCrawler
        from magnet.resource_index.adapters.meijumi.parser import PARSER_VERSION as MEIJUMI_PARSER_VERSION

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
                detail_requests_per_item_upper_bound=1,
                parser_epoch=MEIJUMI_PARSER_VERSION,
            )
        )
    if "bitba-series" not in _SPECS:
        from magnet.resource_index.adapters.bitba.live_crawler import BitbaSeriesLiveCrawler
        from magnet.resource_index.adapters.bitba.parser import PARSER_VERSION as BITBA_SERIES_PARSER_VERSION

        register_movie_source(
            MovieSourceSpec(
                source_id="bitba-series",
                snapshot_schema="media-latest/bitba-series/1",
                default_count=100,
                minimum_delay_seconds=10.0,
                minimum_check_interval_hours=12,
                daily_request_budget=140,
                default_batch_size=10,
                automatic_max_batches=10,
                snapshot_max_requests=3,
                batch_max_requests=10,
                max_listing_pages=3,
                robots_url="https://www.bitba.net/robots.txt",
                allowed_origins=("https://www.bitba.net",),
                allowed_path_prefixes=("/filter-2", "/bt/"),
                crawler_factory=lambda policy, origin=None, allowed_origins=None: BitbaSeriesLiveCrawler(
                    policy=policy,
                    origin=origin or "https://www.bitba.net",
                    allowed_origins=allowed_origins,
                ),
                brand_id="bitba",
                content_kind="series",
                parser_variant="bitba_cards_jsonld",
                catalog_role="supplemental",
                metadata_priority=240,
                detail_requests_per_item_upper_bound=1,
                parser_epoch=BITBA_SERIES_PARSER_VERSION,
            )
        )
    if "mjf-series" not in _SPECS:
        from magnet.resource_index.adapters.mjf.live_crawler import MjfSeriesLiveCrawler
        from magnet.resource_index.adapters.mjf.parser import PARSER_VERSION as MJF_SERIES_PARSER_VERSION

        register_movie_source(
            MovieSourceSpec(
                source_id="mjf-series",
                snapshot_schema="media-latest/mjf-series/1",
                default_count=50,
                minimum_delay_seconds=10.0,
                minimum_check_interval_hours=12,
                daily_request_budget=130,
                default_batch_size=5,
                automatic_max_batches=10,
                snapshot_max_requests=1,
                batch_max_requests=10,
                max_listing_pages=1,
                robots_url="https://www.mjf2020.com/robots.txt",
                allowed_origins=("https://www.mjf2020.com",),
                allowed_path_prefixes=("/gx.html", "/jianjie/", "/bt/"),
                crawler_factory=lambda policy, origin=None, allowed_origins=None: MjfSeriesLiveCrawler(
                    policy=policy,
                    origin=origin or "https://www.mjf2020.com",
                    allowed_origins=allowed_origins,
                ),
                brand_id="mjf",
                content_kind="series",
                parser_variant="mjf_series",
                catalog_role="supplemental",
                metadata_priority=260,
                detail_requests_per_item_upper_bound=2,
                parser_epoch=MJF_SERIES_PARSER_VERSION,
            )
        )
    if "dytt8899" not in _SPECS:
        from magnet.resource_index.adapters.dytt.live_crawler import DyttLiveCrawler
        from magnet.resource_index.adapters.dytt.parser import PARSER_VERSION as DYTT_PARSER_VERSION

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
                detail_requests_per_item_upper_bound=1,
                parser_epoch=DYTT_PARSER_VERSION,
            )
        )
