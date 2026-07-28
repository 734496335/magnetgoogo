# -*- coding: utf-8 -*-
from __future__ import annotations

from magnet.rating_resolver.providers.bangumi import BangumiProvider
from magnet.rating_resolver.providers.base import Provider
from magnet.rating_resolver.providers.douban import DoubanProvider
from magnet.rating_resolver.providers.imdb import ImdbProvider
from magnet.rating_resolver.providers.rotten_tomatoes import RottenTomatoesProvider

ALL_PROVIDERS: dict[str, type[Provider]] = {
    "douban": DoubanProvider,
    "imdb": ImdbProvider,
    "rotten_tomatoes": RottenTomatoesProvider,
    "rt": RottenTomatoesProvider,
    "bangumi": BangumiProvider,
}

DEFAULT_SOURCES = ("douban", "imdb", "rotten_tomatoes", "bangumi")


def build_providers(names: list[str] | tuple[str, ...] | None = None) -> list[Provider]:
    chosen = names or DEFAULT_SOURCES
    out: list[Provider] = []
    seen: set[str] = set()
    for n in chosen:
        key = n.strip().lower()
        cls = ALL_PROVIDERS.get(key)
        if cls is None:
            continue
        # avoid double RT
        inst_name = cls.name
        if inst_name in seen:
            continue
        seen.add(inst_name)
        out.append(cls())
    return out
