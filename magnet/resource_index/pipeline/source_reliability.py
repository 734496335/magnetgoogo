"""Deterministic reliability audit for one durable media source crawl."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.normalize.magnets import normalize_magnet_uri
from magnet.resource_index.pipeline.latest_crawl import _atomic_write_json
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

_APP_RESOURCE_TYPES = {"magnet", "cloud"}
_KNOWN_RESOURCE_TYPES = _APP_RESOURCE_TYPES | {"download", "player", "torrent"}
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_FRAGMENT = re.compile(r"<\s*/?\s*(?:html|body|script|iframe|a|img)\b", re.IGNORECASE)
_MOJIBAKE_MARKERS = ("\ufffd", "锟斤拷", "Ã", "Â")


def _load_feed(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "failed to read source reliability feed",
            {"path": str(path), "error": type(exc).__name__},
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "source reliability feed contract mismatch",
            {"path": str(path)},
        )
    return payload


def _resource_identity(resource: dict[str, Any]) -> str | None:
    info_hash = str(resource.get("info_hash") or "").strip().lower()
    if info_hash:
        return f"hash:{info_hash}"
    url = str(resource.get("url") or resource.get("resource_url") or "").strip()
    return f"url:{url}" if url else None


def _valid_http_url(value: object) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _valid_download_url(value: object) -> bool:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https", "ftp"} and parsed.hostname:
        return True
    if raw.casefold().startswith("thunder://") and len(raw) > len("thunder://"):
        return True
    return raw.casefold().startswith("ed2k://|") and raw.endswith("|")


def _text_has_anomaly(value: object) -> bool:
    text = str(value or "")
    return bool(
        not text.strip()
        or _CONTROL_CHARACTERS.search(text)
        or _HTML_FRAGMENT.search(text)
        or any(marker in text for marker in _MOJIBAKE_MARKERS)
    )


def audit_source_reliability(
    *,
    source_id: str,
    db_path: str | Path,
    feed_path: str | Path,
    expected_count: int = 100,
    output_path: str | Path | None = None,
    require_app_resources: bool = False,
) -> dict[str, Any]:
    if expected_count <= 0:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "source reliability expected_count must be positive",
            {"expected_count": expected_count},
        )
    database = Path(db_path).expanduser().resolve()
    feed_file = Path(feed_path).expanduser().resolve()
    feed = _load_feed(feed_file)
    items = [item for item in feed["items"] if isinstance(item, dict)]
    feed_summary = feed.get("summary") if isinstance(feed.get("summary"), dict) else {}
    discovery_target_count = int(feed_summary.get("discovery_target_count") or expected_count)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if discovery_target_count < expected_count:
        errors.append(
            {
                "code": "DISCOVERY_COUNT_BELOW_FEED_COUNT",
                "expected_at_least": expected_count,
                "actual": discovery_target_count,
            }
        )

    if feed.get("schema_version") != "movie-feed/1":
        errors.append({"code": "FEED_SCHEMA_MISMATCH", "actual": feed.get("schema_version")})
    if feed.get("source_id") != source_id:
        errors.append({"code": "FEED_SOURCE_MISMATCH", "actual": feed.get("source_id")})
    if len(items) != expected_count:
        errors.append({"code": "FEED_COUNT_MISMATCH", "expected": expected_count, "actual": len(items)})

    ranks = [item.get("rank") for item in items]
    if ranks != list(range(1, len(items) + 1)):
        errors.append({"code": "RANK_SEQUENCE_INVALID", "examples": ranks[:20]})

    unique_fields = {
        "movie_id": [str(item.get("movie_id") or "") for item in items],
        "detail_url": [str(item.get("detail_url") or "") for item in items],
        "source_item_key": [str(item.get("source_item_key") or "") for item in items],
    }
    duplicate_counts: dict[str, int] = {}
    for field, values in unique_fields.items():
        nonempty = [value for value in values if value]
        duplicates = len(nonempty) - len(set(nonempty))
        duplicate_counts[field] = duplicates
        if len(nonempty) != len(items):
            errors.append({"code": f"{field.upper()}_MISSING", "count": len(items) - len(nonempty)})
        if duplicates:
            errors.append({"code": f"{field.upper()}_DUPLICATE", "count": duplicates})

    missing_titles: list[dict[str, Any]] = []
    anomalous_titles: list[dict[str, Any]] = []
    missing_covers: list[dict[str, Any]] = []
    invalid_cover_urls: list[dict[str, Any]] = []
    zero_resources: list[dict[str, Any]] = []
    zero_valid_resources: list[dict[str, Any]] = []
    zero_app_resources: list[dict[str, Any]] = []
    invalid_resources: list[dict[str, Any]] = []
    duplicate_item_resources: list[dict[str, Any]] = []
    unsupported_resource_count = 0
    resource_type_counts: Counter[str] = Counter()
    provider_counts: Counter[str] = Counter()
    global_resource_owners: dict[str, set[str]] = defaultdict(set)
    total_resources = 0
    valid_resource_count = 0
    app_resource_count = 0

    for index, item in enumerate(items):
        key = str(item.get("source_item_key") or item.get("detail_url") or index)
        title = str(item.get("title") or "").strip()
        if not title:
            missing_titles.append({"index": index, "key": key})
        elif _text_has_anomaly(title):
            anomalous_titles.append({"index": index, "key": key, "title": title})

        cover = str(item.get("cover_source_url") or "").strip()
        if not cover:
            missing_covers.append({"index": index, "key": key, "title": title})
        elif not _valid_http_url(cover):
            invalid_cover_urls.append({"index": index, "key": key, "url": cover})

        resources = [resource for resource in item.get("resources") or [] if isinstance(resource, dict)]
        total_resources += len(resources)
        if not resources:
            zero_resources.append({"index": index, "key": key, "title": title})
            continue
        seen_item_resources: set[str] = set()
        valid = 0
        supported = 0
        for resource_index, resource in enumerate(resources):
            resource_type = str(resource.get("resource_type") or "").strip().lower()
            provider = str(resource.get("provider") or "").strip().lower()
            url = str(resource.get("url") or resource.get("resource_url") or "").strip()
            resource_type_counts[resource_type or "missing"] += 1
            provider_counts[provider or "missing"] += 1
            identity = _resource_identity(resource)
            if identity:
                if identity in seen_item_resources:
                    duplicate_item_resources.append(
                        {"index": index, "resource_index": resource_index, "key": key, "identity": identity}
                    )
                seen_item_resources.add(identity)
                global_resource_owners[identity].add(key)

            reason = None
            if resource_type not in _KNOWN_RESOURCE_TYPES:
                reason = "unknown_resource_type"
            elif resource_type == "magnet":
                try:
                    _normalized, info_hash = normalize_magnet_uri(url)
                    stored_hash = str(resource.get("info_hash") or "").strip().lower()
                    if stored_hash and stored_hash != info_hash:
                        reason = "info_hash_mismatch"
                except ResourceIndexError:
                    reason = "invalid_magnet"
            elif resource_type == "download":
                if not _valid_download_url(url):
                    reason = "invalid_download_url"
            elif not _valid_http_url(url):
                reason = "invalid_http_url"

            if reason:
                invalid_resources.append(
                    {
                        "index": index,
                        "resource_index": resource_index,
                        "key": key,
                        "resource_type": resource_type,
                        "reason": reason,
                    }
                )
            else:
                valid += 1
                valid_resource_count += 1
            if resource_type in _APP_RESOURCE_TYPES and reason is None:
                supported += 1
                app_resource_count += 1
            elif resource_type not in _APP_RESOURCE_TYPES:
                unsupported_resource_count += 1
        if valid == 0:
            zero_valid_resources.append({"index": index, "key": key, "title": title})
        if supported == 0:
            zero_app_resources.append({"index": index, "key": key, "title": title})

    if zero_app_resources:
        app_gap = {
            "code": "APP_RESOURCE_EMPTY",
            "count": len(zero_app_resources),
            "examples": zero_app_resources[:10],
        }
        if require_app_resources:
            errors.append(app_gap)
        else:
            warnings.append(app_gap)

    cross_item_duplicates = [
        {"identity": identity, "owner_count": len(owners), "owners": sorted(owners)[:10]}
        for identity, owners in global_resource_owners.items()
        if len(owners) > 1
    ]
    if cross_item_duplicates:
        duplicate_report = {
            "code": "CROSS_ITEM_RESOURCE_DUPLICATES",
            "count": len(cross_item_duplicates),
            "examples": cross_item_duplicates[:10],
        }
        if require_app_resources:
            errors.append(duplicate_report)
        else:
            warnings.append(duplicate_report)

    for code, values in (
        ("TITLE_MISSING", missing_titles),
        ("TITLE_ANOMALY", anomalous_titles),
        ("COVER_MISSING", missing_covers),
        ("COVER_URL_INVALID", invalid_cover_urls),
        ("RESOURCE_EMPTY", zero_resources),
        ("VALID_RESOURCE_EMPTY", zero_valid_resources),
        ("RESOURCE_INVALID", invalid_resources),
        ("RESOURCE_DUPLICATE_WITHIN_ITEM", duplicate_item_resources),
    ):
        if values:
            errors.append({"code": code, "count": len(values), "examples": values[:10]})

    repo = SqliteResourceRepository(database)
    try:
        integrity = str(repo.conn.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_key_rows = repo.conn.execute("PRAGMA foreign_key_check").fetchall()
        job = repo.conn.execute(
            """
            SELECT job_id, status, target_count, snapshot_http_requests,
                   detail_http_requests, completed_at, error_summary_json
            FROM latest_crawl_jobs
            WHERE source_id = ? AND target_count = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (source_id, discovery_target_count),
        ).fetchone()
        state_counts: dict[str, int] = {}
        if job is not None:
            state_counts = {
                str(row["status"]): int(row["count"])
                for row in repo.conn.execute(
                    "SELECT status, COUNT(*) AS count FROM latest_crawl_items WHERE job_id = ? GROUP BY status",
                    (job["job_id"],),
                ).fetchall()
            }
        database_item_count = int(
            repo.conn.execute(
                "SELECT COUNT(*) FROM movie_items WHERE source_id = ?",
                (source_id,),
            ).fetchone()[0]
        )
    finally:
        repo.close()

    if integrity != "ok":
        errors.append({"code": "SQLITE_INTEGRITY_FAILED", "result": integrity})
    if foreign_key_rows:
        errors.append({"code": "SQLITE_FOREIGN_KEY_FAILED", "count": len(foreign_key_rows)})
    if job is None:
        errors.append({"code": "CRAWL_JOB_MISSING"})
        job_payload: dict[str, Any] | None = None
    else:
        job_payload = dict(job)
        try:
            job_payload["error_summary"] = json.loads(str(job_payload.pop("error_summary_json") or "{}"))
        except json.JSONDecodeError:
            job_payload["error_summary"] = {"invalid_json": True}
        if job_payload["status"] != "success":
            errors.append({"code": "CRAWL_JOB_NOT_SUCCESS", "status": job_payload["status"]})
        if discovery_target_count == expected_count:
            expected_states = {"success": expected_count}
            if state_counts != expected_states:
                errors.append(
                    {"code": "CRAWL_ITEM_STATES_INVALID", "expected": expected_states, "actual": state_counts}
                )
        else:
            success_count = int(state_counts.get("success", 0))
            failed_count = int(state_counts.get("failed", 0))
            pending_count = int(state_counts.get("pending", 0))
            running_count = int(state_counts.get("running", 0))
            if (
                success_count < expected_count
                or success_count + failed_count != discovery_target_count
                or pending_count != 0
                or running_count != 0
            ):
                errors.append(
                    {
                        "code": "DISCOVERY_ITEM_STATES_INVALID",
                        "expected": {
                            "terminal_count": discovery_target_count,
                            "minimum_success": expected_count,
                            "pending": 0,
                            "running": 0,
                        },
                        "actual": state_counts,
                    }
                )
    if database_item_count < expected_count:
        errors.append(
            {"code": "DATABASE_ITEM_COUNT_LOW", "expected_at_least": expected_count, "actual": database_item_count}
        )

    summary = {
        "expected_count": expected_count,
        "discovery_target_count": discovery_target_count,
        "feed_item_count": len(items),
        "database_item_count": database_item_count,
        "title_missing_count": len(missing_titles),
        "title_anomaly_count": len(anomalous_titles),
        "cover_missing_count": len(missing_covers),
        "cover_url_invalid_count": len(invalid_cover_urls),
        "zero_resource_count": len(zero_resources),
        "zero_valid_resource_count": len(zero_valid_resources),
        "zero_app_resource_count": len(zero_app_resources),
        "resource_count": total_resources,
        "valid_resource_count": valid_resource_count,
        "app_resource_count": app_resource_count,
        "unsupported_resource_count": unsupported_resource_count,
        "invalid_resource_count": len(invalid_resources),
        "duplicate_resource_within_item_count": len(duplicate_item_resources),
        "cross_item_duplicate_resource_count": len(cross_item_duplicates),
        "resource_type_counts": dict(sorted(resource_type_counts.items())),
        "provider_counts": dict(sorted(provider_counts.items())),
        "unique_field_duplicate_counts": duplicate_counts,
    }
    report = {
        "schema_version": "media-source-reliability/1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "pass" if not errors else "fail",
        "source_id": source_id,
        "require_app_resources": require_app_resources,
        "database_path": str(database),
        "feed_path": str(feed_file),
        "job": job_payload,
        "crawl_item_state_counts": state_counts,
        "sqlite_integrity": integrity,
        "sqlite_foreign_key_error_count": len(foreign_key_rows),
        "summary": summary,
        "error_count": len(errors),
        "errors": errors,
        "warning_count": len(warnings),
        "warnings": warnings,
    }
    if output_path is not None:
        _atomic_write_json(Path(output_path), report)
    return report
