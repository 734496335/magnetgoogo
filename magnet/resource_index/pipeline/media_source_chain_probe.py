"""Bounded live chain probe for the production media source set."""

from __future__ import annotations

import re
from typing import Any, Callable

from magnet.resource_index.acquisition.policy import HARD_MAX_PAGES, MIN_DELAY_SECONDS, LiveFetchPolicy
from magnet.resource_index.adapters.movie_registry import MovieSourceSpec, get_movie_source
from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError

DEFAULT_MEDIA_SOURCE_IDS = (
    "sixv",
    "dytt8899",
    "meijumi",
    "sixv-series",
    "bitba-series",
    "mjf-series",
)


def _error_payload(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, ResourceIndexError):
        return {
            "type": type(exc).__name__,
            "error_code": exc.error_code,
            "message": exc.message,
        }
    return {
        "type": type(exc).__name__,
        "error_code": "UNEXPECTED",
        "message": str(exc),
    }


def _valid_magnet_count(detail: Any) -> int:
    count = 0
    for resource in getattr(detail, "resources", ()) or ():
        if str(getattr(resource, "resource_type", "") or "").lower() != "magnet":
            continue
        url = str(getattr(resource, "resource_url", "") or "")
        info_hash = str(getattr(resource, "info_hash", "") or "")
        if not url.lower().startswith("magnet:?xt=urn:btih:"):
            continue
        if not re.fullmatch(r"(?:[0-9A-Fa-f]{40}|[A-Z2-7]{32})", info_hash):
            continue
        count += 1
    return count


def probe_media_source(
    source_id: str,
    *,
    candidate_limit: int = 3,
    spec_loader: Callable[[str], MovieSourceSpec] = get_movie_source,
) -> dict[str, Any]:
    if candidate_limit < 1 or candidate_limit > 5:
        raise ResourceIndexError(CONFIG_ERROR, "media source probe candidate_limit must be between 1 and 5", {})
    spec = spec_loader(source_id)
    listing_pages = max(1, min(int(spec.max_listing_pages), 2))
    detail_upper = max(1, int(spec.detail_requests_per_item_upper_bound or 1))
    max_pages = min(HARD_MAX_PAGES, listing_pages + candidate_limit * detail_upper)
    delay = max(float(spec.minimum_delay_seconds), MIN_DELAY_SECONDS)
    policy = LiveFetchPolicy.from_flags(
        env_enabled=True,
        acknowledged=True,
        max_pages=max_pages,
        request_delay_seconds=delay,
    )
    origin = spec.allowed_origins[0] if spec.allowed_origins else None
    crawler = spec.crawler_factory(
        policy=policy,
        origin=origin,
        allowed_origins=spec.allowed_origins,
    )
    try:
        candidates = crawler.crawl_latest_candidates(
            limit=candidate_limit,
            max_listing_pages=listing_pages,
        )
    except BaseException as exc:
        return {
            "source_id": source_id,
            "status": "failed",
            "stage": "listing",
            "listing_pages_limit": listing_pages,
            "request_budget": max_pages,
            "request_delay_seconds": delay,
            "http_requests": int(getattr(crawler, "http_requests", 0) or 0),
            "error": _error_payload(exc),
        }

    detail_failures: list[dict[str, Any]] = []
    attempts = 0
    for candidate in candidates[:candidate_limit]:
        attempts += 1
        try:
            detail = crawler.crawl_movie_detail(candidate)
        except BaseException as exc:
            detail_failures.append(
                {
                    "rank": int(getattr(candidate, "rank", attempts) or attempts),
                    "error": _error_payload(exc),
                }
            )
            continue
        magnet_count = _valid_magnet_count(detail)
        if magnet_count > 0:
            return {
                "source_id": source_id,
                "status": "pass",
                "stage": "detail-magnet",
                "listing_count": len(candidates),
                "detail_attempts": attempts,
                "magnet_count": magnet_count,
                "request_budget": max_pages,
                "request_delay_seconds": delay,
                "http_requests": int(getattr(crawler, "http_requests", 0) or 0),
            }
        detail_failures.append(
            {
                "rank": int(getattr(candidate, "rank", attempts) or attempts),
                "error": {
                    "type": "ProbeError",
                    "error_code": "MAGNET_NOT_FOUND",
                    "message": "detail parsed successfully but contained no valid magnet resource",
                },
            }
        )

    return {
        "source_id": source_id,
        "status": "failed",
        "stage": "detail-magnet",
        "listing_count": len(candidates),
        "detail_attempts": attempts,
        "magnet_count": 0,
        "request_budget": max_pages,
        "request_delay_seconds": delay,
        "http_requests": int(getattr(crawler, "http_requests", 0) or 0),
        "detail_failures": detail_failures,
    }


def probe_media_sources(
    source_ids: tuple[str, ...] = DEFAULT_MEDIA_SOURCE_IDS,
    *,
    candidate_limit: int = 3,
    spec_loader: Callable[[str], MovieSourceSpec] = get_movie_source,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for source_id in source_ids:
        try:
            result = probe_media_source(
                source_id,
                candidate_limit=candidate_limit,
                spec_loader=spec_loader,
            )
        except BaseException as exc:
            result = {
                "source_id": source_id,
                "status": "failed",
                "stage": "setup",
                "error": _error_payload(exc),
            }
        results.append(result)
    failed = [item["source_id"] for item in results if item.get("status") != "pass"]
    return {
        "schema_version": "media-source-chain-probe/1",
        "status": "pass" if not failed else "failed",
        "candidate_limit": candidate_limit,
        "source_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed_sources": failed,
        "results": results,
    }
