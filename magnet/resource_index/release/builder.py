"""Build and verify an immutable local media release staging tree."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping

from magnet.resource_index.errors import VALIDATION_ERROR, ResourceIndexError
from magnet.resource_index.release.protocol import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    sign_document,
    verify_document,
)

MEDIA_CURRENT_SCHEMA = "media-current/1"
MEDIA_MANIFEST_SCHEMA = "media-manifest/1"
CATALOG_SCHEMA = "media-catalog/1"
DETAIL_SCHEMA = "media-detail/1"
RESOURCE_SCHEMA = "media-resources/1"

_DIRTY_TEXT = re.compile(r"<[^>]+>|&(?:lt|gt|amp);|^\s*:", re.IGNORECASE)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
_SERIES_IDENTITY_HINT = re.compile(
    r"(?:S\d{1,2}\s*E\d{1,3}|(?:^|[^0-9])E\d{1,3}(?:[^0-9]|$)|"
    r"^\D{0,8}\d{1,3}(?:\s*[-~\u81f3]\s*\d{1,3})?(?:\.|\s|\u96c6|$)|"
    r"\u7b2c\s*\d{1,3}\s*\u96c6|\u5168\s*(?:\u96c6|\u5b63)|"
    r"complete\s+season|season\s+pack)",
    re.IGNORECASE,
)
_COUNTRY_CHANNELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("series_us", ("美国", "usa", "united states")),
    ("series_uk", ("英国", "uk", "united kingdom")),
    ("series_kr", ("韩国", "south korea", "korea")),
    ("series_jp", ("日本", "japan")),
    ("series_cn", ("中国", "中国大陆", "大陆", "香港", "台湾", "china")),
)


@dataclass(frozen=True)
class MediaReleaseConfig:
    movie_feed_path: Path
    series_feed_path: Path
    movie_cover_bundle: Path
    series_cover_bundle: Path
    output_dir: Path
    private_key_path: Path
    public_key_path: Path
    pointer_revision: int = 1
    min_app_version: str = "0.2.1"
    page_size: int = 50
    min_movies: int = 100
    min_series: int = 100
    max_object_bytes: int = 512 * 1024
    previous_manifest_path: Path | None = None
    allow_regression_reason: str | None = None


@dataclass(frozen=True)
class MediaReleaseBuildResult:
    release_id: str
    release_dir: str
    current_path: str
    manifest_path: str
    manifest_sha256: str
    object_count: int
    reused: bool
    release_reused: bool
    pointer_reused: bool
    counts: dict[str, int]
    quality: dict[str, Any]


def _fail(message: str, **context: Any) -> None:
    raise ResourceIndexError(VALIDATION_ERROR, message, context)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("failed to read media release JSON input", path=str(path), error=str(exc))
    if not isinstance(data, dict):
        _fail("media release JSON input must be an object", path=str(path))
    return data


def _parse_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _fail("timestamp is missing", label=label, value=value)
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        _fail("timestamp is invalid", label=label, value=value, error=str(exc))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _content_watermark(items: Iterable[Mapping[str, Any]]) -> datetime:
    """Derive a stable timestamp from business data, not crawler execution time."""

    candidates: list[datetime] = []
    for item in items:
        for field in ("update_date", "release_date"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            normalized = value.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            candidates.append(parsed.astimezone(timezone.utc).replace(microsecond=0))
    if candidates:
        return max(candidates)
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _candidate_cover_urls(item: Mapping[str, Any]) -> Iterable[str]:
    primary = item.get("cover_source_url")
    if isinstance(primary, str) and primary:
        yield primary
    candidates = item.get("cover_candidates") or []
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                yield candidate
            elif isinstance(candidate, Mapping):
                for key in ("url", "source_url"):
                    value = candidate.get(key)
                    if isinstance(value, str) and value:
                        yield value


def _load_cover_index(bundle: Path) -> dict[str, dict[str, Any]]:
    manifest_path = bundle / "cover_manifest.json"
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != "media-cover-manifest/1":
        _fail(
            "unsupported cover manifest schema",
            path=str(manifest_path),
            schema_version=manifest.get("schema_version"),
        )
    assets = manifest.get("assets")
    if not isinstance(assets, dict):
        _fail("cover manifest assets must be an object", path=str(manifest_path))

    result: dict[str, dict[str, Any]] = {}
    for source_url, raw in assets.items():
        if not isinstance(source_url, str) or not isinstance(raw, dict):
            _fail("cover manifest asset entry is invalid", path=str(manifest_path))
        relative_path = raw.get("path")
        expected_hash = raw.get("content_hash")
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            _fail("cover manifest asset lacks path or content_hash", source_url=source_url)
        asset_path = (bundle / relative_path).resolve()
        try:
            asset_path.relative_to(bundle.resolve())
        except ValueError:
            _fail("cover manifest path escapes its bundle", path=str(asset_path))
        if not asset_path.is_file():
            _fail("cover asset is missing", path=str(asset_path), source_url=source_url)
        actual_hash = sha256_file(asset_path)
        if actual_hash != expected_hash:
            _fail(
                "cover asset hash mismatch",
                path=str(asset_path),
                expected=expected_hash,
                actual=actual_hash,
            )
        result[source_url] = {**raw, "asset_path": asset_path}
    return result


def _media_id(item: Mapping[str, Any]) -> str:
    value = item.get("movie_id") or item.get("media_id")
    if not isinstance(value, str) or not value:
        _fail("media item lacks a stable media_id", title=item.get("title"))
    return value


def _validate_feed(feed: Mapping[str, Any], *, expected_kind: str, minimum: int) -> list[dict[str, Any]]:
    if feed.get("schema_version") != "media-feed/1":
        _fail(
            "unsupported media feed schema",
            expected="media-feed/1",
            actual=feed.get("schema_version"),
        )
    items = feed.get("items")
    if not isinstance(items, list):
        _fail("media feed items must be a list", expected_kind=expected_kind)
    if len(items) < minimum:
        _fail(
            "media feed is below the release minimum",
            expected_kind=expected_kind,
            minimum=minimum,
            actual=len(items),
        )
    validated: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            _fail("media feed item must be an object", expected_kind=expected_kind)
        if raw.get("content_kind") != expected_kind:
            _fail(
                "media feed item has the wrong content_kind",
                media_id=raw.get("movie_id"),
                expected=expected_kind,
                actual=raw.get("content_kind"),
            )
        validated.append(raw)
    return validated


def _series_resource_identity_state(resource: Mapping[str, Any]) -> str:
    resource_kind = resource.get("resource_type") or resource.get("provider")
    if resource_kind != "magnet":
        return "collection"
    if any(
        resource.get(key) not in (None, "")
        for key in ("season_number", "episode_start", "episode_end", "episode_label")
    ):
        return "structured"
    title = str(resource.get("display_title") or "")
    if _SERIES_IDENTITY_HINT.search(title):
        return "title_inferred"
    return "unknown"


def _quality_gate(movie_items: list[dict[str, Any]], series_items: list[dict[str, Any]]) -> dict[str, Any]:
    all_items = movie_items + series_items
    ids = [_media_id(item) for item in all_items]
    duplicate_ids = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        _fail("duplicate media_id values block release", duplicate_media_ids=duplicate_ids[:20])

    seen_resources: dict[str, str] = {}
    resource_count = 0
    duplicate_resources: list[dict[str, str]] = []
    malformed_values: list[dict[str, str]] = []
    cross_season: list[dict[str, Any]] = []
    unknown_series_resources = 0
    title_inferred_series_resources = 0
    collection_series_resources = 0

    for item in all_items:
        media_id = _media_id(item)
        for field in ("countries", "genres"):
            values = item.get(field) or []
            if not isinstance(values, list):
                _fail("media list field must be a list", media_id=media_id, field=field)
            for value in values:
                if not isinstance(value, str) or _DIRTY_TEXT.search(value):
                    malformed_values.append({"media_id": media_id, "field": field, "value": str(value)})

        item_season = item.get("season_number") if item.get("content_kind") == "series" else None
        resources = item.get("resources") or []
        if not isinstance(resources, list):
            _fail("media resources must be a list", media_id=media_id)
        for resource in resources:
            if not isinstance(resource, dict):
                _fail("media resource must be an object", media_id=media_id)
            resource_count += 1
            key_value = resource.get("info_hash") or resource.get("url")
            if not isinstance(key_value, str) or not key_value:
                _fail("media resource lacks info_hash and url", media_id=media_id)
            resource_key = key_value.lower()
            previous_media = seen_resources.get(resource_key)
            if previous_media is not None:
                duplicate_resources.append(
                    {"resource_key": resource_key, "first_media_id": previous_media, "media_id": media_id}
                )
            else:
                seen_resources[resource_key] = media_id

            if item.get("content_kind") == "series":
                resource_season = resource.get("season_number")
                if item_season is not None and resource_season is not None and resource_season != item_season:
                    cross_season.append(
                        {
                            "media_id": media_id,
                            "item_season": item_season,
                            "resource_season": resource_season,
                        }
                    )
                identity_state = _series_resource_identity_state(resource)
                if identity_state == "unknown":
                    unknown_series_resources += 1
                elif identity_state == "title_inferred":
                    title_inferred_series_resources += 1
                elif identity_state == "collection":
                    collection_series_resources += 1

    if duplicate_resources:
        _fail("duplicate info-hash or resource URL blocks release", duplicates=duplicate_resources[:20])
    if malformed_values:
        _fail("malformed country or genre values block release", values=malformed_values[:20])
    if cross_season:
        _fail("cross-season resources block release", resources=cross_season[:20])

    return {
        "media_id_unique": True,
        "resource_identity_unique": True,
        "malformed_country_genre_values": 0,
        "cross_season_resources": 0,
        "unknown_series_resources": unknown_series_resources,
        "title_inferred_series_resources": title_inferred_series_resources,
        "collection_series_resources": collection_series_resources,
        "resource_count": resource_count,
    }


def _check_regression(
    previous_manifest_path: Path | None,
    *,
    movie_count: int,
    series_count: int,
    resource_count: int,
    cover_count: int,
    unknown_series_resources: int,
    allow_reason: str | None,
    public_key_path: Path,
) -> dict[str, Any]:
    if previous_manifest_path is None:
        return {"compared_to_previous": False, "override_reason": allow_reason}
    previous = _load_json(previous_manifest_path)
    if previous.get("schema_version") != MEDIA_MANIFEST_SCHEMA:
        _fail(
            "previous manifest has an unsupported schema",
            path=str(previous_manifest_path),
            schema_version=previous.get("schema_version"),
        )
    verify_document(previous, public_key_path)
    counts = previous.get("counts") or {}
    if not isinstance(counts, dict):
        _fail("previous manifest counts are invalid", path=str(previous_manifest_path))

    regressions: dict[str, dict[str, int]] = {}
    checks = {
        "movie": (int(counts.get("movie") or 0), movie_count, 0.20),
        "series": (int(counts.get("series") or 0), series_count, 0.20),
        "resources": (int(counts.get("resources") or 0), resource_count, 0.30),
        "covers": (int(counts.get("covers") or 0), cover_count, 0.0),
    }
    for name, (old, new, allowed_drop) in checks.items():
        if old <= 0:
            continue
        minimum = int(old * (1.0 - allowed_drop))
        if new < minimum:
            regressions[name] = {"previous": old, "current": new, "minimum": minimum}

    previous_quality = previous.get("quality") or {}
    if isinstance(previous_quality, dict) and "unknown_series_resources" in previous_quality:
        old_unknown = int(previous_quality.get("unknown_series_resources") or 0)
        if unknown_series_resources > old_unknown:
            regressions["unknown_series_resources"] = {
                "previous": old_unknown,
                "current": unknown_series_resources,
                "maximum": old_unknown,
            }
    if regressions and not allow_reason:
        _fail(
            "media release regression gate failed; use an explicit override reason for an intentional change",
            regressions=regressions,
        )
    return {
        "compared_to_previous": True,
        "regressions": regressions,
        "override_reason": allow_reason,
    }


def _series_channel(item: Mapping[str, Any]) -> str:
    countries = {str(value).strip().lower() for value in (item.get("countries") or [])}
    for channel, aliases in _COUNTRY_CHANNELS:
        if any(alias.lower() in countries for alias in aliases):
            return channel
    return "series_other"


def _copy_cover(
    item: Mapping[str, Any],
    cover_index: Mapping[str, Mapping[str, Any]],
    stage_root: Path,
    cover_refs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    asset: Mapping[str, Any] | None = None
    source_url: str | None = None
    for candidate in _candidate_cover_urls(item):
        selected = cover_index.get(candidate)
        if selected is not None:
            asset = selected
            source_url = candidate
            break
    if asset is None:
        _fail("media item has no verified local cover", media_id=_media_id(item), title=item.get("title"))

    content_hash = str(asset["content_hash"])
    existing_ref = cover_refs.get(content_hash)
    if existing_ref is not None:
        return {**existing_ref, "source_url": source_url}

    source_path = Path(asset["asset_path"])
    suffix = source_path.suffix.lower()
    if not suffix:
        suffix = mimetypes.guess_extension(str(asset.get("mime_type") or "")) or ".bin"
    relative_path = f"/v1/covers/{content_hash}{suffix}"
    target = stage_root / relative_path.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(source_path, target)
    actual_hash = sha256_file(target)
    if actual_hash != content_hash:
        _fail("staged cover hash mismatch", path=str(target), expected=content_hash, actual=actual_hash)
    ref = {
        "hash": content_hash,
        "size": target.stat().st_size,
        "path": relative_path,
        "mime_type": asset.get("mime_type") or mimetypes.guess_type(target.name)[0],
    }
    cover_refs[content_hash] = ref
    return {**ref, "source_url": source_url}


def _write_object(stage_root: Path, category: str, document: Mapping[str, Any], max_bytes: int) -> dict[str, Any]:
    payload = canonical_json_bytes(document)
    if len(payload) > max_bytes:
        _fail(
            "media object exceeds the configured maximum; split or paginate it",
            category=category,
            size=len(payload),
            maximum=max_bytes,
        )
    content_hash = sha256_bytes(payload)
    relative_path = f"/v1/objects/{category}/{content_hash}.json"
    target = stage_root / relative_path.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != payload:
        _fail("content-addressed object collision", path=str(target), hash=content_hash)
    target.write_bytes(payload)
    return {"hash": content_hash, "size": len(payload), "path": relative_path}


def _resource_document(item: Mapping[str, Any]) -> dict[str, Any]:
    media_id = _media_id(item)
    allowed = (
        "display_title",
        "episode_end",
        "episode_label",
        "episode_start",
        "extraction_code",
        "info_hash",
        "provider",
        "quality_tags",
        "resource_type",
        "season_number",
        "title_source",
        "url",
    )
    resources = []
    for raw in item.get("resources") or []:
        resources.append({key: raw.get(key) for key in allowed if raw.get(key) is not None})
    return {
        "schema_version": RESOURCE_SCHEMA,
        "media_id": media_id,
        "items": resources,
    }


def _detail_document(item: Mapping[str, Any], resource_ref: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "title",
        "original_title",
        "year",
        "release_date",
        "duration_minutes",
        "countries",
        "genres",
        "languages",
        "directors",
        "actors",
        "imdb_id",
        "imdb_rating",
        "imdb_rating_text",
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
        "synopsis",
        "season_number",
        "episode_number",
        "episode_label",
        "update_status",
    )
    return {
        "schema_version": DETAIL_SCHEMA,
        "media_id": _media_id(item),
        "content_kind": item.get("content_kind"),
        **{key: item.get(key) for key in allowed if item.get(key) is not None},
        "resource_object": dict(resource_ref),
    }


def _card_document(
    item: Mapping[str, Any],
    detail_ref: Mapping[str, Any],
    cover_ref: Mapping[str, Any],
) -> dict[str, Any]:
    resources = item.get("resources") or []
    allowed = (
        "title",
        "original_title",
        "year",
        "countries",
        "genres",
        "douban_rating",
        "imdb_rating",
        "rotten_tomatoes_rating",
        "bangumi_rating",
        "update_status",
        "season_number",
        "episode_number",
        "episode_label",
        "quality_tags",
        "recommended",
        "highlight_labels",
        "update_date",
    )
    return {
        "media_id": _media_id(item),
        "content_kind": item.get("content_kind"),
        **{key: item.get(key) for key in allowed if item.get(key) is not None},
        "resource_count": len(resources),
        "cover": {key: cover_ref[key] for key in ("hash", "size", "path", "mime_type")},
        "detail_object": dict(detail_ref),
    }


def _catalog_object(
    stage_root: Path,
    *,
    channel: str,
    role: str,
    cards: list[dict[str, Any]],
    max_bytes: int,
    page: int | None = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA,
        "channel": channel,
        "role": role,
        "count": len(cards),
        "items": cards,
    }
    if page is not None:
        document["page"] = page
    ref = _write_object(stage_root, "catalog", document, max_bytes)
    return {**ref, "count": len(cards), **({"page": page} if page is not None else {})}


def _acquire_release_lock(path: Path) -> BinaryIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        _fail("another media release build is already running", path=str(path), error=str(exc))
    return handle


def _release_release_lock(handle: BinaryIO) -> None:
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _safe_release_path(release_dir: Path, manifest_path: str) -> Path:
    if not manifest_path.startswith("/v1/") or ".." in Path(manifest_path).parts:
        _fail("manifest contains an unsafe object path", path=manifest_path)
    resolved = (release_dir / manifest_path.lstrip("/")).resolve()
    try:
        resolved.relative_to(release_dir.resolve())
    except ValueError:
        _fail("manifest object path escapes the release tree", path=manifest_path)
    return resolved


def _validate_current_document(current: Mapping[str, Any]) -> None:
    release_id = current.get("release_id")
    revision = current.get("pointer_revision")
    manifest_path = current.get("manifest_path")
    manifest_hash = current.get("manifest_sha256")
    min_app_version = current.get("min_app_version")
    release_gate = current.get("release_gate")
    if not isinstance(release_id, str) or not _RELEASE_ID_RE.fullmatch(release_id):
        _fail("current.json release_id is invalid", release_id=release_id)
    if type(revision) is not int or revision < 1:
        _fail("current.json pointer_revision is invalid", pointer_revision=revision)
    expected_manifest_path = f"/v1/releases/{release_id}/manifest.json"
    if manifest_path != expected_manifest_path:
        _fail(
            "current.json manifest_path does not match release_id",
            expected=expected_manifest_path,
            actual=manifest_path,
        )
    if not isinstance(manifest_hash, str) or not _SHA256_RE.fullmatch(manifest_hash):
        _fail("current.json manifest_sha256 is invalid", manifest_sha256=manifest_hash)
    if not isinstance(min_app_version, str) or not min_app_version.strip():
        _fail("current.json min_app_version is invalid")
    if release_gate is not None and not isinstance(release_gate, Mapping):
        _fail("current.json release_gate must be an object")
    _parse_timestamp(current.get("published_at"), label="current.published_at")


def _validate_manifest_identity(manifest: Mapping[str, Any]) -> None:
    release_id = manifest.get("release_id")
    if not isinstance(release_id, str) or not _RELEASE_ID_RE.fullmatch(release_id):
        _fail("manifest release_id is invalid", release_id=release_id)
    generated_at = _parse_timestamp(manifest.get("generated_at"), label="manifest.generated_at")
    content = dict(manifest)
    content.pop("release_id", None)
    content.pop("signature_key_id", None)
    content.pop("signature", None)
    release_hash = sha256_bytes(canonical_json_bytes(content))
    expected_release_id = f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}-{release_hash[:8]}"
    if release_id != expected_release_id:
        _fail(
            "manifest release_id does not match its immutable content",
            expected=expected_release_id,
            actual=release_id,
        )


def _manifest_reference_closure(manifest: Mapping[str, Any]) -> dict[str, Any]:
    references: dict[str, tuple[str, int]] = {}
    detail_paths: dict[str, str] = {}
    resource_paths: dict[str, str] = {}
    detail_refs_by_id: dict[str, tuple[str, str, int]] = {}
    resource_refs_by_id: dict[str, tuple[str, str, int]] = {}
    resource_encrypted_by_id: dict[str, bool] = {}
    cover_refs_by_hash: dict[str, tuple[str, str, int]] = {}
    catalog_expectations: dict[str, tuple[str, str]] = {}
    catalog_paths: set[str] = set()

    def add_reference(raw: Any, *, label: str) -> str:
        if not isinstance(raw, Mapping):
            _fail("manifest reference must be an object", label=label)
        path_value = raw.get("path")
        expected_hash = raw.get("hash")
        expected_size = raw.get("size")
        if (
            not isinstance(path_value, str)
            or not isinstance(expected_hash, str)
            or not _SHA256_RE.fullmatch(expected_hash)
            or type(expected_size) is not int
            or expected_size < 0
        ):
            _fail("manifest reference is incomplete or invalid", label=label, reference=dict(raw))
        previous = references.get(path_value)
        identity = (expected_hash, expected_size)
        if previous is not None and previous != identity:
            _fail(
                "manifest path is assigned conflicting object identities",
                path=path_value,
                first=previous,
                second=identity,
            )
        references[path_value] = identity
        return path_value

    channels = manifest.get("channels")
    if not isinstance(channels, Mapping) or not channels:
        _fail("manifest channels must be a non-empty object")
    for channel, entry in channels.items():
        if not isinstance(channel, str) or not isinstance(entry, Mapping):
            _fail("manifest channel entry is invalid", channel=str(channel))
        for role in ("featured", "updating"):
            if entry.get(role) is not None:
                path_value = add_reference(entry[role], label=f"channels.{channel}.{role}")
                expectation = (channel, role)
                if path_value in catalog_expectations and catalog_expectations[path_value] != expectation:
                    _fail("catalog object is assigned conflicting channel roles", path=path_value)
                catalog_expectations[path_value] = expectation
                catalog_paths.add(path_value)
        pages = entry.get("latest_pages")
        if not isinstance(pages, list) or not pages:
            _fail("manifest channel must contain at least one latest page", channel=channel)
        for index, page in enumerate(pages):
            path_value = add_reference(page, label=f"channels.{channel}.latest_pages[{index}]")
            expectation = (channel, "latest")
            if path_value in catalog_expectations and catalog_expectations[path_value] != expectation:
                _fail("catalog object is assigned conflicting channel roles", path=path_value)
            catalog_expectations[path_value] = expectation
            catalog_paths.add(path_value)

    details = manifest.get("details")
    resources = manifest.get("resources")
    covers = manifest.get("covers")
    if not isinstance(details, Mapping) or not isinstance(resources, Mapping) or not isinstance(covers, Mapping):
        _fail("manifest details, resources and covers must be objects")
    if set(details) != set(resources):
        _fail("manifest detail and resource media_id sets differ")

    for media_id, ref in details.items():
        if not isinstance(media_id, str) or not media_id:
            _fail("manifest detail media_id is invalid", media_id=str(media_id))
        path_value = add_reference(ref, label=f"details.{media_id}")
        detail_paths[path_value] = media_id
        detail_refs_by_id[media_id] = (path_value, *references[path_value])
    for media_id, ref in resources.items():
        if not isinstance(media_id, str) or not media_id:
            _fail("manifest resource media_id is invalid", media_id=str(media_id))
        if not isinstance(ref, Mapping) or type(ref.get("encrypted")) is not bool:
            _fail("manifest resource reference must declare encrypted=true/false", media_id=media_id)
        path_value = add_reference(ref, label=f"resources.{media_id}")
        resource_paths[path_value] = media_id
        resource_refs_by_id[media_id] = (path_value, *references[path_value])
        resource_encrypted_by_id[media_id] = bool(ref.get("encrypted"))
    for cover_hash, ref in covers.items():
        if not isinstance(cover_hash, str) or not _SHA256_RE.fullmatch(cover_hash):
            _fail("manifest cover key is not a SHA-256 hash", cover_hash=str(cover_hash))
        path_value = add_reference(ref, label=f"covers.{cover_hash}")
        if references[path_value][0] != cover_hash:
            _fail("manifest cover key and object hash differ", cover_hash=cover_hash, path=path_value)
        cover_refs_by_hash[cover_hash] = (path_value, *references[path_value])

    counts = manifest.get("counts")
    if not isinstance(counts, Mapping):
        _fail("manifest counts must be an object")
    required_counts = ("movie", "series", "resources", "covers", "details", "catalog_objects")
    normalized_counts: dict[str, int] = {}
    for name in required_counts:
        value = counts.get(name)
        if type(value) is not int or value < 0:
            _fail("manifest count is missing or invalid", count=name, value=value)
        normalized_counts[name] = value
    if normalized_counts["movie"] + normalized_counts["series"] != len(details):
        _fail("manifest media counts do not match detail objects")
    if normalized_counts["details"] != len(details):
        _fail("manifest detail count does not match detail references")
    if normalized_counts["covers"] != len(covers):
        _fail("manifest cover count does not match cover references")
    if normalized_counts["catalog_objects"] != len(catalog_paths):
        _fail("manifest catalog count does not match catalog references")

    objects = manifest.get("objects")
    if not isinstance(objects, list):
        _fail("manifest objects must be a list")
    object_registry: dict[str, tuple[str, int]] = {}
    for index, ref in enumerate(objects):
        path_value = add_reference(ref, label=f"objects[{index}]")
        identity = references[path_value]
        if path_value in object_registry:
            _fail("manifest objects contains a duplicate path", path=path_value)
        object_registry[path_value] = identity
    nested_paths = set(detail_paths) | set(resource_paths) | catalog_paths | {
        str(ref.get("path")) for ref in covers.values() if isinstance(ref, Mapping)
    }
    if set(object_registry) != nested_paths:
        _fail(
            "manifest object registry does not exactly match nested references",
            missing=sorted(nested_paths - set(object_registry)),
            unreferenced=sorted(set(object_registry) - nested_paths),
        )

    return {
        "object_registry": object_registry,
        "detail_paths": detail_paths,
        "resource_paths": resource_paths,
        "detail_refs_by_id": detail_refs_by_id,
        "resource_refs_by_id": resource_refs_by_id,
        "resource_encrypted_by_id": resource_encrypted_by_id,
        "cover_refs_by_hash": cover_refs_by_hash,
        "catalog_expectations": catalog_expectations,
        "catalog_paths": catalog_paths,
        "expected_media_ids": set(details),
        "counts": normalized_counts,
    }


def verify_media_release(
    release_dir: str | Path,
    public_key_path: str | Path,
    current_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(release_dir)
    selected_current = Path(current_path) if current_path is not None else root / "v1" / "current.json"
    if not selected_current.is_file():
        _fail(
            "current pointer candidate is required to verify a media release",
            release_dir=str(root),
            current_path=str(selected_current),
        )
    current = _load_json(selected_current)
    if current.get("schema_version") != MEDIA_CURRENT_SCHEMA:
        _fail("current.json has an unsupported schema", actual=current.get("schema_version"))
    verify_document(current, public_key_path)
    _validate_current_document(current)

    manifest_path_value = current.get("manifest_path")
    if not isinstance(manifest_path_value, str):
        _fail("current.json lacks manifest_path")
    manifest_path = _safe_release_path(root, manifest_path_value)
    if not manifest_path.is_file():
        _fail("current.json references a missing manifest", path=manifest_path_value)
    manifest_payload = manifest_path.read_bytes()
    actual_manifest_hash = sha256_bytes(manifest_payload)
    if actual_manifest_hash != current.get("manifest_sha256"):
        _fail(
            "manifest hash does not match current.json",
            expected=current.get("manifest_sha256"),
            actual=actual_manifest_hash,
        )
    try:
        manifest = json.loads(manifest_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("manifest JSON is invalid", path=str(manifest_path), error=str(exc))
    if manifest.get("schema_version") != MEDIA_MANIFEST_SCHEMA:
        _fail("manifest has an unsupported schema", actual=manifest.get("schema_version"))
    if manifest.get("release_id") != current.get("release_id"):
        _fail("current.json and manifest release_id differ")
    verify_document(manifest, public_key_path)
    _validate_manifest_identity(manifest)
    closure = _manifest_reference_closure(manifest)

    verified = 0
    resource_item_count = 0
    latest_media_ids: list[str] = []
    for path_value, (expected_hash, expected_size) in sorted(closure["object_registry"].items()):
        if Path(path_value).stem != expected_hash:
            _fail(
                "content-addressed object filename does not match its hash",
                path=path_value,
                expected_hash=expected_hash,
            )
        if not (
            path_value.startswith("/v1/objects/catalog/")
            or path_value.startswith("/v1/objects/detail/")
            or path_value.startswith("/v1/objects/resources/")
            or path_value.startswith("/v1/covers/")
        ):
            _fail("manifest references an unsupported object path", path=path_value)
        object_path = _safe_release_path(root, path_value)
        if not object_path.is_file():
            _fail("manifest references a missing object", path=path_value)
        payload = object_path.read_bytes()
        actual_size = len(payload)
        actual_hash = sha256_bytes(payload)
        if actual_size != expected_size or actual_hash != expected_hash:
            _fail(
                "manifest object verification failed",
                path=path_value,
                expected_size=expected_size,
                actual_size=actual_size,
                expected_hash=expected_hash,
                actual_hash=actual_hash,
            )

        if path_value.startswith("/v1/covers/"):
            verified += 1
            continue
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _fail("media object JSON is invalid", path=path_value, error=str(exc))
        if not isinstance(document, dict):
            _fail("media object JSON must be an object", path=path_value)

        if path_value in closure["detail_paths"]:
            media_id = closure["detail_paths"][path_value]
            if document.get("schema_version") != DETAIL_SCHEMA or document.get("media_id") != media_id:
                _fail("detail object identity or schema mismatch", path=path_value, media_id=media_id)
            resource_ref = document.get("resource_object")
            expected_ref = closure["resource_refs_by_id"][media_id]
            if not isinstance(resource_ref, Mapping):
                _fail("detail object lacks its resource reference", path=path_value)
            actual_ref = (
                resource_ref.get("path"),
                resource_ref.get("hash"),
                resource_ref.get("size"),
            )
            if actual_ref != expected_ref or resource_ref.get("encrypted") is not closure[
                "resource_encrypted_by_id"
            ][media_id]:
                _fail("detail object resource reference does not match manifest", path=path_value)
        elif path_value in closure["resource_paths"]:
            media_id = closure["resource_paths"][path_value]
            items = document.get("items")
            if document.get("schema_version") != RESOURCE_SCHEMA or document.get("media_id") != media_id:
                _fail("resource object identity or schema mismatch", path=path_value, media_id=media_id)
            if not isinstance(items, list):
                _fail("resource object items must be a list", path=path_value)
            resource_item_count += len(items)
        elif path_value in closure["catalog_paths"]:
            expected_channel, expected_role = closure["catalog_expectations"][path_value]
            items = document.get("items")
            if (
                document.get("schema_version") != CATALOG_SCHEMA
                or document.get("channel") != expected_channel
                or document.get("role") != expected_role
                or not isinstance(items, list)
                or document.get("count") != len(items)
            ):
                _fail(
                    "catalog object schema, channel, role or count mismatch",
                    path=path_value,
                    channel=expected_channel,
                    role=expected_role,
                )
            for index, card in enumerate(items):
                if not isinstance(card, Mapping):
                    _fail("catalog card must be an object", path=path_value, index=index)
                media_id = card.get("media_id")
                if not isinstance(media_id, str) or media_id not in closure["expected_media_ids"]:
                    _fail("catalog card references an unknown media_id", path=path_value, index=index)
                detail_ref = card.get("detail_object")
                cover_ref = card.get("cover")
                if not isinstance(detail_ref, Mapping) or not isinstance(cover_ref, Mapping):
                    _fail("catalog card lacks detail or cover reference", path=path_value, media_id=media_id)
                actual_detail = (
                    detail_ref.get("path"),
                    detail_ref.get("hash"),
                    detail_ref.get("size"),
                )
                if actual_detail != closure["detail_refs_by_id"][media_id]:
                    _fail("catalog card detail reference does not match manifest", media_id=media_id)
                cover_hash = cover_ref.get("hash")
                actual_cover = (
                    cover_ref.get("path"),
                    cover_hash,
                    cover_ref.get("size"),
                )
                if not isinstance(cover_hash, str) or actual_cover != closure["cover_refs_by_hash"].get(
                    cover_hash
                ):
                    _fail("catalog card cover reference does not match manifest", media_id=media_id)
                if expected_role == "latest":
                    latest_media_ids.append(media_id)
        else:
            _fail("verified object is not reachable from a typed manifest section", path=path_value)
        verified += 1

    if resource_item_count != closure["counts"]["resources"]:
        _fail(
            "resource object item count does not match manifest",
            expected=closure["counts"]["resources"],
            actual=resource_item_count,
        )
    latest_counter = Counter(latest_media_ids)
    duplicate_latest = sorted(media_id for media_id, count in latest_counter.items() if count != 1)
    missing_latest = sorted(closure["expected_media_ids"] - set(latest_counter))
    if duplicate_latest or missing_latest:
        _fail(
            "latest catalog pages do not cover each media_id exactly once",
            duplicates=duplicate_latest,
            missing=missing_latest,
        )

    return {
        "status": "pass",
        "release_id": current["release_id"],
        "pointer_revision": current["pointer_revision"],
        "current_path": str(selected_current),
        "manifest_sha256": actual_manifest_hash,
        "verified_objects": verified,
        "counts": manifest.get("counts") or {},
        "quality": manifest.get("quality") or {},
        "release_gate": current.get("release_gate") or {},
    }


def _store_pointer_candidate(
    pointer_dir: Path,
    current: Mapping[str, Any],
    public_key_path: Path,
) -> tuple[Path, bool]:
    pointer_dir.mkdir(parents=True, exist_ok=True)
    revision = int(current["pointer_revision"])
    release_id = str(current["release_id"])
    payload = canonical_json_bytes(current)
    maximum_revision = 0

    for existing_path in sorted(pointer_dir.glob("*.json")):
        existing = _load_json(existing_path)
        verify_document(existing, public_key_path)
        existing_revision = int(existing.get("pointer_revision") or 0)
        maximum_revision = max(maximum_revision, existing_revision)
        if existing_revision != revision:
            continue
        if canonical_json_bytes(existing) != payload:
            _fail(
                "pointer_revision is already assigned to a different pointer candidate",
                pointer_revision=revision,
                existing_path=str(existing_path),
                existing_release_id=existing.get("release_id"),
                requested_release_id=release_id,
            )
        return existing_path, True

    if revision <= maximum_revision:
        _fail(
            "pointer_revision must increase monotonically",
            pointer_revision=revision,
            maximum_existing_revision=maximum_revision,
        )

    target = pointer_dir / f"{revision:020d}-{release_id}.json"
    temporary = pointer_dir / f".{target.name}.{uuid.uuid4().hex}.tmp"
    temporary.write_bytes(payload)
    try:
        verify_document(_load_json(temporary), public_key_path)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target, False


def build_media_release(config: MediaReleaseConfig) -> MediaReleaseBuildResult:
    if not isinstance(config.pointer_revision, int) or config.pointer_revision < 1:
        _fail("pointer_revision must be a positive integer", pointer_revision=config.pointer_revision)
    if config.page_size < 1:
        _fail("page_size must be positive", page_size=config.page_size)
    if config.min_movies < 1 or config.min_series < 1:
        _fail(
            "movie and series release minimums must be positive",
            min_movies=config.min_movies,
            min_series=config.min_series,
        )
    if config.max_object_bytes < 1024:
        _fail("max_object_bytes is unrealistically small", max_object_bytes=config.max_object_bytes)
    if not isinstance(config.min_app_version, str) or not config.min_app_version.strip():
        _fail("min_app_version must not be empty")
    if config.allow_regression_reason is not None and not config.allow_regression_reason.strip():
        _fail("allow_regression_reason must contain a concrete reason")

    movie_feed = _load_json(config.movie_feed_path)
    series_feed = _load_json(config.series_feed_path)
    movie_items = _validate_feed(movie_feed, expected_kind="movie", minimum=config.min_movies)
    series_items = _validate_feed(series_feed, expected_kind="series", minimum=config.min_series)
    quality = _quality_gate(movie_items, series_items)

    movie_covers = _load_cover_index(config.movie_cover_bundle)
    series_covers = _load_cover_index(config.series_cover_bundle)
    generated_at_dt = _content_watermark(movie_items + series_items)
    generated_at = generated_at_dt.isoformat().replace("+00:00", "Z")

    output_dir = config.output_dir.resolve()
    staging_parent = output_dir / "staging"
    release_parent = staging_parent / "releases"
    pointer_dir = staging_parent / "pointers"
    build_lock = _acquire_release_lock(staging_parent / ".build.lock")
    try:
        release_parent.mkdir(parents=True, exist_ok=True)
        temp_root = release_parent / f".build-{uuid.uuid4().hex}"
        temp_root.mkdir(parents=True, exist_ok=False)
    except Exception:
        _release_release_lock(build_lock)
        raise
    pointer_temp: Path | None = None

    try:
        cover_refs: dict[str, dict[str, Any]] = {}
        detail_refs: dict[str, dict[str, Any]] = {}
        resource_refs: dict[str, dict[str, Any]] = {}
        cards_by_channel: dict[str, list[dict[str, Any]]] = {"movie": []}
        object_refs_by_path: dict[str, dict[str, Any]] = {}

        for item, cover_index in [
            *((item, movie_covers) for item in movie_items),
            *((item, series_covers) for item in series_items),
        ]:
            media_id = _media_id(item)
            cover_ref = _copy_cover(item, cover_index, temp_root, cover_refs)
            resource_ref = _write_object(
                temp_root,
                "resources",
                _resource_document(item),
                config.max_object_bytes,
            )
            resource_object_ref = {**resource_ref, "encrypted": False}
            detail_ref = _write_object(
                temp_root,
                "detail",
                _detail_document(item, resource_object_ref),
                config.max_object_bytes,
            )
            resource_refs[media_id] = resource_object_ref
            detail_refs[media_id] = detail_ref
            object_refs_by_path[resource_ref["path"]] = resource_ref
            object_refs_by_path[detail_ref["path"]] = detail_ref
            channel = "movie" if item.get("content_kind") == "movie" else _series_channel(item)
            cards_by_channel.setdefault(channel, []).append(_card_document(item, detail_ref, cover_ref))

        regression = _check_regression(
            config.previous_manifest_path,
            movie_count=len(movie_items),
            series_count=len(series_items),
            resource_count=quality["resource_count"],
            cover_count=len(cover_refs),
            unknown_series_resources=quality["unknown_series_resources"],
            allow_reason=config.allow_regression_reason,
            public_key_path=config.public_key_path,
        )
        quality["cover_complete"] = True
        build_quality = {**quality, "regression_gate": regression}

        channel_manifest: dict[str, Any] = {}
        for channel, cards in sorted(cards_by_channel.items()):
            entry: dict[str, Any] = {"latest_pages": []}
            if channel == "movie":
                special = [card for card in cards if card.get("recommended")][:10] or cards[:10]
                featured = _catalog_object(
                    temp_root,
                    channel=channel,
                    role="featured",
                    cards=special,
                    max_bytes=config.max_object_bytes,
                )
                entry["featured"] = featured
                object_refs_by_path[featured["path"]] = {
                    key: featured[key] for key in ("hash", "size", "path")
                }
            else:
                special = [card for card in cards if card.get("update_status")][:10] or cards[:10]
                updating = _catalog_object(
                    temp_root,
                    channel=channel,
                    role="updating",
                    cards=special,
                    max_bytes=config.max_object_bytes,
                )
                entry["updating"] = updating
                object_refs_by_path[updating["path"]] = {
                    key: updating[key] for key in ("hash", "size", "path")
                }

            for offset in range(0, len(cards), config.page_size):
                page_number = offset // config.page_size + 1
                page_ref = _catalog_object(
                    temp_root,
                    channel=channel,
                    role="latest",
                    page=page_number,
                    cards=cards[offset : offset + config.page_size],
                    max_bytes=config.max_object_bytes,
                )
                entry["latest_pages"].append(page_ref)
                object_refs_by_path[page_ref["path"]] = {
                    key: page_ref[key] for key in ("hash", "size", "path")
                }
            channel_manifest[channel] = entry

        for ref in cover_refs.values():
            object_refs_by_path[ref["path"]] = {key: ref[key] for key in ("hash", "size", "path")}

        counts = {
            "movie": len(movie_items),
            "series": len(series_items),
            "resources": quality["resource_count"],
            "covers": len(cover_refs),
            "details": len(detail_refs),
            "catalog_objects": sum(
                len(entry.get("latest_pages") or [])
                + (1 if entry.get("featured") else 0)
                + (1 if entry.get("updating") else 0)
                for entry in channel_manifest.values()
            ),
        }
        manifest_content = {
            "schema_version": MEDIA_MANIFEST_SCHEMA,
            "generated_at": generated_at,
            "channels": channel_manifest,
            "details": detail_refs,
            "resources": resource_refs,
            "covers": cover_refs,
            "cover_base_path": "/v1/covers/",
            "counts": counts,
            "quality": quality,
            "objects": [object_refs_by_path[path] for path in sorted(object_refs_by_path)],
        }
        release_hash = sha256_bytes(canonical_json_bytes(manifest_content))
        release_id = f"{generated_at_dt.strftime('%Y%m%dT%H%M%SZ')}-{release_hash[:8]}"
        manifest_path_value = f"/v1/releases/{release_id}/manifest.json"
        manifest = sign_document(
            {**manifest_content, "release_id": release_id},
            config.private_key_path,
        )
        manifest_path = temp_root / manifest_path_value.lstrip("/")
        _write_json(manifest_path, manifest)
        manifest_hash = sha256_file(manifest_path)

        current_unsigned = {
            "schema_version": MEDIA_CURRENT_SCHEMA,
            "pointer_revision": config.pointer_revision,
            "release_id": release_id,
            "manifest_path": manifest_path_value,
            "manifest_sha256": manifest_hash,
            "published_at": generated_at,
            "min_app_version": config.min_app_version,
            "release_gate": regression,
        }
        current = sign_document(current_unsigned, config.private_key_path)
        pointer_temp = staging_parent / f".pointer-{uuid.uuid4().hex}.json"
        _write_json(pointer_temp, current)

        preflight = verify_media_release(temp_root, config.public_key_path, pointer_temp)
        final_dir = release_parent / release_id
        release_reused = False
        if final_dir.exists():
            existing = verify_media_release(final_dir, config.public_key_path, pointer_temp)
            if existing["manifest_sha256"] != preflight["manifest_sha256"]:
                _fail(
                    "immutable release_id already exists with different content",
                    release_id=release_id,
                )
            shutil.rmtree(temp_root)
            release_reused = True
        else:
            temp_root.replace(final_dir)
            verify_media_release(final_dir, config.public_key_path, pointer_temp)

        final_current, pointer_reused = _store_pointer_candidate(
            pointer_dir,
            current,
            config.public_key_path,
        )
        if pointer_temp.exists():
            pointer_temp.unlink()
        pointer_temp = None

        final_manifest = final_dir / manifest_path_value.lstrip("/")
        return MediaReleaseBuildResult(
            release_id=release_id,
            release_dir=str(final_dir),
            current_path=str(final_current),
            manifest_path=str(final_manifest),
            manifest_sha256=manifest_hash,
            object_count=len(object_refs_by_path),
            reused=release_reused and pointer_reused,
            release_reused=release_reused,
            pointer_reused=pointer_reused,
            counts=counts,
            quality=build_quality,
        )
    except Exception:
        if temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)
        if pointer_temp is not None and pointer_temp.exists():
            pointer_temp.unlink()
        raise
    finally:
        _release_release_lock(build_lock)
