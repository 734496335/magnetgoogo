"""Aggregate independent movie and series feeds into deterministic media catalogs."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.normalize.media import (
    is_generic_resource_title,
    label_has_anomaly,
    normalize_country_labels,
    normalize_genre_labels,
    normalize_resource,
    normalize_series_item_titles,
)
from magnet.resource_index.normalize.text import normalize_whitespace
from magnet.resource_index.pipeline.latest_crawl import _atomic_write_json

_SERIES_KINDS = {"series", "anime", "documentary", "variety"}
_CHINESE_NUMBER = "零〇一二两三四五六七八九十百"


def _normalized_title(value: object) -> str:
    text = normalize_whitespace(str(value or "")).casefold()
    return re.sub(r"[\s·•:：,，.。!！?？'\"《》()（）\[\]【】\-_/\\]+", "", text)


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _series_base_title(value: object) -> str:
    text = normalize_whitespace(str(value or ""))
    text = re.sub(
        rf"第(?:\d+|[{_CHINESE_NUMBER}]+)(?:(?:至|到|-)第?(?:\d+|[{_CHINESE_NUMBER}]+))?季.*$",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"(?i)\bseason\s*\d+.*$", "", text)
    text = re.sub(r"(?i)\bS\d{1,2}(?:E\d{1,4})?.*$", "", text)
    return _normalized_title(text)


def _identity_parts(item: dict[str, Any]) -> tuple[str, str, int]:
    kind = str(item.get("content_kind") or "movie")
    if kind in _SERIES_KINDS:
        title = _series_base_title(item.get("series_title") or item.get("title"))
        return "series", title, _integer(item.get("season_number")) or 0
    return "movie", _normalized_title(item.get("title")), _integer(item.get("year")) or 0


def media_identity(item: dict[str, Any]) -> str:
    kind, title, number = _identity_parts(item)
    return f"series:{title}:s{number}" if kind == "series" else f"movie:{title}:{number}"


def _date_key(value: object) -> str:
    text = str(value or "")
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return "0001-01-01"


def _completeness(item: dict[str, Any]) -> int:
    scalar_fields = (
        "title",
        "original_title",
        "year",
        "release_date",
        "duration_minutes",
        "imdb_id",
        "douban_rating",
        "rotten_tomatoes_rating",
        "bangumi_rating",
        "cover_source_url",
        "synopsis",
    )
    list_fields = ("countries", "genres", "languages", "directors", "actors", "quality_tags")
    return sum(bool(item.get(field)) for field in scalar_fields) + sum(
        len(item.get(field) or []) for field in list_fields
    )


def _source_variant(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": item.get("source_id"),
        "brand_id": item.get("brand_id"),
        "source_item_key": item.get("source_item_key"),
        "detail_url": item.get("detail_url"),
        "endpoint_origin": item.get("endpoint_origin"),
        "rank": item.get("rank"),
        "update_date": item.get("update_date"),
        "update_status": item.get("update_status"),
    }


def _merge_unique(left: list[Any], right: Iterable[Any]) -> list[Any]:
    output = list(left)
    seen = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in output}
    for item in right:
        marker = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if marker not in seen:
            seen.add(marker)
            output.append(item)
    return output


def _resource_key(resource: dict[str, Any]) -> tuple[str, str, str]:
    info_hash = str(resource.get("info_hash") or "").strip().casefold()
    if info_hash:
        return "magnet", "info_hash", info_hash
    resource_type = str(resource.get("resource_type") or "").strip().casefold()
    provider = str(resource.get("provider") or "").strip().casefold()
    url = str(resource.get("url") or resource.get("resource_url") or "").strip()
    return resource_type, provider, url


def _merge_resources(*collections: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for collection in collections:
        for raw in collection:
            resource = deepcopy(raw)
            key = _resource_key(resource)
            existing = merged.get(key)
            if existing is None:
                merged[key] = resource
                continue
            for field in (
                "url",
                "resource_url",
                "info_hash",
                "display_title",
                "extraction_code",
                "season_number",
                "episode_start",
                "episode_end",
                "episode_label",
                "title_source",
            ):
                if not existing.get(field) and resource.get(field):
                    existing[field] = resource[field]
            existing["quality_tags"] = _merge_unique(
                existing.get("quality_tags") or [],
                resource.get("quality_tags") or [],
            )
    output = list(merged.values())
    output.sort(
        key=lambda item: (
            str(item.get("resource_type") or ""),
            str(item.get("provider") or ""),
            str(item.get("display_title") or ""),
            str(item.get("url") or item.get("resource_url") or ""),
        )
    )
    return output


def _cover_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    url = normalize_whitespace(str(item.get("cover_source_url") or ""))
    if not url:
        return []
    return [
        {
            "url": url,
            "referer": item.get("detail_url"),
            "source_id": item.get("source_id"),
            "source_item_key": item.get("source_item_key"),
        }
    ]


def _quarantine_entry(
    *,
    item: dict[str, Any],
    resource: dict[str, Any],
    reason: str,
    target_season_number: int | None,
    inferred_seasons: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "source_id": item.get("source_id"),
        "brand_id": item.get("brand_id"),
        "source_item_key": item.get("source_item_key"),
        "detail_url": item.get("detail_url"),
        "title": item.get("title"),
        "series_title": item.get("series_title"),
        "target_season_number": target_season_number,
        "inferred_seasons": inferred_seasons or [],
        "resource": deepcopy(resource),
    }


def _partition_series_item(
    item: dict[str, Any],
    *,
    quarantine: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_resources = [
        normalize_resource(resource).resource
        for resource in item.get("resources") or []
        if isinstance(resource, dict)
    ]
    explicit_season = _integer(item.get("season_number"))
    if explicit_season is not None:
        item["season_number"] = explicit_season
        item["title"], item["series_title"] = normalize_series_item_titles(item)
        accepted: list[dict[str, Any]] = []
        for resource in normalized_resources:
            resource_season = _integer(resource.get("season_number"))
            if resource_season == explicit_season:
                accepted.append(resource)
                continue
            reason = "season_unknown" if resource_season is None else "season_mismatch"
            quarantine.append(
                _quarantine_entry(
                    item=item,
                    resource=resource,
                    reason=reason,
                    target_season_number=explicit_season,
                )
            )
        item["resources"] = accepted
        return [item]

    known_seasons = sorted(
        {
            season
            for resource in normalized_resources
            if (season := _integer(resource.get("season_number"))) is not None
        }
    )
    if not known_seasons:
        item["title"], item["series_title"] = normalize_series_item_titles(item)
        item["resources"] = normalized_resources
        return [item]

    output: list[dict[str, Any]] = []
    for season in known_seasons:
        partition = deepcopy(item)
        partition["season_number"] = season
        partition["title"], partition["series_title"] = normalize_series_item_titles(partition)
        partition["resources"] = [
            resource
            for resource in normalized_resources
            if _integer(resource.get("season_number")) == season
        ]
        original_movie_id = normalize_whitespace(str(item.get("movie_id") or ""))
        if original_movie_id:
            partition["source_movie_id"] = original_movie_id
            partition["movie_id"] = f"{original_movie_id}:season:{season}"
        partition["season_partitioned"] = True
        output.append(partition)

    for resource in normalized_resources:
        if _integer(resource.get("season_number")) is None:
            quarantine.append(
                _quarantine_entry(
                    item=item,
                    resource=resource,
                    reason="season_unknown",
                    target_season_number=None,
                    inferred_seasons=known_seasons,
                )
            )
    return output


def _normalize_source_items(
    raw_item: dict[str, Any],
    *,
    quarantine: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    item = deepcopy(raw_item)
    item["content_kind"] = str(item.get("content_kind") or "movie")
    item["countries"] = list(normalize_country_labels(item.get("countries") or []))
    item["genres"] = list(
        normalize_genre_labels(
            item.get("genres") or [],
            fallback_text=str(item.get("listing_title") or ""),
        )
    )
    item["cover_candidates"] = _merge_unique(
        list(item.get("cover_candidates") or []),
        _cover_candidates(item),
    )
    if item["content_kind"] in _SERIES_KINDS:
        return _partition_series_item(item, quarantine=quarantine)
    item["resources"] = [
        normalize_resource(resource).resource
        for resource in item.get("resources") or []
        if isinstance(resource, dict)
    ]
    return [item]


def _enforce_final_season_resources(
    item: dict[str, Any],
    *,
    quarantine: list[dict[str, Any]],
) -> None:
    if _identity_parts(item)[0] != "series":
        return
    target_season = _integer(item.get("season_number"))
    if target_season is None:
        return
    accepted: list[dict[str, Any]] = []
    for resource in item.get("resources") or []:
        resource_season = _integer(resource.get("season_number"))
        if resource_season == target_season:
            accepted.append(resource)
            continue
        quarantine.append(
            _quarantine_entry(
                item=item,
                resource=resource,
                reason="season_unknown" if resource_season is None else "season_mismatch",
                target_season_number=target_season,
            )
        )
    item["resources"] = accepted


def _quarantine_cross_media_duplicate_resources(
    items: list[dict[str, Any]],
    *,
    quarantine: list[dict[str, Any]],
) -> None:
    owners: dict[tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for item in items:
        for resource in item.get("resources") or []:
            owners.setdefault(_resource_key(resource), []).append((item, resource))

    duplicate_keys = {
        key
        for key, entries in owners.items()
        if key[2] and len({media_identity(item) for item, _resource in entries}) > 1
    }
    if not duplicate_keys:
        return

    for item in items:
        accepted: list[dict[str, Any]] = []
        for resource in item.get("resources") or []:
            if _resource_key(resource) not in duplicate_keys:
                accepted.append(resource)
                continue
            quarantine.append(
                _quarantine_entry(
                    item=item,
                    resource=resource,
                    reason="cross_media_duplicate",
                    target_season_number=_integer(item.get("season_number")),
                )
            )
        item["resources"] = accepted


def _quality_report(
    *,
    items: list[dict[str, Any]],
    quarantine: list[dict[str, Any]],
    dropped_zero_resource_count: int,
) -> dict[str, Any]:
    bad_labels: list[dict[str, Any]] = []
    accepted_cross_season: list[dict[str, Any]] = []
    weak_episode_titles: list[dict[str, Any]] = []
    empty_resource_items: list[dict[str, Any]] = []
    for item in items:
        for field in ("genres", "countries"):
            for value in item.get(field) or []:
                if label_has_anomaly(value):
                    bad_labels.append(
                        {
                            "media_identity": item.get("media_identity"),
                            "field": field,
                            "value": value,
                        }
                    )
        resources = item.get("resources") or []
        if not resources:
            empty_resource_items.append(
                {
                    "media_identity": item.get("media_identity"),
                    "title": item.get("title"),
                }
            )
        target_season = _integer(item.get("season_number"))
        for resource in resources:
            resource_season = _integer(resource.get("season_number"))
            if target_season is not None and resource_season != target_season:
                accepted_cross_season.append(
                    {
                        "media_identity": item.get("media_identity"),
                        "target_season_number": target_season,
                        "resource_season_number": resource_season,
                        "url": resource.get("url") or resource.get("resource_url"),
                    }
                )
            if resource.get("episode_label") and is_generic_resource_title(resource.get("display_title")):
                weak_episode_titles.append(
                    {
                        "media_identity": item.get("media_identity"),
                        "display_title": resource.get("display_title"),
                        "episode_label": resource.get("episode_label"),
                    }
                )
    reasons: dict[str, int] = {}
    for entry in quarantine:
        reason = str(entry.get("reason") or "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1
    errors = {
        "bad_label_count": len(bad_labels),
        "accepted_cross_season_count": len(accepted_cross_season),
        "weak_episode_title_count": len(weak_episode_titles),
        "empty_resource_item_count": len(empty_resource_items),
    }
    return {
        "schema_version": "media-quality-report/1",
        "status": "pass" if not any(errors.values()) else "fail",
        "record_count": len(items),
        "resource_count": sum(len(item.get("resources") or []) for item in items),
        "dropped_zero_resource_count": dropped_zero_resource_count,
        "quarantined_resource_count": len(quarantine),
        "quarantine_reason_counts": reasons,
        **errors,
        "examples": {
            "bad_labels": bad_labels[:20],
            "accepted_cross_season": accepted_cross_season[:20],
            "weak_episode_titles": weak_episode_titles[:20],
            "empty_resource_items": empty_resource_items[:20],
        },
    }


def _variant_key(variant: dict[str, Any]) -> tuple[str, str]:
    source_id = str(variant.get("source_id") or "")
    source_key = str(variant.get("source_item_key") or variant.get("detail_url") or "")
    return source_id, source_key


def _merge_variants(*collections: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for collection in collections:
        for raw in collection:
            variant = deepcopy(raw)
            key = _variant_key(variant)
            current = merged.get(key)
            candidate_order = (
                _date_key(variant.get("update_date")),
                -int(variant.get("rank") or 999999),
            )
            current_order = (
                _date_key(current.get("update_date")),
                -int(current.get("rank") or 999999),
            ) if current else None
            if current is None or candidate_order > current_order:
                merged[key] = variant
    output = list(merged.values())
    output.sort(
        key=lambda item: (
            _date_key(item.get("update_date")),
            -int(item.get("rank") or 999999),
            str(item.get("source_id") or ""),
        ),
        reverse=True,
    )
    return output


def _merge_item(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    existing_freshness = (_date_key(existing.get("update_date")), _integer(existing.get("episode_number")) or 0)
    incoming_freshness = (_date_key(incoming.get("update_date")), _integer(incoming.get("episode_number")) or 0)
    incoming_is_preferred = (
        incoming_freshness > existing_freshness
        or (
            incoming_freshness == existing_freshness
            and _completeness(incoming) > _completeness(existing)
        )
    )
    preferred = incoming if incoming_is_preferred else existing
    secondary = existing if incoming_is_preferred else incoming
    merged = deepcopy(preferred)
    for field in (
        "original_title",
        "year",
        "release_date",
        "duration_minutes",
        "imdb_id",
        "douban_rating",
        "douban_rating_text",
        "douban_url",
        "rotten_tomatoes_rating",
        "rotten_tomatoes_rating_text",
        "rotten_tomatoes_url",
        "bangumi_rating",
        "bangumi_rating_text",
        "bangumi_subject_id",
        "bangumi_url",
        "cover_source_url",
        "synopsis",
        "series_title",
        "season_number",
        "episode_number",
        "episode_label",
        "update_status",
    ):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    for field in ("countries", "genres", "languages", "directors", "actors", "quality_tags", "highlight_labels"):
        merged[field] = _merge_unique(merged.get(field) or [], secondary.get(field) or [])
    merged["resources"] = _merge_resources(
        existing.get("resources") or [],
        incoming.get("resources") or [],
    )
    merged["cover_candidates"] = _merge_unique(
        merged.get("cover_candidates") or [],
        secondary.get("cover_candidates") or [],
    )
    variants = _merge_variants(
        existing.get("source_variants") or [_source_variant(existing)],
        incoming.get("source_variants") or [_source_variant(incoming)],
    )
    merged["source_variants"] = variants
    merged["source_count"] = len({item.get("source_id") for item in variants if item.get("source_id")})
    merged["brand_count"] = len(
        {item.get("brand_id") or item.get("source_id") for item in variants if item.get("brand_id") or item.get("source_id")}
    )
    merged["recommended"] = bool(existing.get("recommended") or incoming.get("recommended"))
    merged["media_identity"] = media_identity(merged)
    return merged


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def _deduplicate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    disjoint = _DisjointSet(len(items))
    kinds: list[str] = []
    titles: list[str] = []
    numbers: list[int] = []
    imdb_ids: list[str] = []
    exact_index: dict[tuple[str, str, int], list[int]] = {}
    title_index: dict[tuple[str, str], list[int]] = {}
    imdb_index: dict[tuple[str, str], list[int]] = {}
    known_imdb_index: dict[tuple[str, str, int], list[int]] = {}

    for index, item in enumerate(items):
        kind, title, number = _identity_parts(item)
        imdb_id = str(item.get("imdb_id") or "").strip().casefold()
        kinds.append(kind)
        titles.append(title)
        numbers.append(number)
        imdb_ids.append(imdb_id)
        exact_index.setdefault((kind, title, number), []).append(index)
        title_index.setdefault((kind, title), []).append(index)
        if imdb_id:
            imdb_index.setdefault((kind, imdb_id), []).append(index)
            if number:
                known_imdb_index.setdefault((kind, imdb_id, number), []).append(index)

    # Phase 1: only strong identities. A known season/year never crosses another
    # known number, even through an unknown record that shares a second alias.
    for indices in exact_index.values():
        for index in indices[1:]:
            disjoint.union(indices[0], index)
    for indices in known_imdb_index.values():
        for index in indices[1:]:
            disjoint.union(indices[0], index)

    # Phase 2: connect unknown-number records to each other by title/IMDb, then
    # attach the whole unknown component only when all aliases resolve to one
    # already-known group. Conflicting candidates remain conservative standalone.
    unknown_indices = [index for index, number in enumerate(numbers) if number == 0]
    for index in unknown_indices:
        for candidate in title_index.get((kinds[index], titles[index]), []):
            if numbers[candidate] == 0:
                disjoint.union(index, candidate)
        if imdb_ids[index]:
            for candidate in imdb_index.get((kinds[index], imdb_ids[index]), []):
                if numbers[candidate] == 0:
                    disjoint.union(index, candidate)

    unknown_components: dict[int, list[int]] = {}
    for index in unknown_indices:
        unknown_components.setdefault(disjoint.find(index), []).append(index)
    for members in unknown_components.values():
        known_candidates: set[int] = set()
        for index in members:
            for candidate in title_index.get((kinds[index], titles[index]), []):
                if numbers[candidate] != 0:
                    known_candidates.add(disjoint.find(candidate))
            if imdb_ids[index]:
                for candidate in imdb_index.get((kinds[index], imdb_ids[index]), []):
                    if numbers[candidate] != 0:
                        known_candidates.add(disjoint.find(candidate))
        if len(known_candidates) == 1:
            disjoint.union(members[0], next(iter(known_candidates)))

    groups: dict[int, list[dict[str, Any]]] = {}
    for index, item in enumerate(items):
        groups.setdefault(disjoint.find(index), []).append(item)

    output: list[dict[str, Any]] = []
    for members in groups.values():
        members.sort(
            key=lambda item: (
                str(item.get("source_id") or ""),
                str(item.get("source_item_key") or ""),
                str(item.get("detail_url") or ""),
            )
        )
        merged = members[0]
        for member in members[1:]:
            merged = _merge_item(merged, member)
        merged["resources"] = _merge_resources(merged.get("resources") or [])
        merged["source_variants"] = _merge_variants(
            merged.get("source_variants") or [_source_variant(merged)]
        )
        merged["source_count"] = len(
            {item.get("source_id") for item in merged["source_variants"] if item.get("source_id")}
        )
        merged["brand_count"] = len(
            {
                item.get("brand_id") or item.get("source_id")
                for item in merged["source_variants"]
                if item.get("brand_id") or item.get("source_id")
            }
        )
        merged["media_identity"] = media_identity(merged)
        output.append(merged)
    return output


def _item_sort_key(item: dict[str, Any]) -> tuple[str, int, bool, int, str]:
    return (
        _date_key(item.get("update_date")),
        _integer(item.get("episode_number")) or 0,
        bool(item.get("recommended")),
        _completeness(item),
        media_identity(item),
    )


def _summary(
    *,
    items: list[dict[str, Any]],
    source_count: int,
    available_movie_count: int,
    available_series_count: int,
    movie_limit: int | None,
    series_limit: int | None,
) -> dict[str, Any]:
    return {
        "source_count": source_count,
        "record_count": len(items),
        "movie_count": sum(1 for item in items if _identity_parts(item)[0] == "movie"),
        "series_count": sum(1 for item in items if _identity_parts(item)[0] == "series"),
        "available_movie_count": available_movie_count,
        "available_series_count": available_series_count,
        "requested_movie_count": movie_limit,
        "requested_series_count": series_limit,
        "multi_source_count": sum(1 for item in items if int(item.get("source_count") or 0) > 1),
        "resource_count": sum(len(item.get("resources") or []) for item in items),
    }


def _kind_payload(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    items = [item for item in payload["items"] if _identity_parts(item)[0] == kind]
    used_sources = {
        variant.get("source_id")
        for item in items
        for variant in item.get("source_variants") or []
        if variant.get("source_id")
    }
    sources = [source for source in payload["sources"] if source.get("source_id") in used_sources]
    return {
        "schema_version": payload["schema_version"],
        "generated_at": payload["generated_at"],
        "content_kind_filter": kind,
        "sources": sources,
        "items": items,
        "summary": _summary(
            items=items,
            source_count=len(sources),
            available_movie_count=payload["summary"]["available_movie_count"],
            available_series_count=payload["summary"]["available_series_count"],
            movie_limit=payload["summary"]["requested_movie_count"] if kind == "movie" else None,
            series_limit=payload["summary"]["requested_series_count"] if kind == "series" else None,
        ),
    }


def aggregate_media_feeds(
    feed_paths: Iterable[str | Path],
    *,
    output_path: str | Path | None = None,
    movie_output_path: str | Path | None = None,
    series_output_path: str | Path | None = None,
    quarantine_output_path: str | Path | None = None,
    quality_output_path: str | Path | None = None,
    limit: int = 200,
    movie_limit: int | None = None,
    series_limit: int | None = None,
    strict_kind_limits: bool = False,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if limit <= 0:
        raise ResourceIndexError(CONFIG_ERROR, "aggregate media feed limit must be positive", {})
    for label, value in (("movie_limit", movie_limit), ("series_limit", series_limit)):
        if value is not None and value <= 0:
            raise ResourceIndexError(CONFIG_ERROR, f"{label} must be positive", {label: value})

    raw_items: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for value in feed_paths:
        path = Path(value)
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResourceIndexError(CONFIG_ERROR, "unable to read media source feed", {"path": str(path)}) from exc
        if payload.get("schema_version") != "movie-feed/1" or not isinstance(payload.get("items"), list):
            raise ResourceIndexError(
                CONFIG_ERROR,
                "unsupported media source feed schema",
                {"path": str(path), "schema_version": payload.get("schema_version")},
            )
        sources.append(
            {
                "source_id": payload.get("source_id"),
                "path": str(path.resolve()),
                "record_count": len(payload["items"]),
                "snapshot_captured_at": payload.get("snapshot_captured_at"),
            }
        )
        for raw_item in payload["items"]:
            if not isinstance(raw_item, dict):
                raise ResourceIndexError(CONFIG_ERROR, "media feed item must be an object", {"path": str(path)})
            for item in _normalize_source_items(raw_item, quarantine=quarantine):
                item["source_variants"] = [_source_variant(item)]
                item["source_count"] = 1
                item["brand_count"] = 1
                item["media_identity"] = media_identity(item)
                raw_items.append(item)

    deduplicated = _deduplicate_items(raw_items)
    for item in deduplicated:
        _enforce_final_season_resources(item, quarantine=quarantine)
    _quarantine_cross_media_duplicate_resources(deduplicated, quarantine=quarantine)
    before_resource_gate = len(deduplicated)
    deduplicated = [item for item in deduplicated if item.get("resources")]
    dropped_zero_resource_count = before_resource_gate - len(deduplicated)
    deduplicated.sort(key=_item_sort_key, reverse=True)
    movie_items = [item for item in deduplicated if _identity_parts(item)[0] == "movie"]
    series_items = [item for item in deduplicated if _identity_parts(item)[0] == "series"]
    available_movie_count = len(movie_items)
    available_series_count = len(series_items)

    if strict_kind_limits:
        shortages = {}
        if movie_limit is not None and available_movie_count < movie_limit:
            shortages["movie"] = {"requested": movie_limit, "available": available_movie_count}
        if series_limit is not None and available_series_count < series_limit:
            shortages["series"] = {"requested": series_limit, "available": available_series_count}
        if shortages:
            raise ResourceIndexError(CONFIG_ERROR, "media feed does not satisfy strict kind limits", shortages)

    if movie_limit is not None or series_limit is not None:
        selected = movie_items[: movie_limit or len(movie_items)] + series_items[: series_limit or len(series_items)]
        selected.sort(key=_item_sort_key, reverse=True)
    else:
        selected = deduplicated[:limit]

    quality = _quality_report(
        items=selected,
        quarantine=quarantine,
        dropped_zero_resource_count=dropped_zero_resource_count,
    )
    if quality["status"] != "pass":
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media feed quality gate failed",
            {
                key: quality[key]
                for key in (
                    "bad_label_count",
                    "accepted_cross_season_count",
                    "weak_episode_title_count",
                    "empty_resource_item_count",
                )
            },
        )

    timestamp = generated_at or datetime.now().astimezone()
    payload = {
        "schema_version": "media-feed/1",
        "generated_at": timestamp.isoformat(),
        "sources": sources,
        "items": selected,
        "summary": _summary(
            items=selected,
            source_count=len(sources),
            available_movie_count=available_movie_count,
            available_series_count=available_series_count,
            movie_limit=movie_limit,
            series_limit=series_limit,
        ),
        "quality": quality,
    }
    payload["summary"].update(
        {
            "dropped_zero_resource_count": dropped_zero_resource_count,
            "quarantined_resource_count": len(quarantine),
            "quarantine_reason_counts": quality["quarantine_reason_counts"],
        }
    )
    quarantine_payload = {
        "schema_version": "media-resource-quarantine/1",
        "generated_at": timestamp.isoformat(),
        "record_count": len(quarantine),
        "reason_counts": quality["quarantine_reason_counts"],
        "items": quarantine,
    }
    if output_path is not None:
        _atomic_write_json(Path(output_path), payload)
    if movie_output_path is not None:
        _atomic_write_json(Path(movie_output_path), _kind_payload(payload, "movie"))
    if series_output_path is not None:
        _atomic_write_json(Path(series_output_path), _kind_payload(payload, "series"))
    if quarantine_output_path is not None:
        _atomic_write_json(Path(quarantine_output_path), quarantine_payload)
    if quality_output_path is not None:
        _atomic_write_json(Path(quality_output_path), quality)
    return payload
