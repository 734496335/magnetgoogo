"""Adapter + live crawler registry (multi-source extension point)."""

from __future__ import annotations

from typing import Callable, Protocol

from magnet.resource_index.adapters.base import ResourceSourceAdapter
from magnet.resource_index.adapters.javbus.adapter import JavBusAdapter
from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError


class LiveSourceCrawler(Protocol):
    source_id: str

    def crawl_query(self, query: str, *, limit: int) -> list: ...

    def crawl_detail_urls(self, detail_urls: list[str]) -> list: ...


_ADAPTERS: dict[str, Callable[[], ResourceSourceAdapter]] = {
    "javbus": JavBusAdapter,
}

_CRAWLERS: dict[str, Callable[..., LiveSourceCrawler]] = {}


def register_adapter(source_id: str, factory: Callable[[], ResourceSourceAdapter]) -> None:
    _ADAPTERS[source_id] = factory


def register_crawler(source_id: str, factory: Callable[..., LiveSourceCrawler]) -> None:
    _CRAWLERS[source_id] = factory


def get_adapter(source_id: str) -> ResourceSourceAdapter:
    factory = _ADAPTERS.get(source_id)
    if factory is None:
        raise ResourceIndexError(
            CONFIG_ERROR,
            f"unknown adapter source_id={source_id}",
            {"known": sorted(_ADAPTERS)},
        )
    return factory()


def get_crawler_factory(source_id: str) -> Callable[..., LiveSourceCrawler]:
    # lazy import registration
    _ensure_builtin_crawlers()
    factory = _CRAWLERS.get(source_id)
    if factory is None:
        raise ResourceIndexError(
            CONFIG_ERROR,
            f"unknown live crawler source_id={source_id}",
            {"known": sorted(_CRAWLERS)},
        )
    return factory


def list_sources() -> dict[str, dict[str, bool]]:
    _ensure_builtin_crawlers()
    keys = set(_ADAPTERS) | set(_CRAWLERS)
    return {
        k: {"adapter": k in _ADAPTERS, "live_crawler": k in _CRAWLERS} for k in sorted(keys)
    }


def _ensure_builtin_crawlers() -> None:
    if "javbus" not in _CRAWLERS:
        from magnet.resource_index.adapters.javbus.live_crawler import JavBusLiveCrawler

        register_crawler("javbus", JavBusLiveCrawler)
    if "sixv" not in _CRAWLERS:
        from magnet.resource_index.adapters.sixv.live_crawler import SixVLiveCrawler

        register_crawler("sixv", SixVLiveCrawler)
