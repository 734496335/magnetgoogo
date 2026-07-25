"""Download SixV movie covers into SQLite and export an App-ready offline bundle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageOps, UnidentifiedImageError

from magnet.resource_index.acquisition.http_client import LiveHttpClient
from magnet.resource_index.acquisition.policy import PhysicalRequestBudget
from magnet.resource_index.adapters.sixv.parser import (
    normalize_movie_genres,
    normalize_movie_title,
)
from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.store.movie_repository import MovieRepository
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

_ALLOWED_COVER_HOSTS = {"tu.66tutup.com:667", "www.66tutup.com"}
_MAX_SOURCE_BYTES = 12 * 1024 * 1024
_MAX_WIDTH = 720
_MAX_HEIGHT = 1080
_JPEG_QUALITY = 84


@dataclass(frozen=True)
class MovieCoverSyncResult:
    total_movies: int
    already_stored: int
    downloaded: int
    failed: int
    http_requests: int


@dataclass(frozen=True)
class MovieAppBundleResult:
    item_count: int
    recommended_count: int
    cover_count: int
    feed_path: str
    cover_dir: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _allowed_origins(rows: list[dict[str, Any]]) -> set[str]:
    origins = {"https://www.6v520.com:443", "http://www.6v520.com:80"}
    for row in rows:
        parsed = urlparse(str(row["cover_source_url"]))
        netloc = parsed.netloc.lower()
        if parsed.scheme not in {"http", "https"} or netloc not in _ALLOWED_COVER_HOSTS:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie cover URL is outside the SixV cover allowlist",
                {"movie_id": row["movie_id"], "cover_host": netloc},
            )
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        origins.add(f"{parsed.scheme}://{parsed.hostname}:{port}")
    return origins


def _normalize_cover(raw: bytes) -> tuple[bytes, str, int, int, str]:
    if not raw or len(raw) > _MAX_SOURCE_BYTES:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "movie cover payload is empty or too large",
            {"byte_size": len(raw)},
        )
    try:
        with Image.open(BytesIO(raw)) as opened:
            opened.verify()
        with Image.open(BytesIO(raw)) as opened:
            image = ImageOps.exif_transpose(opened)
            image.thumbnail((_MAX_WIDTH, _MAX_HEIGHT), Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "L"}:
                background = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A") if "A" in image.getbands() else None
                background.paste(image.convert("RGB"), mask=alpha)
                image = background
            elif image.mode == "L":
                image = image.convert("RGB")
            output = BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=_JPEG_QUALITY,
                optimize=True,
                progressive=True,
            )
            encoded = output.getvalue()
            width, height = image.size
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "movie cover payload is not a valid image",
            {},
        ) from exc
    digest = hashlib.sha256(encoded).hexdigest()
    return encoded, "image/jpeg", width, height, digest


def sync_movie_covers(
    repo: SqliteResourceRepository,
    *,
    source_id: str = "sixv",
    delay_seconds: float = 1.5,
    timeout_seconds: float = 30.0,
) -> MovieCoverSyncResult:
    repo.init_schema()
    movie_repo = MovieRepository(repo)
    rows = movie_repo.cover_targets(source_id=source_id)
    if not rows:
        return MovieCoverSyncResult(0, 0, 0, 0, 0)

    pending = [row for row in rows if not row["cover_stored"]]
    already_stored = len(rows) - len(pending)
    if not pending:
        return MovieCoverSyncResult(len(rows), already_stored, 0, 0, 0)

    budget = PhysicalRequestBudget(limit=max(1, len(pending) * 3))
    client = LiveHttpClient(
        request_delay_seconds=delay_seconds,
        timeout_seconds=timeout_seconds,
        max_retries=2,
        allowed_origins=_allowed_origins(rows),
        request_budget=budget,
    )
    downloaded = 0
    failed = 0
    for row in pending:
        try:
            response = client.get(
                row["cover_source_url"],
                referer=row["detail_url"],
                headers={
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    "Cache-Control": "no-cache",
                },
            )
            encoded, mime_type, width, height, digest = _normalize_cover(response.content)
            movie_repo.upsert_cover_asset(
                movie_id=row["movie_id"],
                source_url=row["cover_source_url"],
                mime_type=mime_type,
                content_hash=digest,
                width=width,
                height=height,
                image_blob=encoded,
                fetched_at=_utc_now(),
            )
            downloaded += 1
        except ResourceIndexError:
            failed += 1
    return MovieCoverSyncResult(
        total_movies=len(rows),
        already_stored=already_stored,
        downloaded=downloaded,
        failed=failed,
        http_requests=budget.used,
    )


def export_movie_app_bundle(
    repo: SqliteResourceRepository,
    *,
    feed_path: str | Path,
    output_dir: str | Path,
) -> MovieAppBundleResult:
    repo.init_schema()
    source_path = Path(feed_path)
    try:
        feed = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "unable to read SixV movie feed",
            {"feed_path": str(source_path)},
        ) from exc
    if feed.get("schema_version") != "movie-feed/1" or feed.get("source_id") != "sixv":
        raise ResourceIndexError(
            CONFIG_ERROR,
            "SixV movie feed contract mismatch",
            {"feed_path": str(source_path)},
        )

    target = Path(output_dir)
    cover_dir = target / "covers"
    cover_dir.mkdir(parents=True, exist_ok=True)
    movie_repo = MovieRepository(repo)
    items = feed.get("items")
    if not isinstance(items, list):
        raise ResourceIndexError(CONFIG_ERROR, "movie feed items must be an array", {})

    exported_hashes: set[str] = set()
    app_items: list[dict[str, Any]] = []
    for expected_rank, item in enumerate(items, start=1):
        if int(item.get("rank") or 0) != expected_rank:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie feed ranks are not continuous",
                {"rank": item.get("rank"), "expected_rank": expected_rank},
            )
        asset = movie_repo.get_cover_asset(str(item.get("movie_id") or ""))
        if asset is None:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie cover is missing from SQLite",
                {"movie_id": item.get("movie_id"), "rank": expected_rank},
            )
        blob = bytes(asset["image_blob"])
        digest = hashlib.sha256(blob).hexdigest()
        if digest != asset["content_hash"]:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie cover hash mismatch",
                {"movie_id": item.get("movie_id")},
            )
        filename = f"{digest}.jpg"
        cover_path = cover_dir / filename
        if digest not in exported_hashes or not cover_path.exists():
            cover_path.write_bytes(blob)
            exported_hashes.add(digest)
        app_item = dict(item)
        app_item["title"] = normalize_movie_title(
            str(item.get("title") or item.get("listing_title") or ""),
            str(item.get("listing_title") or ""),
        )
        app_item["genres"] = list(
            normalize_movie_genres(
                list(item.get("genres") or ()),
                str(item.get("listing_title") or ""),
            )
        )
        if app_item["title"] != item.get("title") or app_item["genres"] != item.get("genres"):
            repo.conn.execute(
                "UPDATE movie_items SET title = ?, genres_json = ?, updated_at = ? WHERE movie_id = ?",
                (
                    app_item["title"],
                    json.dumps(app_item["genres"], ensure_ascii=False),
                    _utc_now().isoformat().replace("+00:00", "Z"),
                    item.get("movie_id"),
                ),
            )
        app_item["cover_asset_path"] = f"covers/{filename}"
        app_item["cover_width"] = int(asset["width"])
        app_item["cover_height"] = int(asset["height"])
        app_items.append(app_item)

    app_feed = dict(feed)
    app_feed["schema_version"] = "movie-app-feed/1"
    app_feed["items"] = app_items
    summary = dict(feed.get("summary") or {})
    summary["cover_count"] = len(app_items)
    summary["offline_ready"] = True
    app_feed["summary"] = summary
    app_feed_path = target / "feed.json"
    app_feed_path.write_text(
        json.dumps(app_feed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return MovieAppBundleResult(
        item_count=len(app_items),
        recommended_count=sum(1 for item in app_items if item.get("recommended")),
        cover_count=len(app_items),
        feed_path=str(app_feed_path),
        cover_dir=str(cover_dir),
    )
