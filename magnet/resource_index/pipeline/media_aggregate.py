"""Aggregate independent movie and series feeds into one deduplicated media feed."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.pipeline.latest_crawl import _atomic_write_json
from magnet.resource_index.normalize.text import normalize_whitespace


def _normalized_title(value: object) -> str:
    text = normalize_whitespace(str(value or "")).casefold()
    text = re.sub(r"[\s·•:：,，.。!！?？'\"《》()（）\[\]【】\-_/\\]+", "", text)
    return text


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


_CHINESE_NUMBER = "零〇一二两三四五六七八九十百"


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
    if kind in {"series", "anime", "documentary", "variety"}:
        title = _series_base_title(item.get("series_title") or item.get("title"))
        return "series", title, _integer(item.get("season_number")) or 0
    title = _normalized_title(item.get("title"))
    return "movie", title, _integer(item.get("year")) or 0


def media_identity(item: dict[str, Any]) -> str:
    kind, title, number = _identity_parts(item)
    if kind == "series":
        return f"series:{title}:s{number}"
    return f"movie:{title}:{number}"


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


def _merge_item(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    existing_freshness = (_date_key(existing.get("update_date")), _integer(existing.get("episode_number")) or 0)
    incoming_freshness = (_date_key(incoming.get("update_date")), _integer(incoming.get("episode_number")) or 0)
    preferred = incoming if (
        incoming_freshness > existing_freshness
        or (
            incoming_freshness == existing_freshness
            and _completeness(incoming) > _completeness(existing)
        )
    ) else existing
    secondary = existing if preferred is incoming else incoming
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
    resources = _merge_unique(existing.get("resources") or [], incoming.get("resources") or [])
    resources.sort(key=lambda item: (
        str(item.get("resource_type") or ""),
        str(item.get("provider") or ""),
        str(item.get("display_title") or ""),
        str(item.get("url") or ""),
    ))
    merged["resources"] = resources
    variants = _merge_unique(
        existing.get("source_variants") or [_source_variant(existing)],
        incoming.get("source_variants") or [_source_variant(incoming)],
    )
    variants.sort(key=lambda item: (
        _date_key(item.get("update_date")),
        -int(item.get("rank") or 999999),
    ), reverse=True)
    merged["source_variants"] = variants
    merged["source_count"] = len({item.get("source_id") for item in variants if item.get("source_id")})
    merged["brand_count"] = len({item.get("brand_id") or item.get("source_id") for item in variants})
    merged["recommended"] = bool(existing.get("recommended") or incoming.get("recommended"))
    merged["media_identity"] = media_identity(merged)
    return merged


def aggregate_media_feeds(
    feed_paths: Iterable[str | Path],
    *,
    output_path: str | Path | None = None,
    limit: int = 200,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if limit <= 0:
        raise ResourceIndexError(CONFIG_ERROR, "aggregate media feed limit must be positive", {})
    groups: dict[int, dict[str, Any]] = {}
    identity_index: dict[str, int] = {}
    imdb_index: dict[str, int] = {}
    series_index: dict[str, set[int]] = {}
    next_group_id = 1
    sources: list[dict[str, Any]] = []
    for value in feed_paths:
        path = Path(value)
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "unable to read media source feed",
                {"path": str(path)},
            ) from exc
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
            item = deepcopy(raw_item)
            item["content_kind"] = str(item.get("content_kind") or "movie")
            identity = media_identity(item)
            kind, base_title, season_or_year = _identity_parts(item)
            item["media_identity"] = identity
            item["source_variants"] = [_source_variant(item)]
            item["source_count"] = 1
            item["brand_count"] = 1

            group_id = identity_index.get(identity)
            imdb_id = str(item.get("imdb_id") or "").strip().casefold()
            if group_id is None and imdb_id:
                imdb_group = imdb_index.get(imdb_id)
                if imdb_group is not None:
                    existing = groups[imdb_group]
                    existing_kind, _, existing_number = _identity_parts(existing)
                    if kind == "movie" or (
                        existing_kind == "series"
                        and (
                            season_or_year == 0
                            or existing_number == 0
                            or season_or_year == existing_number
                        )
                    ):
                        group_id = imdb_group
            if group_id is None and kind == "series":
                candidates = series_index.get(base_title, set())
                compatible = [
                    candidate_id
                    for candidate_id in candidates
                    if (
                        season_or_year == 0
                        or _identity_parts(groups[candidate_id])[2] == 0
                        or _identity_parts(groups[candidate_id])[2] == season_or_year
                    )
                ]
                if len(compatible) == 1:
                    group_id = compatible[0]

            if group_id is None:
                group_id = next_group_id
                next_group_id += 1
                groups[group_id] = item
            else:
                groups[group_id] = _merge_item(groups[group_id], item)

            merged = groups[group_id]
            merged_identity = media_identity(merged)
            merged["media_identity"] = merged_identity
            identity_index[identity] = group_id
            identity_index[merged_identity] = group_id
            merged_kind, merged_base, _ = _identity_parts(merged)
            if merged_kind == "series":
                series_index.setdefault(merged_base, set()).add(group_id)
            for candidate in (item, merged):
                candidate_imdb = str(candidate.get("imdb_id") or "").strip().casefold()
                if candidate_imdb:
                    imdb_index[candidate_imdb] = group_id
    items = list(groups.values())
    items.sort(
        key=lambda item: (
            _date_key(item.get("update_date")),
            _integer(item.get("episode_number")) or 0,
            bool(item.get("recommended")),
            _completeness(item),
        ),
        reverse=True,
    )
    items = items[:limit]
    timestamp = generated_at or datetime.now().astimezone()
    payload = {
        "schema_version": "media-feed/1",
        "generated_at": timestamp.isoformat(),
        "sources": sources,
        "items": items,
        "summary": {
            "source_count": len(sources),
            "record_count": len(items),
            "movie_count": sum(1 for item in items if item.get("content_kind", "movie") == "movie"),
            "series_count": sum(1 for item in items if item.get("content_kind") == "series"),
            "multi_source_count": sum(1 for item in items if int(item.get("source_count") or 0) > 1),
            "resource_count": sum(len(item.get("resources") or []) for item in items),
        },
    }
    if output_path is not None:
        _atomic_write_json(Path(output_path), payload)
    return payload
