"""Orchestrator — picks a Tier for a source+query, executes, falls back on TierError.

Public API:
    search(source, query) -> list[SearchResult]
    classify(source) -> TierPlan   # re-exported from detector

Tier construction is lazy (Tier 1 imports cloakbrowser which is heavy) and
cached per process — see _TIER_CACHE.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from .detector import TierPlan, classify
from .tiers.base import SearchResult, TierError, TierKind, Tier

log = logging.getLogger(__name__)

_TIER_CACHE: dict[TierKind, Tier] = {}


def _get_tier(kind: TierKind) -> Tier:
    if kind in _TIER_CACHE:
        return _TIER_CACHE[kind]
    if kind == TierKind.HTTP:
        from .tiers.tier0_http import Tier0Http
        t = Tier0Http()
    elif kind == TierKind.CLOAK:
        from .tiers.tier1_cloak import Tier1Cloak
        t = Tier1Cloak(headless=True, humanize=True)
    elif kind == TierKind.HANDLER:
        from .tiers.tier2_handler import Tier2Handler
        t = Tier2Handler()
    elif kind == TierKind.USERASSIST:
        from .tiers.tier3_stub import Tier3UserAssistStub
        t = Tier3UserAssistStub()
    else:
        raise ValueError(f"unknown tier kind: {kind}")
    _TIER_CACHE[kind] = t
    return t


def search(source: dict, query: str, *, limit: int = 24) -> list[SearchResult]:
    """Search a single source. Walks the Tier plan, returns first success."""
    plan = classify(source)
    site_name = source.get("site", {}).get("name", "?")
    log.info("[orchestrator] %s plan=%s reason=%s", site_name, [k.value for k in plan.order], plan.reason)

    last_err: TierError | None = None
    for kind in plan.order:
        try:
            tier = _get_tier(kind)
        except TierError as e:
            log.warning("[orchestrator] %s skip %s: %s", site_name, kind.value, e.reason)
            last_err = e
            continue
        except Exception as e:
            log.error("[orchestrator] %s tier %s init failed: %s", site_name, kind.value, e)
            continue

        if not tier.supports(source):
            log.debug("[orchestrator] %s tier %s declined (supports=False)", site_name, kind.value)
            continue

        t0 = time.time()
        try:
            results = tier.search(source, query, limit=limit)
            elapsed = time.time() - t0
            log.info(
                "[orchestrator] %s ✓ %s n=%d in %.2fs",
                site_name, kind.value, len(results), elapsed,
            )
            return results
        except TierError as e:
            elapsed = time.time() - t0
            log.info(
                "[orchestrator] %s ✗ %s reason=%s hint=%s in %.2fs",
                site_name, kind.value, e.reason, e.hint, elapsed,
            )
            last_err = e
            continue
        except Exception as e:
            elapsed = time.time() - t0
            log.error("[orchestrator] %s ✗ %s UNEXPECTED %s in %.2fs", site_name, kind.value, e, elapsed)
            last_err = TierError(f"unexpected: {e}", retryable=False)
            continue

    log.warning("[orchestrator] %s exhausted all tiers, last=%s", site_name, last_err)
    return []
