"""Validated movie and series brand-family registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError

_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "movie_source_brands.json"
)
_ALLOWED_ROLES = {
    "primary",
    "official_mirror",
    "redirect_alias",
    "release_page",
    "branch",
    "candidate",
    "discovery_portal",
}
_ALLOWED_STATES = {"active", "standby", "candidate", "discovery_only", "unavailable"}
_RUNTIME_STATES = {"active", "standby"}
_ALLOWED_CONTENT_KINDS = {
    "movie",
    "series",
    "anime",
    "variety",
    "documentary",
    "discovery",
}


@dataclass(frozen=True)
class MovieBrandEndpoint:
    endpoint_id: str
    origin: str
    role: str
    state: str
    parser_variant: str | None
    priority: int
    source_ids: tuple[str, ...]
    evidence: str
    verified_at: str | None
    content_fingerprint: str | None
    allowed_redirect_origins: tuple[str, ...]
    notes: str | None

    @property
    def runtime_enabled(self) -> bool:
        return self.state in _RUNTIME_STATES and self.parser_variant is not None

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        output = [self.origin]
        for origin in self.allowed_redirect_origins:
            if origin not in output:
                output.append(origin)
        return tuple(output)


@dataclass(frozen=True)
class MovieBrand:
    brand_id: str
    label: str
    content_kinds: tuple[str, ...]
    strategy: str
    endpoints: tuple[MovieBrandEndpoint, ...]


@dataclass(frozen=True)
class MovieBrandRegistry:
    schema_version: str
    verified_at: str
    brands: tuple[MovieBrand, ...]

    def get(self, brand_id: str) -> MovieBrand:
        for brand in self.brands:
            if brand.brand_id == brand_id:
                return brand
        raise ResourceIndexError(
            CONFIG_ERROR,
            f"unknown movie brand_id={brand_id}",
            {"known": sorted(brand.brand_id for brand in self.brands)},
        )

    def runtime_endpoints(
        self,
        *,
        brand_id: str,
        source_id: str,
        parser_variant: str,
    ) -> tuple[MovieBrandEndpoint, ...]:
        brand = self.get(brand_id)
        endpoints = tuple(
            endpoint
            for endpoint in sorted(brand.endpoints, key=lambda item: item.priority)
            if endpoint.runtime_enabled
            and endpoint.parser_variant == parser_variant
            and source_id in endpoint.source_ids
        )
        if not endpoints:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie brand has no enabled runtime endpoint",
                {
                    "brand_id": brand_id,
                    "source_id": source_id,
                    "parser_variant": parser_variant,
                },
            )
        return endpoints


def _valid_origin(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResourceIndexError(CONFIG_ERROR, f"{field} must be a non-empty URL", {})
    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ResourceIndexError(
            CONFIG_ERROR,
            f"{field} must use http/https and include a host",
            {"value": value},
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ResourceIndexError(
            CONFIG_ERROR,
            f"{field} must be an origin without credentials/query/fragment",
            {"value": value},
        )
    return normalized


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ResourceIndexError(CONFIG_ERROR, f"{field} must be a string array", {})
    if len(set(value)) != len(value):
        raise ResourceIndexError(CONFIG_ERROR, f"{field} contains duplicates", {})
    return tuple(value)


def _parse_endpoint(raw: object, *, endpoint_ids: set[str], origins: set[str]) -> MovieBrandEndpoint:
    if not isinstance(raw, dict):
        raise ResourceIndexError(CONFIG_ERROR, "movie brand endpoint must be an object", {})
    endpoint_id = raw.get("endpoint_id")
    if not isinstance(endpoint_id, str) or not endpoint_id:
        raise ResourceIndexError(CONFIG_ERROR, "movie brand endpoint_id is required", {})
    if endpoint_id in endpoint_ids:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "duplicate movie brand endpoint_id",
            {"endpoint_id": endpoint_id},
        )
    endpoint_ids.add(endpoint_id)
    origin = _valid_origin(raw.get("origin"), field="origin")
    if origin in origins:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "movie brand origin belongs to multiple endpoints",
            {"origin": origin},
        )
    origins.add(origin)
    role = raw.get("role")
    state = raw.get("state")
    if role not in _ALLOWED_ROLES:
        raise ResourceIndexError(CONFIG_ERROR, "invalid movie brand endpoint role", {"role": role})
    if state not in _ALLOWED_STATES:
        raise ResourceIndexError(CONFIG_ERROR, "invalid movie brand endpoint state", {"state": state})
    parser_variant = raw.get("parser_variant")
    if parser_variant is not None and (not isinstance(parser_variant, str) or not parser_variant):
        raise ResourceIndexError(CONFIG_ERROR, "parser_variant must be null or non-empty", {})
    priority = raw.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
        raise ResourceIndexError(CONFIG_ERROR, "movie brand priority must be a non-negative integer", {})
    source_ids = _string_tuple(raw.get("source_ids", []), field="source_ids")
    allowed_redirect_origins = tuple(
        _valid_origin(item, field="allowed_redirect_origins")
        for item in _string_tuple(
            raw.get("allowed_redirect_origins", []),
            field="allowed_redirect_origins",
        )
    )
    if state in _RUNTIME_STATES and (not source_ids or parser_variant is None):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "active/standby movie endpoint requires source_ids and parser_variant",
            {"endpoint_id": endpoint_id},
        )
    evidence = raw.get("evidence")
    if not isinstance(evidence, str) or not evidence:
        raise ResourceIndexError(CONFIG_ERROR, "movie brand endpoint evidence is required", {})
    verified_at = raw.get("verified_at")
    content_fingerprint = raw.get("content_fingerprint")
    notes = raw.get("notes")
    for value, field in (
        (verified_at, "verified_at"),
        (content_fingerprint, "content_fingerprint"),
        (notes, "notes"),
    ):
        if value is not None and not isinstance(value, str):
            raise ResourceIndexError(CONFIG_ERROR, f"{field} must be null or string", {})
    return MovieBrandEndpoint(
        endpoint_id=endpoint_id,
        origin=origin,
        role=role,
        state=state,
        parser_variant=parser_variant,
        priority=priority,
        source_ids=source_ids,
        evidence=evidence,
        verified_at=verified_at,
        content_fingerprint=content_fingerprint,
        allowed_redirect_origins=allowed_redirect_origins,
        notes=notes,
    )


def _parse_registry(payload: object) -> MovieBrandRegistry:
    if not isinstance(payload, dict) or payload.get("schema_version") != "movie-source-brands/1":
        raise ResourceIndexError(CONFIG_ERROR, "unsupported movie brand registry schema", {})
    verified_at = payload.get("verified_at")
    if not isinstance(verified_at, str) or not verified_at:
        raise ResourceIndexError(CONFIG_ERROR, "movie brand registry verified_at is required", {})
    raw_brands = payload.get("brands")
    if not isinstance(raw_brands, list) or not raw_brands:
        raise ResourceIndexError(CONFIG_ERROR, "movie brand registry brands must be non-empty", {})
    brand_ids: set[str] = set()
    endpoint_ids: set[str] = set()
    origins: set[str] = set()
    brands: list[MovieBrand] = []
    for raw in raw_brands:
        if not isinstance(raw, dict):
            raise ResourceIndexError(CONFIG_ERROR, "movie brand must be an object", {})
        brand_id = raw.get("brand_id")
        label = raw.get("label")
        strategy = raw.get("strategy")
        if not isinstance(brand_id, str) or not brand_id or brand_id in brand_ids:
            raise ResourceIndexError(CONFIG_ERROR, "movie brand_id must be unique", {"brand_id": brand_id})
        brand_ids.add(brand_id)
        if not isinstance(label, str) or not label or not isinstance(strategy, str) or not strategy:
            raise ResourceIndexError(CONFIG_ERROR, "movie brand label and strategy are required", {})
        content_kinds = _string_tuple(raw.get("content_kinds"), field="content_kinds")
        invalid = sorted(set(content_kinds) - _ALLOWED_CONTENT_KINDS)
        if invalid:
            raise ResourceIndexError(CONFIG_ERROR, "invalid movie brand content kinds", {"invalid": invalid})
        raw_endpoints = raw.get("endpoints")
        if not isinstance(raw_endpoints, list) or not raw_endpoints:
            raise ResourceIndexError(CONFIG_ERROR, "movie brand endpoints must be non-empty", {})
        endpoints = tuple(
            _parse_endpoint(item, endpoint_ids=endpoint_ids, origins=origins)
            for item in raw_endpoints
        )
        brands.append(
            MovieBrand(
                brand_id=brand_id,
                label=label,
                content_kinds=content_kinds,
                strategy=strategy,
                endpoints=endpoints,
            )
        )
    return MovieBrandRegistry(
        schema_version="movie-source-brands/1",
        verified_at=verified_at,
        brands=tuple(brands),
    )


@lru_cache(maxsize=1)
def load_movie_brand_registry(path: str | Path | None = None) -> MovieBrandRegistry:
    selected = Path(path) if path is not None else _CONFIG_PATH
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "unable to load movie brand registry",
            {"path": str(selected)},
        ) from exc
    return _parse_registry(payload)


def get_movie_brand(brand_id: str) -> MovieBrand:
    return load_movie_brand_registry().get(brand_id)


def list_movie_brands() -> dict[str, dict[str, object]]:
    registry = load_movie_brand_registry()
    return {
        brand.brand_id: {
            "label": brand.label,
            "content_kinds": list(brand.content_kinds),
            "strategy": brand.strategy,
            "endpoints": [
                {
                    "endpoint_id": endpoint.endpoint_id,
                    "origin": endpoint.origin,
                    "role": endpoint.role,
                    "state": endpoint.state,
                    "parser_variant": endpoint.parser_variant,
                    "priority": endpoint.priority,
                    "source_ids": list(endpoint.source_ids),
                    "evidence": endpoint.evidence,
                    "verified_at": endpoint.verified_at,
                }
                for endpoint in sorted(brand.endpoints, key=lambda item: item.priority)
            ],
        }
        for brand in registry.brands
    }
