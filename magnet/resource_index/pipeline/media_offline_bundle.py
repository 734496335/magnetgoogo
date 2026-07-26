"""Build and audit fully offline movie/series App bundles without LLM involvement."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import urlparse

from PIL import Image

from magnet.resource_index.acquisition.http_client import LiveHttpClient
from magnet.resource_index.acquisition.policy import PhysicalRequestBudget
from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.normalize.cover import normalize_cover_image
from magnet.resource_index.normalize.media import is_generic_resource_title, label_has_anomaly
from magnet.resource_index.pipeline.latest_crawl import _atomic_write_json

CoverFetcher = Callable[[str, str | None], bytes]


@dataclass(frozen=True)
class MediaAppBundleResult:
    content_kind: str
    item_count: int
    cover_count: int
    resource_count: int
    downloaded: int
    reused: int
    failed: int
    http_requests: int
    feed_path: str
    cover_dir: str
    manifest_path: str


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            f"unable to read {label}",
            {"path": str(path)},
        ) from exc
    if not isinstance(value, dict):
        raise ResourceIndexError(CONFIG_ERROR, f"{label} must be an object", {"path": str(path)})
    return value


def _safe_relative_path(value: object) -> PurePosixPath | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return None
    return path


def _cover_candidates(item: dict[str, Any]) -> list[dict[str, str | None]]:
    output: list[dict[str, str | None]] = []
    seen: set[str] = set()
    raw_candidates = item.get("cover_candidates") or []
    if isinstance(raw_candidates, list):
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            if url and url not in seen:
                seen.add(url)
                output.append(
                    {
                        "url": url,
                        "referer": str(raw.get("referer") or item.get("detail_url") or "").strip() or None,
                    }
                )
    fallback = str(item.get("cover_source_url") or "").strip()
    if fallback and fallback not in seen:
        output.append(
            {
                "url": fallback,
                "referer": str(item.get("detail_url") or "").strip() or None,
            }
        )
    validated: list[dict[str, str | None]] = []
    for candidate in output:
        parsed = urlparse(str(candidate["url"]))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            continue
        referer = candidate["referer"]
        if referer:
            referer_parsed = urlparse(referer)
            if referer_parsed.scheme not in {"http", "https"} or not referer_parsed.hostname:
                referer = None
        validated.append({"url": str(candidate["url"]), "referer": referer})
    return validated


def _origin(url: str) -> str:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{parsed.hostname}:{port}"


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "media-cover-manifest/1", "assets": {}}
    manifest = _load_json(path, label="cover manifest")
    if manifest.get("schema_version") != "media-cover-manifest/1" or not isinstance(manifest.get("assets"), dict):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "cover manifest contract mismatch",
            {"path": str(path)},
        )
    return manifest


def _verified_asset(
    *,
    output_dir: Path,
    asset: object,
) -> dict[str, Any] | None:
    if not isinstance(asset, dict):
        return None
    relative = _safe_relative_path(asset.get("path"))
    digest = str(asset.get("content_hash") or "")
    if relative is None or len(digest) != 64:
        return None
    path = output_dir.joinpath(*relative.parts)
    if not path.exists() or not path.is_file():
        return None
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        return None
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
    except OSError:
        return None
    if width != int(asset.get("width") or 0) or height != int(asset.get("height") or 0):
        return None
    if len(payload) != int(asset.get("byte_size") or 0):
        return None
    return dict(asset)


def _app_summary(items: list[dict[str, Any]], *, cover_count: int) -> dict[str, Any]:
    return {
        "record_count": len(items),
        "target_count": len(items),
        "recommended_count": sum(1 for item in items if item.get("recommended")),
        "resource_count": sum(len(item.get("resources") or []) for item in items),
        "missing_urls": [],
        "snapshot_http_requests": 0,
        "detail_http_requests": 0,
        "database_movie_count": len(items),
        "cover_count": cover_count,
        "offline_ready": cover_count == len(items),
    }


def build_media_app_bundle(
    *,
    feed_path: str | Path,
    output_dir: str | Path,
    content_kind: str,
    expected_count: int | None = None,
    delay_seconds: float = 1.5,
    timeout_seconds: float = 30.0,
    fetcher: CoverFetcher | None = None,
) -> MediaAppBundleResult:
    """Build a content-addressed offline bundle from a strict media-feed/1 catalog."""
    if content_kind not in {"movie", "series"}:
        raise ResourceIndexError(CONFIG_ERROR, "unsupported offline media kind", {"content_kind": content_kind})
    source_path = Path(feed_path)
    feed = _load_json(source_path, label="media feed")
    if feed.get("schema_version") != "media-feed/1" or not isinstance(feed.get("items"), list):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media feed contract mismatch for offline bundle",
            {"path": str(source_path), "content_kind": content_kind},
        )
    feed_filter = feed.get("content_kind_filter")
    if feed_filter is not None and feed_filter != content_kind:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media feed kind filter does not match offline bundle target",
            {"path": str(source_path), "expected": content_kind, "actual": feed_filter},
        )

    candidate_items: list[dict[str, Any]] = []
    skipped_unsupported = 0
    for raw_item in feed["items"]:
        if not isinstance(raw_item, dict) or str(raw_item.get("content_kind") or "movie") != content_kind:
            continue
        supported_resources = [
            dict(resource)
            for resource in raw_item.get("resources") or []
            if isinstance(resource, dict)
            and str(resource.get("resource_type") or "") in {"magnet", "cloud"}
        ]
        if not supported_resources:
            skipped_unsupported += 1
            continue
        item = dict(raw_item)
        item["resources"] = supported_resources
        candidate_items.append(item)
        if expected_count is not None and len(candidate_items) >= expected_count:
            break

    if expected_count is not None and len(candidate_items) < expected_count:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media feed does not contain enough App-supported items",
            {
                "expected": expected_count,
                "available": len(candidate_items),
                "skipped_unsupported": skipped_unsupported,
                "content_kind": content_kind,
            },
        )
    items = candidate_items[:expected_count] if expected_count is not None else candidate_items
    if not items:
        raise ResourceIndexError(CONFIG_ERROR, "media feed has no App-supported items", {"content_kind": content_kind})

    target = Path(output_dir)
    cover_dir = target / "covers"
    manifest_path = target / "cover_manifest.json"
    cover_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(manifest_path)
    assets: dict[str, Any] = manifest["assets"]

    resolved: dict[int, dict[str, Any]] = {}
    pending: list[tuple[int, dict[str, Any], list[dict[str, str | None]]]] = []
    reused = 0
    for index, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            raise ResourceIndexError(CONFIG_ERROR, "media feed item must be an object", {"index": index})
        candidates = _cover_candidates(raw_item)
        selected = None
        for candidate in candidates:
            selected = _verified_asset(output_dir=target, asset=assets.get(str(candidate["url"])))
            if selected is not None:
                break
        if selected is not None:
            resolved[index] = selected
            reused += 1
        else:
            pending.append((index, raw_item, candidates))

    budget = PhysicalRequestBudget(limit=max(1, sum(max(1, len(candidates)) for _, _, candidates in pending) * 3))
    client = None
    if pending and fetcher is None:
        origins: set[str] = set()
        for _, _, candidates in pending:
            for candidate in candidates:
                origins.add(_origin(str(candidate["url"])))
                if candidate["referer"]:
                    origins.add(_origin(str(candidate["referer"])))
        if origins:
            client = LiveHttpClient(
                request_delay_seconds=delay_seconds,
                timeout_seconds=timeout_seconds,
                max_retries=2,
                allowed_origins=origins,
                request_budget=budget,
            )

    downloaded = 0
    failures: list[dict[str, Any]] = []
    for index, item, candidates in pending:
        selected = None
        attempts: list[dict[str, str]] = []
        for candidate in candidates:
            url = str(candidate["url"])
            referer = candidate["referer"]
            try:
                if fetcher is not None:
                    raw = fetcher(url, referer)
                elif client is not None:
                    response = client.get(
                        url,
                        referer=referer,
                        headers={
                            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                            "Cache-Control": "no-cache",
                        },
                    )
                    raw = response.content
                else:
                    raise ResourceIndexError(CONFIG_ERROR, "media item has no usable cover candidate", {})
                encoded, mime_type, width, height, digest = normalize_cover_image(raw)
                relative = PurePosixPath("covers") / f"{digest}.jpg"
                path = target.joinpath(*relative.parts)
                if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    _atomic_write_bytes(path, encoded)
                selected = {
                    "path": relative.as_posix(),
                    "source_url": url,
                    "mime_type": mime_type,
                    "content_hash": digest,
                    "width": width,
                    "height": height,
                    "byte_size": len(encoded),
                }
                assets[url] = selected
                manifest["assets"] = assets
                _atomic_write_json(manifest_path, manifest)
                downloaded += 1
                break
            except ResourceIndexError as exc:
                attempts.append({"url": url, "error_code": exc.error_code})
        if selected is None:
            failures.append(
                {
                    "index": index,
                    "movie_id": item.get("movie_id"),
                    "title": item.get("title"),
                    "attempts": attempts,
                }
            )
        else:
            resolved[index] = selected

    if failures:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "offline media covers are incomplete",
            {"content_kind": content_kind, "failed": len(failures), "examples": failures[:10]},
        )

    app_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items):
        asset = resolved[index]
        item = dict(raw_item)
        item["rank"] = index + 1
        item["content_kind"] = content_kind
        item["cover_asset_path"] = asset["path"]
        item["cover_width"] = asset["width"]
        item["cover_height"] = asset["height"]
        item["cover_content_hash"] = asset["content_hash"]
        item["cover_byte_size"] = asset["byte_size"]
        app_items.append(item)

    app_feed = {
        "schema_version": "media-app-feed/1",
        "source_id": f"{content_kind}-offline",
        "content_kind": content_kind,
        "generated_at": feed.get("generated_at"),
        "snapshot_captured_at": next(
            (
                source.get("snapshot_captured_at")
                for source in feed.get("sources") or []
                if isinstance(source, dict) and source.get("snapshot_captured_at")
            ),
            None,
        ),
        "items": app_items,
        "summary": _app_summary(app_items, cover_count=len(app_items)),
        "quality": feed.get("quality"),
    }
    feed_output = target / "feed.json"
    _atomic_write_json(feed_output, app_feed)
    return MediaAppBundleResult(
        content_kind=content_kind,
        item_count=len(app_items),
        cover_count=len(app_items),
        resource_count=app_feed["summary"]["resource_count"],
        downloaded=downloaded,
        reused=reused,
        failed=0,
        http_requests=budget.used if fetcher is None else downloaded,
        feed_path=str(feed_output),
        cover_dir=str(cover_dir),
        manifest_path=str(manifest_path),
    )


def audit_media_app_bundle(
    *,
    bundle_dir: str | Path,
    content_kind: str,
    expected_count: int | None = None,
    raise_on_error: bool = True,
) -> dict[str, Any]:
    """Audit local files and semantic media invariants without network access."""
    root = Path(bundle_dir)
    feed = _load_json(root / "feed.json", label="offline media App feed")
    errors: list[dict[str, Any]] = []
    if feed.get("schema_version") != "media-app-feed/1":
        errors.append({"code": "SCHEMA_MISMATCH"})
    if feed.get("content_kind") != content_kind:
        errors.append({"code": "CONTENT_KIND_MISMATCH", "actual": feed.get("content_kind")})
    items = feed.get("items")
    if not isinstance(items, list):
        items = []
        errors.append({"code": "ITEMS_INVALID"})
    if expected_count is not None and len(items) != expected_count:
        errors.append({"code": "COUNT_MISMATCH", "expected": expected_count, "actual": len(items)})

    seen_ids: set[str] = set()
    total_resources = 0
    cover_bytes = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append({"code": "ITEM_INVALID", "index": index})
            continue
        movie_id = str(item.get("movie_id") or "")
        if not movie_id or movie_id in seen_ids:
            errors.append({"code": "MOVIE_ID_INVALID_OR_DUPLICATE", "index": index, "movie_id": movie_id})
        seen_ids.add(movie_id)
        if int(item.get("rank") or 0) != index + 1:
            errors.append({"code": "RANK_INVALID", "index": index, "rank": item.get("rank")})
        for field in ("genres", "countries"):
            for value in item.get(field) or []:
                if label_has_anomaly(value):
                    errors.append({"code": "LABEL_ANOMALY", "index": index, "field": field, "value": value})
        relative = _safe_relative_path(item.get("cover_asset_path"))
        if relative is None:
            errors.append({"code": "COVER_PATH_INVALID", "index": index})
        else:
            path = root.joinpath(*relative.parts)
            if not path.exists():
                errors.append({"code": "COVER_MISSING", "index": index, "path": relative.as_posix()})
            else:
                payload = path.read_bytes()
                cover_bytes += len(payload)
                digest = hashlib.sha256(payload).hexdigest()
                if digest != item.get("cover_content_hash"):
                    errors.append({"code": "COVER_HASH_MISMATCH", "index": index})
                try:
                    with Image.open(path) as image:
                        width, height = image.size
                        image.verify()
                    if width != item.get("cover_width") or height != item.get("cover_height"):
                        errors.append({"code": "COVER_DIMENSION_MISMATCH", "index": index})
                except OSError:
                    errors.append({"code": "COVER_INVALID", "index": index})
        resources = item.get("resources") or []
        if not resources:
            errors.append({"code": "RESOURCE_EMPTY", "index": index})
        total_resources += len(resources)
        target_season = item.get("season_number") if isinstance(item.get("season_number"), int) else None
        for resource_index, resource in enumerate(resources):
            if not isinstance(resource, dict):
                errors.append({"code": "RESOURCE_INVALID", "index": index, "resource_index": resource_index})
                continue
            if target_season is not None and resource.get("season_number") != target_season:
                errors.append(
                    {
                        "code": "CROSS_SEASON_RESOURCE",
                        "index": index,
                        "resource_index": resource_index,
                        "target": target_season,
                        "actual": resource.get("season_number"),
                    }
                )
            if resource.get("episode_label") and is_generic_resource_title(resource.get("display_title")):
                errors.append(
                    {
                        "code": "EPISODE_TITLE_LOST",
                        "index": index,
                        "resource_index": resource_index,
                    }
                )

    summary = feed.get("summary") if isinstance(feed.get("summary"), dict) else {}
    if summary.get("record_count") != len(items) or summary.get("cover_count") != len(items):
        errors.append({"code": "SUMMARY_COUNT_MISMATCH"})
    if summary.get("resource_count") != total_resources:
        errors.append({"code": "SUMMARY_RESOURCE_MISMATCH"})
    if summary.get("offline_ready") is not True:
        errors.append({"code": "OFFLINE_READY_FALSE"})

    report = {
        "schema_version": "media-app-bundle-audit/1",
        "status": "pass" if not errors else "fail",
        "content_kind": content_kind,
        "record_count": len(items),
        "cover_count": len(items) - sum(1 for error in errors if error["code"] in {"COVER_PATH_INVALID", "COVER_MISSING", "COVER_HASH_MISMATCH", "COVER_INVALID"}),
        "resource_count": total_resources,
        "cover_bytes": cover_bytes,
        "error_count": len(errors),
        "errors": errors[:100],
    }
    if errors and raise_on_error:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "offline media App bundle audit failed",
            {"content_kind": content_kind, "error_count": len(errors), "examples": errors[:10]},
        )
    return report
