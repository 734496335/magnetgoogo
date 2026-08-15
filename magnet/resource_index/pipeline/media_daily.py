"""Unattended daily media crawl, rating, bundle and dual-plane publication."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from magnet.rating_resolver.service import RatingResolver
from magnet.rating_resolver.writeback import enrich_feed_file
from magnet.resource_index.errors import (
    ACCESS_CHALLENGE,
    DETAIL_DOM_DRIFT,
    LATEST_BATCH_INTERRUPTED,
    LATEST_CRAWL_INCOMPLETE,
    LISTING_DOM_DRIFT,
    LISTING_EMPTY,
    LIVE_EMPTY_RESULT,
    LIVE_HTTP_ERROR,
    LIVE_RATE_LIMITED,
    LIVE_REQUEST_BUDGET_EXHAUSTED,
    NOT_FOUND,
    CONFIG_ERROR,
    ResourceIndexError,
)
from magnet.resource_index.pipeline.media_aggregate import aggregate_media_feeds
from magnet.resource_index.pipeline.magnet_only import build_magnet_only_media_feeds
from magnet.resource_index.pipeline.media_library import export_source_library_feed
from magnet.resource_index.pipeline.media_maintenance import (
    RetentionConfig,
    assert_disk_capacity,
    prune_media_state,
    run_lock as _run_lock,
    update_candidate_soak,
)
from magnet.resource_index.pipeline.media_offline_bundle import (
    audit_media_app_bundle,
    build_media_app_bundle,
)
from magnet.resource_index.pipeline.media_rating_state import (
    apply_media_rating_state,
    persist_media_rating_state,
)
from magnet.resource_index.pipeline.movie_automation import (
    run_safe_movie_source,
    safe_movie_source_status,
)
from magnet.resource_index.publish.filesystem import FilesystemPublisherBackend
from magnet.resource_index.publish.orchestrator import MediaPublishConfig, publish_media_release
from magnet.resource_index.publish.worker_bridge import WorkerR2PublisherBackend
from magnet.resource_index.release.builder import MediaReleaseConfig, build_media_release
from magnet.resource_index.release.protocol import canonical_json_bytes, sha256_file, verify_document


@dataclass(frozen=True)
class DailySourceConfig:
    source_id: str
    count: int
    freshness_required: bool = False


@dataclass(frozen=True)
class MediaDailyConfig:
    state_root: Path
    public_root: Path
    private_key_path: Path
    public_key_path: Path
    worker_url: str
    worker_token_env: str
    r2_public_base: str
    aliyun_public_base: str
    min_app_version: str
    sources: tuple[DailySourceConfig, ...]
    previous_public_key_path: Path | None = None
    min_movies: int = 1
    min_series: int = 1
    page_size: int = 50
    max_workers: int = 8
    rating_lookup_limit_per_feed: int = 40
    retention_runs: int = 7
    retention_status_history: int = 30
    retention_releases: int = 3
    retention_receipts: int = 30
    disk_max_used_percent: float = 80.0
    disk_min_free_bytes: int = 2 * 1024 * 1024 * 1024
    source_fallback_max_age_hours: int = 168
    source_fallback_retry_delay_seconds: int = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _soak_date() -> date:
    return _utc_now().astimezone(ZoneInfo("Asia/Shanghai")).date()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(CONFIG_ERROR, "failed to read media daily JSON", {"path": str(path)}) from exc
    if not isinstance(value, dict):
        raise ResourceIndexError(CONFIG_ERROR, "media daily JSON must be an object", {"path": str(path)})
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    temporary.write_bytes(canonical_json_bytes(value))
    temporary.replace(path)


def _config_int(source: dict[str, Any], name: str, default: int, *, minimum: int) -> int:
    value = source.get(name, default)
    if type(value) is not int or value < minimum:
        raise ResourceIndexError(CONFIG_ERROR, "media daily integer setting is invalid", {"name": name, "value": value})
    return value


def _config_percent(source: dict[str, Any], name: str, default: float) -> float:
    value = source.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResourceIndexError(CONFIG_ERROR, "media daily percent setting is invalid", {"name": name, "value": value})
    result = float(value)
    if not (0 < result < 100):
        raise ResourceIndexError(CONFIG_ERROR, "media daily percent setting is out of range", {"name": name, "value": value})
    return result


def load_media_daily_config(path: str | Path) -> MediaDailyConfig:
    source = _load_json(Path(path))
    raw_sources = source.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ResourceIndexError(CONFIG_ERROR, "media daily sources are missing", {})
    sources: list[DailySourceConfig] = []
    for item in raw_sources:
        if not isinstance(item, dict) or not str(item.get("source_id") or "").strip():
            raise ResourceIndexError(CONFIG_ERROR, "media daily source entry is invalid", {"entry": item})
        count = item.get("count")
        if type(count) is not int or count < 1:
            raise ResourceIndexError(CONFIG_ERROR, "media daily source count is invalid", {"entry": item})
        freshness_required = item.get("freshness_required", False)
        if type(freshness_required) is not bool:
            raise ResourceIndexError(CONFIG_ERROR, "media daily source freshness flag is invalid", {"entry": item})
        sources.append(DailySourceConfig(str(item["source_id"]), count, freshness_required))
    return MediaDailyConfig(
        state_root=Path(str(source["state_root"])).expanduser(),
        public_root=Path(str(source["public_root"])).expanduser(),
        private_key_path=Path(str(source["private_key_path"])).expanduser(),
        public_key_path=Path(str(source["public_key_path"])).expanduser(),
        worker_url=str(source.get("worker_url") or "").rstrip("/"),
        worker_token_env=str(source.get("worker_token_env") or "R2_UPLOAD_WORKER_TOKEN"),
        r2_public_base=str(source.get("r2_public_base") or "https://media.magnetgoogo.com").rstrip("/"),
        aliyun_public_base=str(source.get("aliyun_public_base") or "https://cn.magnetgoogo.com/media").rstrip("/"),
        min_app_version=str(source.get("min_app_version") or "0.2.3"),
        sources=tuple(sources),
        previous_public_key_path=(
            Path(str(source["previous_public_key_path"])).expanduser()
            if source.get("previous_public_key_path")
            else None
        ),
        min_movies=_config_int(source, "min_movies", 1, minimum=1),
        min_series=_config_int(source, "min_series", 1, minimum=1),
        page_size=_config_int(source, "page_size", 50, minimum=1),
        max_workers=_config_int(source, "max_workers", 8, minimum=1),
        rating_lookup_limit_per_feed=_config_int(
            source,
            "rating_lookup_limit_per_feed",
            40,
            minimum=1,
        ),
        retention_runs=_config_int(source, "retention_runs", 7, minimum=1),
        retention_status_history=_config_int(source, "retention_status_history", 30, minimum=1),
        retention_releases=_config_int(source, "retention_releases", 3, minimum=1),
        retention_receipts=_config_int(source, "retention_receipts", 30, minimum=1),
        disk_max_used_percent=_config_percent(source, "disk_max_used_percent", 80.0),
        disk_min_free_bytes=_config_int(
            source,
            "disk_min_free_bytes",
            2 * 1024 * 1024 * 1024,
            minimum=0,
        ),
        source_fallback_max_age_hours=_config_int(
            source,
            "source_fallback_max_age_hours",
            168,
            minimum=1,
        ),
        source_fallback_retry_delay_seconds=_config_int(
            source,
            "source_fallback_retry_delay_seconds",
            900,
            minimum=0,
        ),
    )


def _http_bytes(url: str, *, timeout: float = 60.0, max_attempts: int = 3) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MagnetGoogo-Media-Daily/1.0", "Cache-Control": "no-cache"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with opener.open(request, timeout=timeout) as response:
                if int(response.status) != 200:
                    raise ResourceIndexError(
                        CONFIG_ERROR,
                        "media endpoint returned non-200",
                        {"url": url, "status": response.status},
                    )
                return response.read()
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt < max_attempts:
                time.sleep(min(2 ** (attempt - 1), 4))
    assert last_error is not None
    raise ResourceIndexError(
        CONFIG_ERROR,
        "media endpoint request failed",
        {"url": url, "error": type(last_error).__name__, "attempts": max_attempts},
    ) from last_error


def _online_control(base: str, run_dir: Path) -> tuple[dict[str, Any], Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    current_bytes = _http_bytes(f"{base}/v1/current.json")
    current_path = run_dir / "previous-current.json"
    current_path.write_bytes(current_bytes)
    current = json.loads(current_bytes.decode("utf-8"))
    manifest_bytes = _http_bytes(f"{base}{current['manifest_path']}")
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_hash != current.get("manifest_sha256"):
        raise ResourceIndexError(CONFIG_ERROR, "online manifest hash does not match current pointer", {"base": base})
    manifest_path = run_dir / "previous-manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    return current, manifest_path


def _verify_with_trusted_media_keys(
    document: dict[str, Any],
    *,
    config: MediaDailyConfig,
    label: str,
) -> str:
    key_paths = [config.public_key_path]
    if config.previous_public_key_path is not None and config.previous_public_key_path != config.public_key_path:
        key_paths.append(config.previous_public_key_path)
    failures: list[str] = []
    for key_path in key_paths:
        if not key_path.is_file():
            failures.append(f"missing:{key_path}")
            continue
        try:
            verify_document(document, key_path)
        except ResourceIndexError as exc:
            failures.append(f"{key_path}:{exc.message}")
            continue
        return str(key_path)
    raise ResourceIndexError(
        CONFIG_ERROR,
        "online media document is not signed by a trusted key",
        {"label": label, "failures": failures},
    )


def _validate_online_control(
    current: dict[str, Any],
    manifest_path: Path,
    *,
    config: MediaDailyConfig,
    base: str,
) -> dict[str, Any]:
    revision = current.get("pointer_revision")
    release_id = current.get("release_id")
    if type(revision) is not int or revision < 1 or not isinstance(release_id, str) or not release_id:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "online media current pointer metadata is invalid",
            {"base": base, "pointer_revision": revision, "release_id": release_id},
        )
    current_key = _verify_with_trusted_media_keys(current, config=config, label=f"{base}:current")
    manifest = _load_json(manifest_path)
    manifest_key = _verify_with_trusted_media_keys(manifest, config=config, label=f"{base}:manifest")
    if manifest.get("release_id") != release_id:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "online media manifest release does not match current pointer",
            {"base": base, "current_release_id": release_id, "manifest_release_id": manifest.get("release_id")},
        )
    return {
        "base": base,
        "pointer_revision": revision,
        "release_id": release_id,
        "current_key": current_key,
        "manifest_key": manifest_key,
    }


def _verify_manifest_available(base: str, current: dict[str, Any]) -> str:
    manifest_path = current.get("manifest_path")
    expected_hash = current.get("manifest_sha256")
    if not isinstance(manifest_path, str) or not manifest_path.startswith("/v1/releases/"):
        raise ResourceIndexError(CONFIG_ERROR, "media current manifest path is invalid", {"base": base})
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ResourceIndexError(CONFIG_ERROR, "media current manifest hash is invalid", {"base": base})
    manifest_bytes = _http_bytes(f"{base}{manifest_path}")
    actual_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if actual_hash != expected_hash:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media current manifest is unavailable on recovery target",
            {"base": base, "expected": expected_hash, "actual": actual_hash},
        )
    return actual_hash


def _pointer_semantics(document: dict[str, Any]) -> bytes:
    value = dict(document)
    value.pop("pointer_revision", None)
    value.pop("signature", None)
    return canonical_json_bytes(value)


def _reconcile_online_controls(
    config: MediaDailyConfig,
    run_dir: Path,
    *,
    publish: bool,
) -> tuple[dict[str, Any], Path, Path, dict[str, Any]]:
    r2_dir = run_dir / "control-r2"
    aliyun_dir = run_dir / "control-aliyun"
    r2_current, r2_manifest = _online_control(config.r2_public_base, r2_dir)
    aliyun_current, aliyun_manifest = _online_control(config.aliyun_public_base, aliyun_dir)
    _validate_online_control(r2_current, r2_manifest, config=config, base=config.r2_public_base)
    _validate_online_control(aliyun_current, aliyun_manifest, config=config, base=config.aliyun_public_base)
    r2_current_path = r2_dir / "previous-current.json"
    aliyun_current_path = aliyun_dir / "previous-current.json"
    r2_bytes = r2_current_path.read_bytes()
    aliyun_bytes = aliyun_current_path.read_bytes()
    r2_revision = int(r2_current["pointer_revision"])
    aliyun_revision = int(aliyun_current["pointer_revision"])
    stage: dict[str, Any] = {
        "status": "pass",
        "r2_revision_before": r2_revision,
        "aliyun_revision_before": aliyun_revision,
        "action": "none",
    }
    if r2_bytes == aliyun_bytes:
        stage["current_sha256"] = hashlib.sha256(r2_bytes).hexdigest()
        return r2_current, r2_manifest, r2_current_path, stage

    if not publish:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media public current pointers diverge during read-only run",
            {
                "r2_revision": r2_revision,
                "aliyun_revision": aliyun_revision,
                "r2_release_id": r2_current.get("release_id"),
                "aliyun_release_id": aliyun_current.get("release_id"),
            },
        )
    if r2_revision == aliyun_revision:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media public current pointers rebind the same revision differently",
            {
                "pointer_revision": r2_revision,
                "r2_release_id": r2_current.get("release_id"),
                "aliyun_release_id": aliyun_current.get("release_id"),
            },
        )
    if abs(r2_revision - aliyun_revision) != 1:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media public current revision gap is unsafe to repair automatically",
            {"r2_revision": r2_revision, "aliyun_revision": aliyun_revision},
        )

    if r2_revision > aliyun_revision:
        _verify_manifest_available(config.aliyun_public_base, r2_current)
        FilesystemPublisherBackend(config.public_root).promote_current(r2_current_path)
        expected_current = r2_current
        expected_manifest = r2_manifest
        expected_path = r2_current_path
        stage["action"] = "repair_aliyun_from_r2_authority"
    else:
        _verify_manifest_available(config.r2_public_base, aliyun_current)
        token = os.environ.get(config.worker_token_env, "")
        if len(token) < 32 or not config.worker_url.startswith("https://"):
            raise ResourceIndexError(CONFIG_ERROR, "production Worker credentials are missing for R2 control repair", {})
        WorkerR2PublisherBackend(
            worker_url=config.worker_url,
            upload_token=token,
            prefix="",
            allow_production_root=True,
            allow_current_promotion=True,
            max_attempts=4,
        ).promote_current(aliyun_current_path)
        expected_current = aliyun_current
        expected_manifest = aliyun_manifest
        expected_path = aliyun_current_path
        stage["action"] = "repair_r2_from_signed_aliyun_ahead"

    verification = [
        _verify_public_control(config.r2_public_base, expected_path),
        _verify_public_control(config.aliyun_public_base, expected_path),
    ]
    stage["verification"] = verification
    stage["current_sha256"] = hashlib.sha256(expected_path.read_bytes()).hexdigest()
    stage["r2_revision_after"] = int(expected_current["pointer_revision"])
    stage["aliyun_revision_after"] = int(expected_current["pointer_revision"])
    return expected_current, expected_manifest, expected_path, stage


def _filter_feed_to_bundle(feed_path: Path, bundle_dir: Path, output_path: Path) -> dict[str, Any]:
    feed = _load_json(feed_path)
    app_feed = _load_json(bundle_dir / "feed.json")
    source_by_id = {
        str(item.get("movie_id")): item
        for item in feed.get("items") or []
        if isinstance(item, dict) and item.get("movie_id")
    }
    items: list[dict[str, Any]] = []
    for app_item in app_feed.get("items") or []:
        movie_id = str(app_item.get("movie_id") or "")
        source_item = source_by_id.get(movie_id)
        if source_item is None:
            raise ResourceIndexError(CONFIG_ERROR, "bundle item is missing from source media feed", {"movie_id": movie_id})
        item = dict(source_item)
        item["rank"] = len(items) + 1
        items.append(item)
    filtered = dict(feed)
    filtered["items"] = items
    summary = dict(filtered.get("summary") or {})
    summary["record_count"] = len(items)
    summary["resource_count"] = sum(len(item.get("resources") or []) for item in items)
    summary["cover_count"] = len(items)
    summary["offline_ready"] = True
    filtered["summary"] = summary
    quality = dict(filtered.get("quality") or {})
    failures = _load_json(bundle_dir / "cover_failures.json")
    quality["cover_failure_count"] = int(failures.get("failed_count") or 0)
    quality["required_fields"] = ["title", "cover", "resources"]
    quality["rating_required"] = False
    filtered["quality"] = quality
    _write_json(output_path, filtered)
    return filtered


def _rating_next_offset(result: dict[str, Any], fallback: int) -> int:
    value = result.get("next_offset")
    if type(value) is int and value >= 0:
        return value
    return fallback


def _run_rating_stage(
    *,
    movie_feed: Path,
    series_feed: Path,
    root: Path,
    lookup_limit_per_feed: int,
    skip_lookup: bool = False,
) -> dict[str, Any]:
    rating_state_path = root / "ratings" / "media-ratings.json"
    restored = apply_media_rating_state(
        feed_paths=(movie_feed, series_feed),
        state_path=rating_state_path,
    )
    if skip_lookup:
        return {
            "status": "skipped",
            "sources": ["douban", "imdb", "rotten_tomatoes", "bangumi"],
            "restored": restored,
            "lookup": {"status": "skipped"},
            "persisted": None,
        }
    progress_path = root / "ratings" / "progress.json"
    progress_corrupt = False
    try:
        progress = _load_json(progress_path) if progress_path.exists() else {}
    except ResourceIndexError:
        progress = {}
        progress_corrupt = True
    if progress and progress.get("schema_version") != "media-rating-progress/1":
        progress = {}
        progress_corrupt = True
    movie_value = progress.get("movie_offset", 0)
    series_value = progress.get("series_offset", 0)
    if type(movie_value) is not int or movie_value < 0 or type(series_value) is not int or series_value < 0:
        movie_value = 0
        series_value = 0
        progress_corrupt = True
    movie_offset = movie_value
    series_offset = series_value
    next_movie_offset = movie_offset
    next_series_offset = series_offset
    rating_result: dict[str, Any]
    try:
        resolver = RatingResolver(
            cache_dir=root / "rating-cache",
            sources=("douban", "imdb", "rotten_tomatoes", "bangumi"),
            max_workers=4,
        )
        movie_rating = enrich_feed_file(
            movie_feed,
            resolver,
            lookup_limit=lookup_limit_per_feed,
            start_offset=movie_offset,
            dry_run=False,
        )
        series_rating = enrich_feed_file(
            series_feed,
            resolver,
            lookup_limit=lookup_limit_per_feed,
            start_offset=series_offset,
            dry_run=False,
        )
        next_movie_offset = _rating_next_offset(movie_rating, movie_offset)
        next_series_offset = _rating_next_offset(series_rating, series_offset)
        next_progress = {
            "schema_version": "media-rating-progress/1",
            "movie_offset": next_movie_offset,
            "series_offset": next_series_offset,
            "lookup_limit_per_feed": lookup_limit_per_feed,
            "updated_at": _iso(),
        }
        _write_json(progress_path, next_progress)
        error_count = int(movie_rating.get("errors") or 0) + int(series_rating.get("errors") or 0)
        rating_result = {
            "status": "pass" if error_count == 0 else "warning",
            "error_count": error_count,
            "movie": movie_rating,
            "series": series_rating,
        }
    except Exception as exc:  # rating providers are optional publication enrichment
        rating_result = {
            "status": "warning",
            "error_count": 1,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
    persisted = persist_media_rating_state(
        feed_paths=(movie_feed, series_feed),
        state_path=rating_state_path,
    )
    return {
        "status": rating_result["status"],
        "sources": ["douban", "imdb", "rotten_tomatoes", "bangumi"],
        "restored": restored,
        "lookup": rating_result,
        "persisted": persisted,
        "progress": {
            "path": str(progress_path),
            "previous_state_corrupt": progress_corrupt,
            "movie_offset": next_movie_offset,
            "series_offset": next_series_offset,
            "lookup_limit_per_feed": lookup_limit_per_feed,
        },
    }


def _content_fingerprint(movie_bundle: Path, series_bundle: Path) -> str:
    payload = {
        "movie": _load_json(movie_bundle / "feed.json").get("items") or [],
        "series": _load_json(series_bundle / "feed.json").get("items") or [],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _verify_public_control(base: str, candidate_path: Path) -> dict[str, Any]:
    expected = candidate_path.read_bytes()
    current = _http_bytes(f"{base}/v1/current.json")
    if current != expected:
        raise ResourceIndexError(CONFIG_ERROR, "public current pointer bytes do not match candidate", {"base": base})
    document = json.loads(current.decode("utf-8"))
    manifest = _http_bytes(f"{base}{document['manifest_path']}")
    actual_manifest_hash = hashlib.sha256(manifest).hexdigest()
    if actual_manifest_hash != document.get("manifest_sha256"):
        raise ResourceIndexError(CONFIG_ERROR, "public manifest hash mismatch", {"base": base})
    return {
        "base": base,
        "pointer_revision": document["pointer_revision"],
        "release_id": document["release_id"],
        "pointer_sha256": hashlib.sha256(current).hexdigest(),
        "manifest_sha256": actual_manifest_hash,
    }


def _archive_unpromoted_pointer_candidates(
    pointer_dir: Path,
    *,
    public_revision: int,
    public_release_id: str,
    config: MediaDailyConfig,
    evidence_dir: Path,
) -> list[dict[str, Any]]:
    archived: list[dict[str, Any]] = []
    if not pointer_dir.is_dir():
        return archived
    for path in sorted(pointer_dir.glob("*.json")):
        document = _load_json(path)
        trusted_key = _verify_with_trusted_media_keys(
            document,
            config=config,
            label=f"staged-pointer:{path.name}",
        )
        revision = document.get("pointer_revision")
        release_id = str(document.get("release_id") or "")
        if type(revision) is not int or revision < 1 or not release_id:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "staged media pointer metadata is invalid",
                {"path": str(path), "pointer_revision": revision, "release_id": release_id},
            )
        if revision < public_revision:
            continue
        if revision == public_revision:
            if release_id != public_release_id:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "staged published revision conflicts with public current",
                    {
                        "path": str(path),
                        "pointer_revision": revision,
                        "staged_release_id": release_id,
                        "public_release_id": public_release_id,
                    },
                )
            continue
        evidence_dir.mkdir(parents=True, exist_ok=True)
        target = evidence_dir / path.name
        if target.exists():
            raise ResourceIndexError(
                CONFIG_ERROR,
                "unpromoted pointer evidence target already exists",
                {"source": str(path), "target": str(target)},
            )
        path.replace(target)
        archived.append(
            {
                "pointer_revision": revision,
                "release_id": release_id,
                "source_path": str(path),
                "evidence_path": str(target),
                "trusted_key": trusted_key,
            }
        )
    return archived


def _status_base(started_at: str, *, mode: str) -> dict[str, Any]:
    return {
        "schema_version": "media-daily-status/1",
        "mode": mode,
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "published": False,
        "no_change": False,
        "stages": {},
    }


_TRANSIENT_SOURCE_ERRORS = {
    ACCESS_CHALLENGE,
    DETAIL_DOM_DRIFT,
    LATEST_BATCH_INTERRUPTED,
    LATEST_CRAWL_INCOMPLETE,
    LISTING_DOM_DRIFT,
    LISTING_EMPTY,
    LIVE_EMPTY_RESULT,
    LIVE_HTTP_ERROR,
    LIVE_RATE_LIMITED,
    LIVE_REQUEST_BUDGET_EXHAUSTED,
    NOT_FOUND,
}


def _source_fallback(
    *,
    source: DailySourceConfig,
    source_root: Path,
    error: BaseException,
    max_age_hours: int,
) -> tuple[str, dict[str, Any]]:
    if not isinstance(error, ResourceIndexError) or error.error_code not in _TRANSIENT_SOURCE_ERRORS:
        raise error
    current = safe_movie_source_status(
        source_id=source.source_id,
        output_dir=source_root,
        target_count=source.count,
    )
    job = current.get("job") or {}
    source_state = current.get("source") or {}
    db_path = Path(str(job.get("db_path") or ""))
    completed_at = source_state.get("last_completed_at") or job.get("completed_at")
    if not db_path.is_file() or not completed_at:
        raise error
    try:
        completed = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
    except ValueError:
        raise error
    stale_hours = max(0.0, (_utc_now() - completed.astimezone(timezone.utc)).total_seconds() / 3600)
    if stale_hours > max_age_hours:
        raise ResourceIndexError(
            LATEST_CRAWL_INCOMPLETE,
            "source fallback database is too old",
            {
                "source_id": source.source_id,
                "stale_hours": round(stale_hours, 2),
                "maximum_hours": max_age_hours,
                "original_error_code": error.error_code,
            },
        ) from error
    return str(db_path), {
        "source_id": source.source_id,
        "status": "fallback",
        "reason": "last_known_good_database",
        "target_count": source.count,
        "job_status": job.get("status"),
        "covered_count": job.get("covered_count"),
        "db_path": str(db_path),
        "stale_hours": round(stale_hours, 2),
        "error": {
            "type": type(error).__name__,
            "error_code": error.error_code,
            "message": error.message,
        },
    }


def run_media_daily(
    config: MediaDailyConfig,
    *,
    publish: bool = True,
    skip_crawl: bool = False,
    skip_ratings: bool = False,
    force_publish: bool = False,
) -> dict[str, Any]:
    started_at = _iso()
    mode = "publish" if publish else ("audit" if skip_crawl and skip_ratings else "candidate")
    root = config.state_root.resolve()
    status_dir = root / "status"
    latest_status = status_dir / "latest.json"
    mode_status = status_dir / f"latest-{mode}.json"
    status = _status_base(started_at, mode=mode)
    run_id = _utc_now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = root / "runs" / run_id
    status["run_id"] = run_id
    status_owned = False
    root.mkdir(parents=True, exist_ok=True)

    try:
        with _run_lock(root / "locks" / "media-daily.lock", started_at=started_at) as lock_status:
            status_owned = True
            retention = prune_media_state(
                root,
                RetentionConfig(
                    runs=config.retention_runs,
                    status_history=config.retention_status_history,
                    releases=config.retention_releases,
                    receipts=config.retention_receipts,
                ),
            )
            disk = assert_disk_capacity(
                root,
                max_used_percent=config.disk_max_used_percent,
                min_free_bytes=config.disk_min_free_bytes,
            )
            run_dir.mkdir(parents=True, exist_ok=False)
            status["stages"]["maintenance"] = {
                "lock": lock_status,
                "retention": retention,
                "disk": disk,
            }
            _write_json(latest_status, status)
            source_results: list[dict[str, Any]] = []
            library_feeds: list[Path] = []
            recovery_candidates: list[tuple[int, DailySourceConfig, Path]] = []
            source_root = root / "sources"
            for source in config.sources:
                if skip_crawl:
                    current = safe_movie_source_status(
                        source_id=source.source_id,
                        output_dir=source_root,
                        target_count=source.count,
                    )
                    current_job = current["job"]
                    db_path = str(current_job["db_path"])
                    source_results.append({
                        "source_id": source.source_id,
                        "status": "crawl_skipped",
                        "reason": "skip_crawl",
                        "target_count": source.count,
                        "job_status": str(current_job.get("status") or ""),
                        "covered_count": int(current_job.get("covered_count") or 0),
                        "db_path": db_path,
                        "freshness_required": source.freshness_required,
                    })
                else:
                    try:
                        result = run_safe_movie_source(
                            source_id=source.source_id,
                            output_dir=source_root,
                            target_count=source.count,
                        )
                        db_path = result.db_path
                        result_payload = {**result.__dict__, "freshness_required": source.freshness_required}
                        result_status = str(getattr(result, "status", "") or "")
                        result_reason = str(getattr(result, "reason", "") or "")
                        result_job_status = str(getattr(result, "job_status", "") or "")
                        freshness_incomplete = (
                            result_status == "paused"
                            or result_job_status in {"pending", "paused", "partial"}
                            or (result_status == "skipped" and result_reason == "failure_backoff")
                        )
                        if source.freshness_required and freshness_incomplete:
                            synthetic = ResourceIndexError(
                                LIVE_RATE_LIMITED,
                                "freshness-required source did not complete a fresh crawl",
                                {
                                    "source_id": source.source_id,
                                    "reason": result_reason,
                                    "status": result_status,
                                    "job_status": result_job_status,
                                },
                            )
                            db_path, fallback = _source_fallback(
                                source=source,
                                source_root=source_root,
                                error=synthetic,
                                max_age_hours=config.source_fallback_max_age_hours,
                            )
                            fallback["freshness_required"] = True
                            fallback["initial_result"] = result_payload
                            source_results.append(fallback)
                        else:
                            source_results.append(result_payload)
                    except BaseException as exc:
                        db_path, fallback = _source_fallback(
                            source=source,
                            source_root=source_root,
                            error=exc,
                            max_age_hours=config.source_fallback_max_age_hours,
                        )
                        fallback["freshness_required"] = source.freshness_required
                        source_results.append(fallback)
                library_path = run_dir / "library" / f"{source.source_id}.json"
                export_source_library_feed(
                    db_path=db_path,
                    source_id=source.source_id,
                    output_path=library_path,
                )
                library_feeds.append(library_path)
                if source.freshness_required and source_results[-1].get("status") == "fallback":
                    recovery_candidates.append((len(source_results) - 1, source, library_path))

            if recovery_candidates and not skip_crawl:
                if config.source_fallback_retry_delay_seconds > 0:
                    time.sleep(config.source_fallback_retry_delay_seconds)
                for result_index, source, library_path in recovery_candidates:
                    initial_result = dict(source_results[result_index])
                    try:
                        retry = run_safe_movie_source(
                            source_id=source.source_id,
                            output_dir=source_root,
                            target_count=source.count,
                            recovery_retry=True,
                        )
                        retry_payload = retry.__dict__
                        recovered = (
                            retry.status == "ran"
                            and retry.job_status == "success"
                            and retry.covered_count == source.count
                        )
                        if recovered:
                            export_source_library_feed(
                                db_path=retry.db_path,
                                source_id=source.source_id,
                                output_path=library_path,
                            )
                            source_results[result_index] = {
                                **retry_payload,
                                "status": "recovered",
                                "reason": "fallback_retry",
                                "freshness_required": True,
                                "initial_result": initial_result,
                            }
                        else:
                            source_results[result_index]["recovery"] = {
                                **retry_payload,
                                "succeeded": False,
                            }
                    except BaseException as retry_exc:
                        source_results[result_index]["recovery"] = {
                            "succeeded": False,
                            "error": {
                                "type": type(retry_exc).__name__,
                                "error_code": (
                                    retry_exc.error_code
                                    if isinstance(retry_exc, ResourceIndexError)
                                    else "UNEXPECTED"
                                ),
                                "message": str(retry_exc),
                            },
                        }

            def source_is_degraded(item: dict[str, Any]) -> bool:
                source_status = str(item.get("status") or "")
                source_reason = str(item.get("reason") or "")
                job_status = str(item.get("job_status") or "")
                return (
                    source_status in {"fallback", "paused"}
                    or job_status in {"pending", "paused", "partial"}
                    or (source_status == "skipped" and source_reason == "failure_backoff")
                )

            degraded = [item for item in source_results if source_is_degraded(item)]
            required_degraded = [item for item in degraded if item.get("freshness_required") is True]
            status["quality_status"] = "degraded" if degraded else "healthy"
            status["degraded_sources"] = [str(item.get("source_id") or "") for item in degraded]
            status["required_degraded_sources"] = [
                str(item.get("source_id") or "") for item in required_degraded
            ]
            status["stages"]["crawl"] = source_results
            _write_json(latest_status, status)

            aggregate_dir = run_dir / "aggregate"
            movie_feed = aggregate_dir / "movies.json"
            series_feed = aggregate_dir / "series.json"
            aggregate = aggregate_media_feeds(
                library_feeds,
                output_path=aggregate_dir / "all.json",
                movie_output_path=movie_feed,
                series_output_path=series_feed,
                quarantine_output_path=aggregate_dir / "quarantine.json",
                quality_output_path=aggregate_dir / "quality.json",
                limit=1_000_000,
            )
            status["stages"]["aggregate"] = aggregate["summary"]
            _write_json(latest_status, status)

            magnet_only = build_magnet_only_media_feeds(
                movie_feed_path=movie_feed,
                series_feed_path=series_feed,
                output_dir=aggregate_dir / "magnet-only",
            )
            movie_feed = Path(magnet_only["movie_feed"])
            series_feed = Path(magnet_only["series_feed"])
            status["stages"]["magnet_only"] = magnet_only
            _write_json(latest_status, status)

            status["stages"]["rating"] = _run_rating_stage(
                movie_feed=movie_feed,
                series_feed=series_feed,
                root=root,
                lookup_limit_per_feed=config.rating_lookup_limit_per_feed,
                skip_lookup=skip_ratings,
            )
            _write_json(latest_status, status)

            bundle_root = root / "bundles"
            movie_bundle = bundle_root / "movie"
            series_bundle = bundle_root / "series"
            movie_bundle_result = build_media_app_bundle(
                feed_path=movie_feed,
                output_dir=movie_bundle,
                content_kind="movie",
                skip_failed_covers=True,
            )
            series_bundle_result = build_media_app_bundle(
                feed_path=series_feed,
                output_dir=series_bundle,
                content_kind="series",
                skip_failed_covers=True,
            )
            movie_final_path = aggregate_dir / "movies-final.json"
            series_final_path = aggregate_dir / "series-final.json"
            movie_final = _filter_feed_to_bundle(movie_feed, movie_bundle, movie_final_path)
            series_final = _filter_feed_to_bundle(series_feed, series_bundle, series_final_path)
            movie_audit = audit_media_app_bundle(
                bundle_dir=movie_bundle,
                content_kind="movie",
                expected_count=len(movie_final["items"]),
            )
            series_audit = audit_media_app_bundle(
                bundle_dir=series_bundle,
                content_kind="series",
                expected_count=len(series_final["items"]),
            )
            status["stages"]["covers"] = {
                "movie": {**movie_bundle_result.__dict__, "audit": movie_audit},
                "series": {**series_bundle_result.__dict__, "audit": series_audit},
            }
            _write_json(latest_status, status)

            fingerprint = _content_fingerprint(movie_bundle, series_bundle)
            durable_state_path = status_dir / "state.json"
            durable_state = _load_json(durable_state_path) if durable_state_path.exists() else {}
            status["content_sha256"] = fingerprint
            status["movie_count"] = len(movie_final["items"])
            status["series_count"] = len(series_final["items"])
            status["resource_count"] = (
                sum(len(item.get("resources") or []) for item in movie_final["items"])
                + sum(len(item.get("resources") or []) for item in series_final["items"])
            )
            if not config.public_key_path.is_file():
                raise ResourceIndexError(CONFIG_ERROR, "media public signing key is missing", {})
            if config.previous_public_key_path is not None and not config.previous_public_key_path.is_file():
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "trusted previous media public key is missing",
                    {"path": str(config.previous_public_key_path)},
                )

            previous_current, previous_manifest_path, previous_current_path, control_stage = _reconcile_online_controls(
                config,
                run_dir,
                publish=publish,
            )
            status["stages"]["control_recovery"] = control_stage
            previous_revision = int(previous_current.get("pointer_revision") or 0)
            status["previous_revision"] = previous_revision
            if publish and not force_publish and durable_state.get("content_sha256") == fingerprint:
                expected_revision = durable_state.get("current_revision")
                expected_release_id = durable_state.get("release_id")
                if expected_revision == previous_revision and expected_release_id == previous_current.get("release_id"):
                    verification = [
                        _verify_public_control(config.r2_public_base, previous_current_path),
                        _verify_public_control(config.aliyun_public_base, previous_current_path),
                    ]
                    status["stages"]["verification"] = verification
                    status.update(
                        {
                            "status": "success",
                            "no_change": True,
                            "public_verified": True,
                            "current_revision": previous_revision,
                            "release_id": str(previous_current.get("release_id") or ""),
                            "pointer_sha256": hashlib.sha256(previous_current_path.read_bytes()).hexdigest(),
                            "finished_at": _iso(),
                        }
                    )
                    _write_json(latest_status, status)
                    return status
            if not config.private_key_path.is_file():
                raise ResourceIndexError(CONFIG_ERROR, "media private signing key is missing", {})

            release_output_dir = run_dir / "release-candidate"
            if publish:
                archived_pointers = _archive_unpromoted_pointer_candidates(
                    root / "releases" / "staging" / "pointers",
                    public_revision=previous_revision,
                    public_release_id=str(previous_current.get("release_id") or ""),
                    config=config,
                    evidence_dir=root / "evidence" / "unpromoted-pointers" / run_id,
                )
                status["stages"]["pointer_recovery"] = {
                    "status": "pass",
                    "archived_count": len(archived_pointers),
                    "archived": archived_pointers,
                }
                _write_json(latest_status, status)

            release_result = build_media_release(
                MediaReleaseConfig(
                    movie_feed_path=movie_final_path,
                    series_feed_path=series_final_path,
                    movie_cover_bundle=movie_bundle,
                    series_cover_bundle=series_bundle,
                    output_dir=release_output_dir,
                    private_key_path=config.private_key_path,
                    public_key_path=config.public_key_path,
                    pointer_revision=previous_revision + 1,
                    min_app_version=config.min_app_version,
                    page_size=config.page_size,
                    min_movies=config.min_movies,
                    min_series=config.min_series,
                    previous_manifest_path=previous_manifest_path,
                    previous_public_key_path=config.previous_public_key_path,
                )
            )
            release_dir = Path(release_result.release_dir)
            current_path = Path(release_result.current_path)
            status["stages"]["release"] = release_result.__dict__
            _write_json(latest_status, status)
            if publish and not force_publish:
                candidate_current = _load_json(current_path)
                if _pointer_semantics(candidate_current) == _pointer_semantics(previous_current):
                    verification = [
                        _verify_public_control(config.r2_public_base, previous_current_path),
                        _verify_public_control(config.aliyun_public_base, previous_current_path),
                    ]
                    status["stages"]["verification"] = verification
                    status.update(
                        {
                            "status": "success",
                            "no_change": True,
                            "public_verified": True,
                            "state_recovered": True,
                            "current_revision": previous_revision,
                            "release_id": str(previous_current.get("release_id") or ""),
                            "pointer_sha256": hashlib.sha256(previous_current_path.read_bytes()).hexdigest(),
                            "finished_at": _iso(),
                        }
                    )
                    _write_json(
                        durable_state_path,
                        {
                            "schema_version": "media-daily-state/1",
                            "content_sha256": fingerprint,
                            "current_revision": previous_revision,
                            "release_id": str(previous_current.get("release_id") or ""),
                            "updated_at": status["finished_at"],
                        },
                    )
                    _write_json(latest_status, status)
                    return status
            if not publish:
                status.update(
                    {
                        "status": "success",
                        "publish_candidate": True,
                        "candidate_verified": True,
                        "candidate_revision": previous_revision + 1,
                        "release_id": release_result.release_id,
                        "pointer_sha256": hashlib.sha256(current_path.read_bytes()).hexdigest(),
                        "finished_at": _iso(),
                    }
                )
                if not skip_crawl and not skip_ratings:
                    status["stages"]["soak"] = update_candidate_soak(
                        status_dir / "candidate-soak.json",
                        run_id=run_id,
                        run_date=_soak_date(),
                        success=True,
                        summary={
                            "content_sha256": fingerprint,
                            "candidate_revision": previous_revision + 1,
                            "release_id": release_result.release_id,
                            "movie_count": status["movie_count"],
                            "series_count": status["series_count"],
                            "resource_count": status["resource_count"],
                        },
                    )
                _write_json(latest_status, status)
                return status

            token = os.environ.get(config.worker_token_env, "")
            if len(token) < 32 or not config.worker_url.startswith("https://"):
                raise ResourceIndexError(CONFIG_ERROR, "production Worker credentials are missing", {})

            publish_config = MediaPublishConfig(
                release_dir=release_dir,
                current_path=current_path,
                public_key_path=config.public_key_path,
                receipt_dir=root / "receipts",
                max_workers=config.max_workers,
                deep_verify=False,
                upload_pointer_candidate=False,
            )
            local_backend = FilesystemPublisherBackend(config.public_root)
            r2_backend = WorkerR2PublisherBackend(
                worker_url=config.worker_url,
                upload_token=token,
                prefix="",
                allow_production_root=True,
                allow_current_promotion=True,
                max_attempts=4,
            )
            local_publish = publish_media_release(local_backend, publish_config)
            r2_publish = publish_media_release(r2_backend, publish_config)
            status["stages"]["publish"] = {
                "aliyun": local_publish.__dict__,
                "r2": r2_publish.__dict__,
            }
            _write_json(latest_status, status)

            candidate_bytes = current_path.read_bytes()
            r2_backend.promote_current(current_path)
            local_backend.promote_current(current_path)

            verification = [
                _verify_public_control(config.r2_public_base, current_path),
                _verify_public_control(config.aliyun_public_base, current_path),
            ]
            status["stages"]["verification"] = verification
            status.update(
                {
                    "status": "success",
                    "published": True,
                    "current_revision": previous_revision + 1,
                    "release_id": release_result.release_id,
                    "pointer_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
                    "finished_at": _iso(),
                }
            )
            _write_json(
                durable_state_path,
                {
                    "schema_version": "media-daily-state/1",
                    "content_sha256": fingerprint,
                    "current_revision": previous_revision + 1,
                    "release_id": release_result.release_id,
                    "updated_at": status["finished_at"],
                },
            )
            _write_json(latest_status, status)
            return status
    except BaseException as exc:
        if not status_owned:
            raise
        status.update(
            {
                "status": "failed",
                "finished_at": _iso(),
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "error_code": exc.error_code if isinstance(exc, ResourceIndexError) else "UNEXPECTED",
                    "context": exc.context if isinstance(exc, ResourceIndexError) else {},
                },
            }
        )
        if not publish and not skip_crawl and not skip_ratings:
            try:
                status["stages"]["soak"] = update_candidate_soak(
                    status_dir / "candidate-soak.json",
                    run_id=run_id,
                    run_date=_soak_date(),
                    success=False,
                    summary={
                        "content_sha256": status.get("content_sha256"),
                        "movie_count": status.get("movie_count"),
                        "series_count": status.get("series_count"),
                        "resource_count": status.get("resource_count"),
                    },
                    error=status["error"],
                )
            except Exception as soak_exc:
                status["stages"]["soak"] = {
                    "status": "warning",
                    "error": f"{type(soak_exc).__name__}: {soak_exc}",
                }
        _write_json(latest_status, status)
        raise
    finally:
        if status_owned:
            status_dir.mkdir(parents=True, exist_ok=True)
            history = status_dir / f"{run_id}.json"
            if latest_status.exists():
                shutil.copyfile(latest_status, history)
                shutil.copyfile(latest_status, mode_status)
            try:
                prune_media_state(
                    root,
                    RetentionConfig(
                        runs=config.retention_runs,
                        status_history=config.retention_status_history,
                        releases=config.retention_releases,
                        receipts=config.retention_receipts,
                    ),
                    protected_run_id=run_id,
                )
            except Exception as cleanup_exc:
                maintenance = status.setdefault("stages", {}).setdefault("maintenance", {})
                maintenance["cleanup_warning"] = {
                    "type": type(cleanup_exc).__name__,
                    "message": str(cleanup_exc),
                }
                if latest_status.exists():
                    _write_json(latest_status, status)
                    shutil.copyfile(latest_status, history)
                    shutil.copyfile(latest_status, mode_status)
