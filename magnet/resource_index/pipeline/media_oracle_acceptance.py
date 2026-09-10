"""Fail-closed acceptance checks for an Oracle media shadow candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.pipeline.media_daily import MediaDailyConfig


def _fail(message: str, **context: Any) -> None:
    raise ResourceIndexError(CONFIG_ERROR, message, context)


def _load_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("failed to read Oracle media acceptance JSON", path=str(source), error=type(exc).__name__)
    if not isinstance(value, dict):
        _fail("Oracle media acceptance JSON must be an object", path=str(source))
    return value


def _read_bytes(path: str | Path) -> bytes:
    source = Path(path)
    try:
        return source.read_bytes()
    except OSError as exc:
        _fail("failed to read Oracle media acceptance control file", path=str(source), error=type(exc).__name__)


def _pointer(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("public media pointer is invalid JSON", label=label, error=type(exc).__name__)
    if not isinstance(value, dict):
        _fail("public media pointer must be an object", label=label)
    revision = value.get("pointer_revision")
    release_id = value.get("release_id")
    if type(revision) is not int or revision < 1 or not isinstance(release_id, str) or not release_id:
        _fail("public media pointer has invalid control fields", label=label)
    return value


def _crawl_by_source(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    crawl = ((status.get("stages") or {}).get("crawl") or [])
    if not isinstance(crawl, list):
        _fail("candidate crawl stage is invalid")
    output: dict[str, dict[str, Any]] = {}
    for item in crawl:
        if not isinstance(item, dict):
            _fail("candidate crawl entry is invalid")
        source_id = str(item.get("source_id") or "")
        if not source_id or source_id in output:
            _fail("candidate crawl source ids are missing or duplicated", source_id=source_id)
        output[source_id] = item
    return output


def verify_oracle_media_candidate(
    *,
    status: dict[str, Any],
    config: MediaDailyConfig,
    r2_before: bytes,
    r2_after: bytes,
    aliyun_before: bytes,
    aliyun_after: bytes,
    require_all_group_members_fresh: bool = True,
) -> dict[str, Any]:
    if status.get("status") != "success":
        _fail("Oracle media candidate did not finish successfully", status=status.get("status"))
    if status.get("mode") != "candidate":
        _fail("Oracle media acceptance requires candidate mode", mode=status.get("mode"))
    if status.get("publish_candidate") is not True or status.get("candidate_verified") is not True:
        _fail("Oracle media candidate was not fully verified")
    if status.get("published") is True or "publish" in (status.get("stages") or {}):
        _fail("Oracle media candidate unexpectedly entered a publication stage")
    if status.get("publish_withheld") is True:
        _fail("Oracle media candidate reports publication withholding", reason=status.get("publish_withheld_reason"))

    if r2_before != r2_after:
        _fail("R2 current pointer changed during Oracle shadow validation")
    if aliyun_before != aliyun_after:
        _fail("Aliyun current pointer changed during Oracle shadow validation")
    if r2_before != aliyun_before:
        _fail("R2 and Aliyun current pointers were already divergent before Oracle shadow validation")
    public_pointer = _pointer(r2_before, label="public-before")
    previous_revision = status.get("previous_revision")
    candidate_revision = status.get("candidate_revision")
    if previous_revision != public_pointer["pointer_revision"]:
        _fail(
            "candidate previous revision does not match the frozen public pointer",
            expected=public_pointer["pointer_revision"],
            actual=previous_revision,
        )
    if candidate_revision != public_pointer["pointer_revision"] + 1:
        _fail(
            "candidate revision is not exactly one revision after public",
            public_revision=public_pointer["pointer_revision"],
            candidate_revision=candidate_revision,
        )

    required_degraded = status.get("required_degraded_sources")
    failed_groups = status.get("failed_freshness_groups")
    if required_degraded != []:
        _fail("Oracle candidate has degraded required sources", sources=required_degraded)
    if failed_groups != []:
        _fail("Oracle candidate has failed freshness groups", groups=failed_groups)

    crawl = _crawl_by_source(status)
    configured_ids = [source.source_id for source in config.sources]
    if set(crawl) != set(configured_ids):
        _fail(
            "Oracle candidate crawl set does not match configured sources",
            expected=sorted(configured_ids),
            actual=sorted(crawl),
        )
    for source in config.sources:
        if not source.freshness_required:
            continue
        item = crawl[source.source_id]
        if item.get("freshness_magnet_status") != "pass" or int(item.get("magnet_item_count") or 0) <= 0:
            _fail("required freshness source has no current magnet evidence", source_id=source.source_id)

    group_health = status.get("freshness_groups")
    if not isinstance(group_health, dict):
        _fail("Oracle candidate freshness group report is missing")
    for group in config.freshness_groups:
        report = group_health.get(group.group_id)
        if not isinstance(report, dict) or report.get("status") != "pass":
            _fail("Oracle candidate freshness group did not pass", group=group.group_id)
        fresh_count = int(report.get("fresh_count") or 0)
        member_count = int(report.get("member_count") or 0)
        if fresh_count < group.min_fresh:
            _fail("Oracle candidate freshness group is below quorum", group=group.group_id)
        if require_all_group_members_fresh and fresh_count != member_count:
            _fail(
                "Oracle migration acceptance requires all freshness group members fresh",
                group=group.group_id,
                fresh_count=fresh_count,
                member_count=member_count,
            )
        no_magnet = report.get("no_magnet_sources")
        if no_magnet not in (None, []):
            _fail("freshness group has source without current magnet evidence", group=group.group_id, sources=no_magnet)

    movie_count = int(status.get("movie_count") or 0)
    series_count = int(status.get("series_count") or 0)
    resource_count = int(status.get("resource_count") or 0)
    if movie_count < config.min_movies or series_count < config.min_series:
        _fail(
            "Oracle candidate content counts are below production floor",
            movie_count=movie_count,
            min_movies=config.min_movies,
            series_count=series_count,
            min_series=config.min_series,
        )
    if resource_count <= 0:
        _fail("Oracle candidate contains no resources")

    stages = status.get("stages") or {}
    aggregate = stages.get("aggregate")
    quality = aggregate.get("quality") if isinstance(aggregate, dict) else None
    if not isinstance(quality, dict) or quality.get("status") != "pass":
        _fail("Oracle candidate aggregate quality gate did not pass")
    for field in (
        "bad_label_count",
        "accepted_cross_season_count",
        "weak_episode_title_count",
        "empty_resource_item_count",
    ):
        if int(quality.get(field) or 0) != 0:
            _fail("Oracle candidate accepted invalid aggregate output", field=field, value=quality.get(field))

    magnet_only = stages.get("magnet_only")
    if not isinstance(magnet_only, dict) or magnet_only.get("status") != "pass":
        _fail("Oracle candidate magnet-only stage did not pass")
    if int(magnet_only.get("total_magnet_resource_count") or 0) != resource_count:
        _fail(
            "Oracle candidate resource count does not match magnet-only output",
            resource_count=resource_count,
            magnet_count=magnet_only.get("total_magnet_resource_count"),
        )
    if int(magnet_only.get("total_item_count") or 0) != movie_count + series_count:
        _fail("Oracle candidate item count does not match magnet-only output")

    covers = stages.get("covers")
    if not isinstance(covers, dict):
        _fail("Oracle candidate cover stage is missing")
    for kind in ("movie", "series"):
        report = covers.get(kind)
        audit = report.get("audit") if isinstance(report, dict) else None
        if not isinstance(audit, dict) or audit.get("status") != "pass":
            _fail("Oracle candidate cover audit did not pass", content_kind=kind)

    pointer_sha = hashlib.sha256(r2_before).hexdigest()
    return {
        "schema_version": "media-oracle-acceptance/1",
        "status": "pass",
        "run_id": status.get("run_id"),
        "public_revision": public_pointer["pointer_revision"],
        "candidate_revision": candidate_revision,
        "candidate_release_id": status.get("release_id"),
        "movie_count": movie_count,
        "series_count": series_count,
        "resource_count": resource_count,
        "public_pointer_sha256": pointer_sha,
        "public_pointer_unchanged": True,
        "required_sources_fresh": True,
        "freshness_groups_all_fresh": require_all_group_members_fresh,
        "aggregate_quality": True,
        "magnet_only": True,
        "cover_audits": True,
    }
