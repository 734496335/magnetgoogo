from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.release.protocol import canonical_json_bytes

_INFO_HASH_RE = re.compile(r"^[0-9a-f]{40}$")


def _load_feed(path: Path, expected_kind: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(CONFIG_ERROR, "failed to read media feed", {"path": str(path)}) from exc
    if value.get("schema_version") != "media-feed/1" or not isinstance(value.get("items"), list):
        raise ResourceIndexError(CONFIG_ERROR, "media feed contract mismatch", {"path": str(path)})
    actual_kind = value.get("content_kind_filter")
    if actual_kind not in {None, expected_kind}:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media feed content kind mismatch",
            {"path": str(path), "expected": expected_kind, "actual": actual_kind},
        )
    return value


def _magnet_info_hash(resource: dict[str, Any], context: str) -> str:
    url = str(resource.get("url") or "").strip()
    if not url.casefold().startswith("magnet:?"):
        raise ResourceIndexError(CONFIG_ERROR, "magnet resource URL is invalid", {"context": context, "url": url})
    values = parse_qs(urlsplit(url).query).get("xt") or []
    hashes = [value.removeprefix("urn:btih:").casefold() for value in values if value.casefold().startswith("urn:btih:")]
    if len(hashes) != 1 or not _INFO_HASH_RE.fullmatch(hashes[0]):
        raise ResourceIndexError(CONFIG_ERROR, "magnet resource info hash is invalid", {"context": context, "url": url})
    declared = str(resource.get("info_hash") or "").strip().casefold()
    if declared and declared != hashes[0]:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "magnet resource info hash does not match URL",
            {"context": context, "declared": declared, "actual": hashes[0]},
        )
    return hashes[0]


def _filter_feed(
    feed: dict[str, Any],
    kind: str,
    seen_hashes: set[str],
) -> tuple[dict[str, Any], dict[str, int]]:
    items: list[dict[str, Any]] = []
    input_resources = 0
    cloud_resources = 0
    dropped_items = 0
    for item_index, raw_item in enumerate(feed["items"]):
        if not isinstance(raw_item, dict):
            raise ResourceIndexError(CONFIG_ERROR, "media feed item must be an object", {"index": item_index})
        resources = raw_item.get("resources") or []
        if not isinstance(resources, list):
            raise ResourceIndexError(CONFIG_ERROR, "media resources must be an array", {"index": item_index})
        input_resources += len(resources)
        magnets: list[dict[str, Any]] = []
        local_hashes: set[str] = set()
        for resource_index, raw_resource in enumerate(resources):
            if not isinstance(raw_resource, dict):
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "media resource must be an object",
                    {"item_index": item_index, "resource_index": resource_index},
                )
            if str(raw_resource.get("resource_type") or "").casefold() != "magnet":
                cloud_resources += 1
                continue
            context = f"items[{item_index}].resources[{resource_index}]"
            info_hash = _magnet_info_hash(raw_resource, context)
            if info_hash in local_hashes or info_hash in seen_hashes:
                raise ResourceIndexError(CONFIG_ERROR, "duplicate magnet info hash", {"context": context, "info_hash": info_hash})
            local_hashes.add(info_hash)
            seen_hashes.add(info_hash)
            resource = dict(raw_resource)
            resource["resource_type"] = "magnet"
            resource["provider"] = "magnet"
            resource["info_hash"] = info_hash
            magnets.append(resource)
        if not magnets:
            dropped_items += 1
            continue
        item = dict(raw_item)
        item["rank"] = len(items) + 1
        item["resources"] = magnets
        items.append(item)

    output = dict(feed)
    output["content_kind_filter"] = kind
    output["items"] = items
    summary = dict(output.get("summary") or {})
    summary["record_count"] = len(items)
    summary["movie_count"] = len(items) if kind == "movie" else 0
    summary["series_count"] = len(items) if kind == "series" else 0
    summary["resource_count"] = sum(len(item["resources"]) for item in items)
    summary["dropped_zero_resource_count"] = int(summary.get("dropped_zero_resource_count") or 0) + dropped_items
    output["summary"] = summary
    quality = dict(output.get("quality") or {})
    quality["record_count"] = len(items)
    quality["resource_count"] = summary["resource_count"]
    quality["empty_resource_item_count"] = 0
    quality["rating_required"] = False
    quality["status"] = "pass"
    output["quality"] = quality
    return output, {
        "input_item_count": len(feed["items"]),
        "output_item_count": len(items),
        "dropped_zero_magnet_item_count": dropped_items,
        "input_resource_count": input_resources,
        "removed_non_magnet_resource_count": cloud_resources,
        "magnet_resource_count": summary["resource_count"],
    }


def _item_cover_urls(item: dict[str, Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for candidate in item.get("cover_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        url = str(candidate.get("url") or "").strip()
        if url and url not in seen:
            seen.add(url)
            output.append(url)
    fallback = str(item.get("cover_source_url") or "").strip()
    if fallback and fallback not in seen:
        output.append(fallback)
    return output


def seed_media_cover_bundle_cache(
    *,
    feed_path: str | Path,
    output_dir: str | Path,
    probe_dirs: list[str | Path],
) -> dict[str, Any]:
    feed = _load_feed(Path(feed_path).expanduser().resolve(), str(json.loads(Path(feed_path).read_text(encoding="utf-8-sig")).get("content_kind_filter") or "movie"))
    available: dict[str, tuple[Path, dict[str, Any]]] = {}
    for raw_dir in probe_dirs:
        probe_dir = Path(raw_dir).expanduser().resolve()
        manifest_path = probe_dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResourceIndexError(CONFIG_ERROR, "failed to read source cover manifest", {"path": str(manifest_path)}) from exc
        if manifest.get("schema_version") != "source-cover-assets/1" or not isinstance(manifest.get("assets"), dict):
            raise ResourceIndexError(CONFIG_ERROR, "source cover manifest contract mismatch", {"path": str(manifest_path)})
        for url, raw_asset in manifest["assets"].items():
            if not isinstance(url, str) or not isinstance(raw_asset, dict):
                continue
            source_path = probe_dir / str(raw_asset.get("path") or "")
            available[url] = (source_path, raw_asset)

    target = Path(output_dir).expanduser().resolve()
    cover_dir = target / "covers"
    cover_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[str, dict[str, Any]] = {}
    covered_items = 0
    missing_items: list[dict[str, Any]] = []
    unique_hashes: set[str] = set()
    for item in feed["items"]:
        if not isinstance(item, dict):
            continue
        matched = False
        for url in _item_cover_urls(item):
            source = available.get(url)
            if source is None:
                continue
            source_path, raw_asset = source
            digest = str(raw_asset.get("content_hash") or "")
            if len(digest) != 64 or not source_path.is_file():
                continue
            payload = source_path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != digest:
                raise ResourceIndexError(CONFIG_ERROR, "cached source cover hash mismatch", {"path": str(source_path), "url": url})
            try:
                with Image.open(source_path) as image:
                    width, height = image.size
                    image.verify()
            except OSError as exc:
                raise ResourceIndexError(CONFIG_ERROR, "cached source cover cannot be decoded", {"path": str(source_path)}) from exc
            if width != int(raw_asset.get("width") or 0) or height != int(raw_asset.get("height") or 0):
                raise ResourceIndexError(CONFIG_ERROR, "cached source cover dimensions mismatch", {"path": str(source_path)})
            destination = cover_dir / f"{digest}.jpg"
            if not destination.exists():
                shutil.copyfile(source_path, destination)
            assets[url] = {
                "path": f"covers/{digest}.jpg",
                "source_url": url,
                "mime_type": str(raw_asset.get("mime_type") or "image/jpeg"),
                "content_hash": digest,
                "width": width,
                "height": height,
                "byte_size": len(payload),
            }
            unique_hashes.add(digest)
            matched = True
        if matched:
            covered_items += 1
        else:
            missing_items.append({"movie_id": item.get("movie_id"), "title": item.get("title")})
    if missing_items:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media feed has covers missing from verified source caches",
            {"missing_count": len(missing_items), "examples": missing_items[:10]},
        )
    manifest = {"schema_version": "media-cover-manifest/1", "assets": assets}
    manifest_path = target / "cover_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    report = {
        "schema_version": "media-cover-cache-seed/1",
        "status": "pass",
        "item_count": len(feed["items"]),
        "covered_item_count": covered_items,
        "asset_url_count": len(assets),
        "unique_asset_count": len(unique_hashes),
        "manifest_path": str(manifest_path),
    }
    (target / "cover_cache_seed_report.json").write_bytes(canonical_json_bytes(report))
    return report


def build_magnet_only_media_feeds(
    *,
    movie_feed_path: str | Path,
    series_feed_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    movie_feed = _load_feed(Path(movie_feed_path).expanduser().resolve(), "movie")
    series_feed = _load_feed(Path(series_feed_path).expanduser().resolve(), "series")
    seen_hashes: set[str] = set()
    movies, movie_stats = _filter_feed(movie_feed, "movie", seen_hashes)
    series, series_stats = _filter_feed(series_feed, "series", seen_hashes)
    movie_count = len(movies["items"])
    series_count = len(series["items"])
    for value in (movies, series):
        summary = dict(value.get("summary") or {})
        summary["available_movie_count"] = movie_count
        summary["available_series_count"] = series_count
        value["summary"] = summary
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    movie_output = root / "movies-magnet-only.json"
    series_output = root / "series-magnet-only.json"
    report_output = root / "magnet-only-report.json"
    movie_output.write_bytes(canonical_json_bytes(movies))
    series_output.write_bytes(canonical_json_bytes(series))
    report = {
        "schema_version": "media-magnet-only-report/1",
        "status": "pass",
        "movie": movie_stats,
        "series": series_stats,
        "total_item_count": movie_count + series_count,
        "total_magnet_resource_count": movie_stats["magnet_resource_count"] + series_stats["magnet_resource_count"],
        "movie_feed": str(movie_output),
        "series_feed": str(series_output),
    }
    report_output.write_bytes(canonical_json_bytes(report))
    return {**report, "report_path": str(report_output)}
