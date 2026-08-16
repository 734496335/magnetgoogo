"""Tier 2 — Reverse-engineered handler registry.

For sources whose anti-bot is a JS-computed token (custom captcha / signed API):
we use hello_js_reverse_skill + js-reverse-mcp to AI-analyze the JS, recover the
algorithm, and ship a pure-Python handler. The handler then runs at Tier 0 speed
without any browser.

A "handler" is just a callable with signature:

    handler(source: dict, query: str) -> list[SearchResult]

Handlers register themselves in HANDLER_REGISTRY keyed by `platform` ID. A
sources.json rule opts into a handler by setting:

    "tier_override": {"tier": "tier2_handler", "platform": "thatcdn"}

Without an explicit platform mapping, Tier 2 declines (TierError).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from .base import SearchResult, Tier, TierError, TierKind, valid_search_results

log = logging.getLogger(__name__)

# Registry: platform_id → handler callable
HANDLER_REGISTRY: dict[str, Callable[[dict, str], list[SearchResult]]] = {}


def register_handler(platform_id: str):
    """Decorator to register a Tier 2 handler.

    Usage:
        @register_handler("thatcdn")
        def thatcdn_search(source, query): ...
    """
    def _decorator(fn: Callable[[dict, str], list[SearchResult]]):
        if platform_id in HANDLER_REGISTRY:
            log.warning("Handler %s already registered, overwriting", platform_id)
        HANDLER_REGISTRY[platform_id] = fn
        return fn
    return _decorator


class Tier2Handler(Tier):
    kind = TierKind.HANDLER

    def supports(self, source: dict) -> bool:
        platform = self._resolve_platform(source)
        return platform is not None and platform in HANDLER_REGISTRY

    def search(self, source: dict, query: str, *, limit: int = 24) -> list[SearchResult]:
        platform = self._resolve_platform(source)
        if not platform:
            raise TierError("source has no platform mapping", retryable=False)

        handler = HANDLER_REGISTRY.get(platform)
        if handler is None:
            raise TierError(
                f"no registered handler for platform '{platform}'",
                retryable=False,
                hint="reverse_engineer_and_register",
            )

        results = handler(source, query)
        if not results:
            raise TierError(f"handler '{platform}' returned 0 results", retryable=False)
        usable = valid_search_results(results)
        if not usable:
            raise TierError(f"handler '{platform}' returned 0 valid bound results", retryable=False)
        return usable[:limit]

    @staticmethod
    def _resolve_platform(source: dict) -> str | None:
        override = source.get("tier_override") or {}
        if isinstance(override, dict):
            return override.get("platform")
        return None


# Auto-import all handlers so they self-register
def _autoload_handlers() -> None:
    import importlib
    import pkgutil
    from .. import handlers as _handlers_pkg

    for mod_info in pkgutil.iter_modules(_handlers_pkg.__path__):
        if mod_info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"magnet.crawler_v3.handlers.{mod_info.name}")
        except Exception as e:
            log.warning("Failed to load handler %s: %s", mod_info.name, e)


_autoload_handlers()
