"""Resumable full-cover verification for one source feed."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import urlparse

from magnet.resource_index.acquisition.http_client import LiveHttpClient
from magnet.resource_index.acquisition.policy import PhysicalRequestBudget
from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.normalize.cover import normalize_cover_image
from magnet.resource_index.pipeline.latest_crawl import _atomic_write_json

CoverFetcher = Callable[[str, str | None], bytes]


@dataclass(frozen=True)
class SourceCoverProbeResult:
    status: str
    source_id: str
    expected_count: int
    verified_count: int
    downloaded_count: int
    reused_count: int
    failed_count: int
    unique_cover_asset_count: int
    unique_cover_ratio: float
    http_requests: int
    report_path: str
    cover_dir: str


def _load_feed(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "failed to read source cover feed",
            {"path": str(path), "error": type(exc).__name__},
        ) from exc
    if payload.get("schema_version") != "movie-feed/1" or not isinstance(payload.get("items"), list):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "source cover feed contract mismatch",
            {"path": str(path)},
        )
    return payload


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ResourceIndexError(CONFIG_ERROR, "cover URL origin is invalid", {"url": url})
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{parsed.hostname}:{port}"


def _asset_valid(root: Path, asset: object) -> bool:
    if not isinstance(asset, dict):
        return False
    relative = PurePosixPath(str(asset.get("path") or ""))
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return False
    path = root.joinpath(*relative.parts)
    if not path.is_file():
        return False
    payload = path.read_bytes()
    return (
        len(payload) == int(asset.get("byte_size") or -1)
        and hashlib.sha256(payload).hexdigest() == asset.get("content_hash")
    )


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def probe_source_covers(
    *,
    feed_path: str | Path,
    output_dir: str | Path,
    expected_count: int = 100,
    delay_seconds: float = 1.0,
    timeout_seconds: float = 30.0,
    minimum_unique_ratio: float = 0.9,
    fetcher: CoverFetcher | None = None,
) -> SourceCoverProbeResult:
    if expected_count <= 0:
        raise ResourceIndexError(CONFIG_ERROR, "cover probe expected_count must be positive", {})
    if not 0 < minimum_unique_ratio <= 1:
        raise ResourceIndexError(CONFIG_ERROR, "cover probe unique ratio must be within (0, 1]", {})
    feed_file = Path(feed_path).expanduser().resolve()
    feed = _load_feed(feed_file)
    source_id = str(feed.get("source_id") or "")
    items = [item for item in feed["items"] if isinstance(item, dict)]
    if len(items) != expected_count:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "cover probe feed count mismatch",
            {"expected": expected_count, "actual": len(items), "source_id": source_id},
        )
    root = Path(output_dir).expanduser().resolve()
    cover_dir = root / "covers"
    manifest_path = root / "manifest.json"
    report_path = root / "report.json"
    cover_dir.mkdir(parents=True, exist_ok=True)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        manifest = {}
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), dict) else {}

    pending: list[tuple[int, dict[str, Any], str, str | None]] = []
    reused = 0
    verified = 0
    failures: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        url = str(item.get("cover_source_url") or "").strip()
        referer = str(item.get("detail_url") or "").strip() or None
        if not url:
            failures.append({"index": index, "movie_id": item.get("movie_id"), "title": item.get("title"), "reason": "missing_url"})
            continue
        asset = assets.get(url)
        if _asset_valid(root, asset):
            reused += 1
            verified += 1
        else:
            pending.append((index, item, url, referer))

    budget = PhysicalRequestBudget(limit=max(1, len(pending) * 3))
    client = None
    if pending and fetcher is None:
        origins: set[str] = set()
        for _, _, url, referer in pending:
            origins.add(_origin(url))
            if referer:
                origins.add(_origin(referer))
        client = LiveHttpClient(
            request_delay_seconds=delay_seconds,
            timeout_seconds=timeout_seconds,
            max_retries=2,
            allowed_origins=origins,
            request_budget=budget,
        )

    downloaded = 0
    for index, item, url, referer in pending:
        try:
            if fetcher is not None:
                raw = fetcher(url, referer)
            elif client is not None:
                raw = client.get(
                    url,
                    referer=referer,
                    headers={"Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"},
                ).content
            else:
                raise ResourceIndexError(CONFIG_ERROR, "cover probe has no fetch path", {})
            encoded, mime_type, width, height, digest = normalize_cover_image(raw)
            relative = PurePosixPath("covers") / f"{digest}.jpg"
            path = root.joinpath(*relative.parts)
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                _write_bytes(path, encoded)
            assets[url] = {
                "path": relative.as_posix(),
                "mime_type": mime_type,
                "content_hash": digest,
                "width": width,
                "height": height,
                "byte_size": len(encoded),
            }
            manifest = {"schema_version": "source-cover-assets/1", "source_id": source_id, "assets": assets}
            _atomic_write_json(manifest_path, manifest)
            downloaded += 1
            verified += 1
        except ResourceIndexError as exc:
            failures.append(
                {
                    "index": index,
                    "movie_id": item.get("movie_id"),
                    "title": item.get("title"),
                    "url": url,
                    "reason": exc.error_code,
                }
            )

    current_hashes = {
        str(asset.get("content_hash"))
        for item in items
        if isinstance((asset := assets.get(str(item.get("cover_source_url") or "").strip())), dict)
        and _asset_valid(root, asset)
    }
    unique_cover_asset_count = len(current_hashes)
    unique_cover_ratio = unique_cover_asset_count / expected_count
    report = {
        "schema_version": "source-cover-probe/1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": (
            "pass"
            if verified == expected_count and not failures and unique_cover_ratio >= minimum_unique_ratio
            else "fail"
        ),
        "source_id": source_id,
        "expected_count": expected_count,
        "verified_count": verified,
        "downloaded_count": downloaded,
        "reused_count": reused,
        "failed_count": len(failures),
        "http_requests": budget.used if fetcher is None else downloaded,
        "minimum_unique_ratio": minimum_unique_ratio,
        "unique_cover_asset_count": unique_cover_asset_count,
        "unique_cover_ratio": unique_cover_ratio,
        "failures": failures,
    }
    _atomic_write_json(report_path, report)
    return SourceCoverProbeResult(
        status=report["status"],
        source_id=source_id,
        expected_count=expected_count,
        verified_count=verified,
        downloaded_count=downloaded,
        reused_count=reused,
        failed_count=len(failures),
        unique_cover_asset_count=unique_cover_asset_count,
        unique_cover_ratio=unique_cover_ratio,
        http_requests=report["http_requests"],
        report_path=str(report_path),
        cover_dir=str(cover_dir),
    )
