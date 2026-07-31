from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.release.protocol import canonical_json_bytes

_SCHEMA = "media-rating-state/1"
_SCORE_LIMITS = {
    "imdb_rating": 10.0,
    "douban_rating": 10.0,
    "rotten_tomatoes_rating": 100.0,
    "bangumi_rating": 10.0,
}
_SCORE_METADATA = {
    "imdb_rating": ("imdb_rating_text", "imdb_id"),
    "douban_rating": ("douban_rating_text", "douban_url"),
    "rotten_tomatoes_rating": (
        "rotten_tomatoes_rating_text",
        "rotten_tomatoes_url",
    ),
    "bangumi_rating": (
        "bangumi_rating_text",
        "bangumi_subject_id",
        "bangumi_url",
    ),
}
_IMDB_ID_RE = re.compile(r"^tt[0-9]{5,12}$", re.IGNORECASE)
_INDEPENDENT_METADATA_FIELDS = (
    "imdb_id",
    "douban_url",
    "rotten_tomatoes_url",
    "bangumi_subject_id",
    "bangumi_url",
)
_RATING_FIELDS = tuple(
    dict.fromkeys(
        field
        for score_field, metadata_fields in _SCORE_METADATA.items()
        for field in (score_field, *metadata_fields)
    )
)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "failed to read media rating state JSON",
            {"path": str(path)},
        ) from exc
    if not isinstance(value, dict):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media rating state JSON must be an object",
            {"path": str(path)},
        )
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    temporary.write_bytes(canonical_json_bytes(value))
    temporary.replace(path)


def _valid_score(value: object, maximum: float) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score) or score <= 0 or score > maximum:
        return None
    return score


def _valid_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _trusted_rating_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for field in _INDEPENDENT_METADATA_FIELDS:
        text = _valid_text(item.get(field))
        if text is None:
            continue
        if field == "imdb_id" and not _IMDB_ID_RE.fullmatch(text):
            continue
        if field == "rotten_tomatoes_url" and "the_odyssey_2026" in text.casefold():
            continue
        snapshot[field] = text
    for score_field, maximum in _SCORE_LIMITS.items():
        score = _valid_score(item.get(score_field), maximum)
        if score is None:
            continue
        if score_field == "rotten_tomatoes_rating":
            url = _valid_text(item.get("rotten_tomatoes_url"))
            if url and "the_odyssey_2026" in url.casefold():
                continue
        snapshot[score_field] = score
        text_field = _SCORE_METADATA[score_field][0]
        text = _valid_text(item.get(text_field))
        if text is not None:
            snapshot[text_field] = text
    return snapshot


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA,
        "updated_at": None,
        "items": {},
    }


def load_media_rating_state(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return _empty_state()
    value = _load_json(target)
    if value.get("schema_version") != _SCHEMA or not isinstance(value.get("items"), dict):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media rating state contract mismatch",
            {"path": str(target)},
        )
    return value


def _load_feed(path: Path) -> dict[str, Any]:
    value = _load_json(path)
    if value.get("schema_version") != "media-feed/1" or not isinstance(value.get("items"), list):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media feed contract mismatch for rating state",
            {"path": str(path)},
        )
    return value


def apply_media_rating_state(
    *,
    feed_paths: Iterable[str | Path],
    state_path: str | Path,
) -> dict[str, Any]:
    state = load_media_rating_state(state_path)
    stored_items = state["items"]
    restored_items = 0
    restored_fields = 0
    per_feed: list[dict[str, Any]] = []

    for raw_path in feed_paths:
        path = Path(raw_path)
        feed = _load_feed(path)
        feed_restored_items = 0
        feed_restored_fields = 0
        for raw_item in feed["items"]:
            if not isinstance(raw_item, dict):
                continue
            media_id = _valid_text(raw_item.get("movie_id"))
            if media_id is None:
                continue
            stored = stored_items.get(media_id)
            if not isinstance(stored, dict):
                continue
            stored_kind = _valid_text(stored.get("content_kind"))
            current_kind = _valid_text(raw_item.get("content_kind"))
            if stored_kind and current_kind and stored_kind != current_kind:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "media rating state content kind collision",
                    {
                        "media_id": media_id,
                        "stored_kind": stored_kind,
                        "current_kind": current_kind,
                    },
                )
            ratings = stored.get("ratings")
            if not isinstance(ratings, dict):
                continue
            trusted = _trusted_rating_snapshot(ratings)
            changed = 0
            for field in _RATING_FIELDS:
                if raw_item.get(field) not in {None, ""}:
                    continue
                if field in trusted:
                    raw_item[field] = trusted[field]
                    changed += 1
            if changed:
                feed_restored_items += 1
                feed_restored_fields += changed
        if feed_restored_fields:
            _write_json(path, feed)
        restored_items += feed_restored_items
        restored_fields += feed_restored_fields
        per_feed.append(
            {
                "path": str(path),
                "restored_items": feed_restored_items,
                "restored_fields": feed_restored_fields,
            }
        )

    return {
        "status": "applied",
        "state_path": str(Path(state_path)),
        "stored_item_count": len(stored_items),
        "restored_items": restored_items,
        "restored_fields": restored_fields,
        "feeds": per_feed,
    }


def persist_media_rating_state(
    *,
    feed_paths: Iterable[str | Path],
    state_path: str | Path,
) -> dict[str, Any]:
    target = Path(state_path)
    state = load_media_rating_state(target)
    stored_items = state["items"]
    changed_items = 0
    rating_item_count = 0
    score_counts = {field: 0 for field in _SCORE_LIMITS}

    for raw_path in feed_paths:
        feed = _load_feed(Path(raw_path))
        for raw_item in feed["items"]:
            if not isinstance(raw_item, dict):
                continue
            media_id = _valid_text(raw_item.get("movie_id"))
            if media_id is None:
                continue
            snapshot = _trusted_rating_snapshot(raw_item)
            if not snapshot:
                continue
            rating_item_count += 1
            for score_field in score_counts:
                if score_field in snapshot:
                    score_counts[score_field] += 1
            current = stored_items.get(media_id)
            if not isinstance(current, dict):
                current = {
                    "content_kind": _valid_text(raw_item.get("content_kind")),
                    "title": _valid_text(raw_item.get("title")),
                    "year": raw_item.get("year"),
                    "ratings": {},
                    "updated_at": None,
                }
            stored_kind = _valid_text(current.get("content_kind"))
            item_kind = _valid_text(raw_item.get("content_kind"))
            if stored_kind and item_kind and stored_kind != item_kind:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "media rating state content kind collision",
                    {
                        "media_id": media_id,
                        "stored_kind": stored_kind,
                        "current_kind": item_kind,
                    },
                )
            ratings = current.get("ratings")
            if not isinstance(ratings, dict):
                ratings = {}
            merged = dict(ratings)
            merged.update(snapshot)
            updated = dict(current)
            updated["content_kind"] = item_kind or stored_kind
            updated["title"] = _valid_text(raw_item.get("title")) or current.get("title")
            updated["year"] = raw_item.get("year") if raw_item.get("year") is not None else current.get("year")
            updated["ratings"] = merged
            if updated != current:
                updated["updated_at"] = _utc_now()
                stored_items[media_id] = updated
                changed_items += 1

    state["updated_at"] = _utc_now()
    state["items"] = stored_items
    _write_json(target, state)
    return {
        "status": "written",
        "state_path": str(target),
        "stored_item_count": len(stored_items),
        "rating_item_count": rating_item_count,
        "changed_items": changed_items,
        "score_counts": score_counts,
    }
