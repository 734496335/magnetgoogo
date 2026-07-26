"""Manual low-frequency probes for movie and series brand endpoints."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime
from typing import Any, Iterable

from magnet.resource_index.acquisition.http_client import LiveHttpClient, normalized_origin
from magnet.resource_index.acquisition.policy import PhysicalRequestBudget
from magnet.resource_index.adapters.movie_brand_registry import (
    MovieBrandEndpoint,
    load_movie_brand_registry,
)
from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.normalize.text import normalize_whitespace


def _decode_html(content: bytes) -> str:
    match = re.search(br"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)", content[:4096], re.I)
    encoding = match.group(1).decode("ascii", errors="ignore") if match else "utf-8"
    if encoding.casefold() in {"gb2312", "gbk", "x-gbk"}:
        encoding = "gb18030"
    try:
        return content.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return content.decode("utf-8", errors="replace")


def _title(content: bytes) -> str | None:
    html = _decode_html(content)
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not match:
        return None
    return normalize_whitespace(re.sub(r"<[^>]+>", " ", match.group(1))) or None


def _selected_endpoints(
    *,
    brand_ids: Iterable[str] | None,
    include_candidates: bool,
) -> list[tuple[str, MovieBrandEndpoint]]:
    registry = load_movie_brand_registry()
    selected = set(brand_ids or ())
    output: list[tuple[str, MovieBrandEndpoint]] = []
    for brand in registry.brands:
        if selected and brand.brand_id not in selected:
            continue
        for endpoint in sorted(brand.endpoints, key=lambda item: item.priority):
            if endpoint.state in {"active", "standby"} or (
                include_candidates and endpoint.state in {"candidate", "discovery_only", "unavailable"}
            ):
                output.append((brand.brand_id, endpoint))
    return output


def probe_movie_brands(
    *,
    brand_ids: Iterable[str] | None = None,
    include_candidates: bool = False,
    delay_seconds: float = 2.0,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    endpoints = _selected_endpoints(
        brand_ids=brand_ids,
        include_candidates=include_candidates,
    )
    results: list[dict[str, Any]] = []
    for index, (brand_id, endpoint) in enumerate(endpoints):
        allowed = {normalized_origin(value) for value in endpoint.allowed_origins}
        request_budget = PhysicalRequestBudget(
            2 if endpoint.role == "redirect_alias" else 1
        )
        client = LiveHttpClient(
            request_delay_seconds=0,
            timeout_seconds=20,
            max_retries=0,
            allowed_origins=allowed,
            request_budget=request_budget,
        )
        record: dict[str, Any] = {
            "brand_id": brand_id,
            "endpoint_id": endpoint.endpoint_id,
            "origin": endpoint.origin,
            "role": endpoint.role,
            "configured_state": endpoint.state,
            "parser_variant": endpoint.parser_variant,
            "evidence": endpoint.evidence,
        }
        try:
            response = client.get(endpoint.origin + "/")
            content_hash = hashlib.sha256(response.content).hexdigest()
            record.update(
                {
                    "reachable": True,
                    "status_code": response.status_code,
                    "final_url": response.url,
                    "content_length": len(response.content),
                    "content_hash": content_hash,
                    "content_fingerprint": content_hash[:12],
                    "title": _title(response.content),
                    "http_requests": request_budget.used,
                    "matches_recorded_fingerprint": (
                        endpoint.content_fingerprint is None
                        or endpoint.content_fingerprint == content_hash[:12]
                    ),
                }
            )
        except ResourceIndexError as exc:
            record.update(
                {
                    "reachable": False,
                    "error_code": exc.error_code,
                    "error": exc.message,
                    "http_requests": request_budget.used,
                }
            )
        except Exception as exc:
            record.update(
                {
                    "reachable": False,
                    "error_code": type(exc).__name__,
                    "error": str(exc)[:200],
                    "http_requests": request_budget.used,
                }
            )
        results.append(record)
        if index + 1 < len(endpoints) and delay_seconds > 0:
            sleep(delay_seconds)
    return {
        "schema_version": "movie-brand-probe/1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "include_candidates": include_candidates,
        "result_count": len(results),
        "reachable_count": sum(1 for item in results if item.get("reachable")),
        "results": results,
    }
