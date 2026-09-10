from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.pipeline.media_compute_handoff import extract_compute_handoff
from magnet.resource_index.pipeline.media_daily import (
    MediaDailyConfig,
    _pointer_semantics,
    _reconcile_online_controls,
    _verify_public_control,
)
from magnet.resource_index.publish.filesystem import FilesystemPublisherBackend
from magnet.resource_index.publish.orchestrator import MediaPublishConfig, publish_media_release
from magnet.resource_index.publish.worker_bridge import WorkerR2PublisherBackend
from magnet.resource_index.release.builder import MediaReleaseConfig, build_media_release


def _fail(message: str, **context: Any) -> None:
    raise ResourceIndexError(CONFIG_ERROR, message, context)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_handoff_time(status: dict[str, Any], config: MediaDailyConfig) -> None:
    raw_finished_at = status.get("finished_at")
    if not isinstance(raw_finished_at, str) or not raw_finished_at.strip():
        _fail("compute handoff finished_at is required")
    normalized = raw_finished_at.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        finished_at = datetime.fromisoformat(normalized)
    except ValueError:
        _fail("compute handoff finished_at is invalid", finished_at=raw_finished_at)
    if finished_at.tzinfo is None or finished_at.utcoffset() is None:
        _fail("compute handoff finished_at must be timezone-aware", finished_at=raw_finished_at)
    finished_at = finished_at.astimezone(timezone.utc)
    now = _utc_now()
    if finished_at > now + timedelta(minutes=15):
        _fail("compute handoff finished_at is too far in the future", finished_at=raw_finished_at)
    if now - finished_at > timedelta(hours=config.compute_handoff_max_age_hours):
        _fail(
            "compute handoff is older than maximum age",
            finished_at=raw_finished_at,
            max_age_hours=config.compute_handoff_max_age_hours,
        )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("media compute finalizer JSON is invalid", path=str(path), error=type(exc).__name__)
    if not isinstance(value, dict):
        _fail("media compute finalizer JSON must be an object", path=str(path))
    return value


def _validate_compute_status(status: dict[str, Any], config: MediaDailyConfig) -> None:
    if status.get("status") != "success" or status.get("mode") != "compute":
        _fail("compute handoff status is not a successful compute run")
    if status.get("compute_candidate") is not True or status.get("compute_verified") is not True:
        _fail("compute handoff was not verified")
    if status.get("published") is True:
        _fail("compute handoff unexpectedly reports publication")
    if status.get("required_degraded_sources") not in (None, []):
        _fail("compute handoff has degraded required sources", sources=status.get("required_degraded_sources"))
    if status.get("failed_freshness_groups") not in (None, []):
        _fail("compute handoff has failed freshness groups", groups=status.get("failed_freshness_groups"))
    stages = status.get("stages") or {}
    aggregate = stages.get("aggregate") or {}
    quality = aggregate.get("quality") or {}
    if quality.get("status") != "pass":
        _fail("compute handoff aggregate quality did not pass")
    for field in ("bad_label_count", "accepted_cross_season_count", "weak_episode_title_count", "empty_resource_item_count"):
        if int(quality.get(field) or 0) != 0:
            _fail("compute handoff aggregate quality contains accepted errors", field=field, value=quality.get(field))
    magnet_only = stages.get("magnet_only") or {}
    if magnet_only.get("status") != "pass":
        _fail("compute handoff magnet-only gate did not pass")
    movie_count = int(status.get("movie_count") or 0)
    series_count = int(status.get("series_count") or 0)
    resource_count = int(status.get("resource_count") or 0)
    if movie_count < config.min_movies or series_count < config.min_series or resource_count <= 0:
        _fail("compute handoff counts are below publication floor", movie_count=movie_count, series_count=series_count, resource_count=resource_count)
    if int(magnet_only.get("total_magnet_resource_count") or 0) != resource_count:
        _fail("compute handoff resource count does not match magnet-only output")
    covers = stages.get("covers") or {}
    for kind in ("movie", "series"):
        report = covers.get(kind) or {}
        if (report.get("audit") or {}).get("status") != "pass":
            _fail("compute handoff cover audit did not pass", content_kind=kind)
    groups = status.get("freshness_groups") or {}
    for group in config.freshness_groups:
        report = groups.get(group.group_id) or {}
        if report.get("status") != "pass" or int(report.get("fresh_count") or 0) < group.min_fresh:
            _fail("compute handoff freshness group is below quorum", group=group.group_id)


def finalize_compute_handoff(
    config: MediaDailyConfig,
    *,
    package_path: str | Path,
    publish: bool = False,
    force_publish: bool = False,
) -> dict[str, Any]:
    if config.aliyun_ssh_target:
        _fail("Aliyun compute finalizer must use the local filesystem mirror backend")
    root = config.state_root.resolve()
    finalizer_root = root / "finalizer"
    run_token = uuid.uuid4().hex[:12]
    run_dir = finalizer_root / "runs" / run_token
    input_dir = run_dir / "input"
    run_dir.mkdir(parents=True, exist_ok=False)
    extracted = extract_compute_handoff(package_path, input_dir)
    manifest = extracted["manifest"]
    status = _load_json(input_dir / "status.json")
    if status.get("run_id") != manifest.get("run_id"):
        _fail("compute handoff run id mismatch")
    _validate_handoff_time(status, config)
    state_dir = root / "status"
    state_path = state_dir / "compute-finalizer-state.json"
    prior_state = _load_json(state_path) if state_path.is_file() else {}
    if prior_state.get("compute_run_id") == status.get("run_id"):
        return {
            "schema_version": "media-compute-finalize/1",
            "status": "success",
            "mode": "publish" if publish else "candidate",
            "compute_run_id": status.get("run_id"),
            "no_change": True,
            "already_finalized": True,
            "current_revision": prior_state.get("current_revision"),
            "release_id": prior_state.get("release_id"),
            "published": False,
        }
    for key in ("previous_revision", "content_sha256", "movie_count", "series_count", "resource_count"):
        if status.get(key) != manifest.get(key):
            _fail("compute handoff manifest/status mismatch", field=key)
    _validate_compute_status(status, config)
    if not config.public_key_path.is_file() or not config.private_key_path.is_file():
        _fail("production media signing material is missing on finalizer")
    if config.previous_public_key_path is not None and not config.previous_public_key_path.is_file():
        _fail("trusted previous media public key is missing on finalizer")

    previous_current, previous_manifest_path, previous_current_path, control_stage = _reconcile_online_controls(
        config,
        run_dir / "control",
        publish=publish,
    )
    previous_revision = int(previous_current.get("pointer_revision") or 0)
    if int(status.get("previous_revision") or 0) != previous_revision:
        _fail("compute handoff is stale relative to current production", handoff_revision=status.get("previous_revision"), production_revision=previous_revision)
    if (
        publish
        and prior_state.get("content_sha256") == status.get("content_sha256")
        and prior_state.get("current_revision") == previous_revision
        and prior_state.get("release_id") == previous_current.get("release_id")
    ):
        state_dir.mkdir(parents=True, exist_ok=True)
        temporary = state_dir / f".{state_path.name}.{uuid.uuid4().hex}.tmp"
        temporary.write_text(
            json.dumps(
                {
                    **prior_state,
                    "compute_run_id": status.get("run_id"),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.replace(temporary, state_path)
        return {
            "schema_version": "media-compute-finalize/1",
            "status": "success",
            "mode": "publish",
            "compute_run_id": status.get("run_id"),
            "no_change": True,
            "content_unchanged": True,
            "current_revision": previous_revision,
            "release_id": previous_current.get("release_id"),
            "published": False,
        }

    release_result = build_media_release(
        MediaReleaseConfig(
            movie_feed_path=input_dir / "feeds" / "movies-final.json",
            series_feed_path=input_dir / "feeds" / "series-final.json",
            movie_cover_bundle=input_dir / "bundles" / "movie",
            series_cover_bundle=input_dir / "bundles" / "series",
            output_dir=run_dir / "release-candidate",
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
    current_path = Path(release_result.current_path)
    candidate_current = _load_json(current_path)
    result: dict[str, Any] = {
        "schema_version": "media-compute-finalize/1",
        "status": "success",
        "mode": "publish" if publish else "candidate",
        "compute_run_id": status.get("run_id"),
        "control_recovery": control_stage,
        "previous_revision": previous_revision,
        "candidate_revision": previous_revision + 1,
        "release_id": release_result.release_id,
        "movie_count": status.get("movie_count"),
        "series_count": status.get("series_count"),
        "resource_count": status.get("resource_count"),
        "release": release_result.__dict__,
        "published": False,
    }
    if not force_publish and _pointer_semantics(candidate_current) == _pointer_semantics(previous_current):
        result.update({"no_change": True, "candidate_revision": previous_revision, "release_id": previous_current.get("release_id")})
        return result
    if not publish:
        result["candidate_verified"] = True
        return result

    token = os.environ.get(config.worker_token_env, "")
    if len(token) < 32 or not config.worker_url.startswith("https://"):
        _fail("production Worker credentials are missing on finalizer")
    release_dir = Path(release_result.release_dir)
    publish_config = MediaPublishConfig(
        release_dir=release_dir,
        current_path=current_path,
        public_key_path=config.public_key_path,
        receipt_dir=root / "receipts",
        max_workers=config.max_workers,
        deep_verify=False,
        upload_pointer_candidate=False,
    )
    aliyun_backend = FilesystemPublisherBackend(config.public_root)
    r2_backend = WorkerR2PublisherBackend(
        worker_url=config.worker_url,
        upload_token=token,
        prefix="",
        allow_production_root=True,
        allow_current_promotion=True,
        max_attempts=4,
    )
    aliyun_publish = publish_media_release(aliyun_backend, publish_config)
    r2_publish = publish_media_release(r2_backend, publish_config)
    expected_sha = hashlib.sha256(previous_current_path.read_bytes()).hexdigest()
    live_local = config.public_root / "v1" / "current.json"
    if not live_local.is_file() or hashlib.sha256(live_local.read_bytes()).hexdigest() != expected_sha:
        _fail("Aliyun local current changed before finalizer promotion")
    r2_backend.promote_current(current_path)
    try:
        aliyun_backend.promote_current(current_path)
    except BaseException as promotion_error:
        try:
            _reconcile_online_controls(config, run_dir / "post-promotion-recovery", publish=True)
        except BaseException as recovery_error:
            raise promotion_error from recovery_error
    verification = [
        _verify_public_control(config.r2_public_base, current_path),
        _verify_public_control(config.aliyun_public_base, current_path),
    ]
    result.update(
        {
            "published": True,
            "current_revision": previous_revision + 1,
            "publish": {"aliyun": aliyun_publish.__dict__, "r2": r2_publish.__dict__},
            "verification": verification,
            "pointer_sha256": hashlib.sha256(current_path.read_bytes()).hexdigest(),
        }
    )
    state_dir.mkdir(parents=True, exist_ok=True)
    temporary = state_dir / f".{state_path.name}.{uuid.uuid4().hex}.tmp"
    temporary.write_text(json.dumps({"schema_version": "media-compute-finalizer-state/1", "compute_run_id": status.get("run_id"), "content_sha256": status.get("content_sha256"), "current_revision": previous_revision + 1, "release_id": release_result.release_id}, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, state_path)
    return result
