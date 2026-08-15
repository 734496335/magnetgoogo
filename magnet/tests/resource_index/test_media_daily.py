from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline import media_daily
from magnet.resource_index.pipeline.media_daily import (
    DailySourceConfig,
    MediaDailyConfig,
    _archive_unpromoted_pointer_candidates,
    _rating_next_offset,
    _run_lock,
    load_media_daily_config,
    run_media_daily,
)
from magnet.resource_index.pipeline.media_offline_bundle import MediaAppBundleResult


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _media_feed(kind: str) -> dict:
    movie_id = f"{kind}:1"
    info_hash = ("a" if kind == "movie" else "b") * 40
    return {
        "schema_version": "media-feed/1",
        "content_kind_filter": kind,
        "generated_at": "2026-07-30T00:00:00Z",
        "items": [
            {
                "rank": 1,
                "movie_id": movie_id,
                "title": f"{kind}-title",
                "content_kind": kind,
                "resources": [
                    {
                        "resource_type": "magnet",
                        "provider": "magnet",
                        "url": f"magnet:?xt=urn:btih:{info_hash}",
                        "info_hash": info_hash,
                    },
                    {
                        "resource_type": "cloud",
                        "provider": "quark",
                        "url": "https://pan.quark.cn/s/example",
                    },
                ],
            }
        ],
        "summary": {"record_count": 1, "resource_count": 1},
        "quality": {"required_fields": ["title", "cover", "resources"], "rating_required": False},
    }


def _install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        media_daily,
        "run_safe_movie_source",
        lambda **kwargs: SimpleNamespace(
            source_id=kwargs["source_id"],
            status="ran",
            db_path=f"/{kwargs['source_id']}.db",
        ),
    )

    def fake_export(**kwargs):
        _write(Path(kwargs["output_path"]), {"schema_version": "movie-feed/1", "items": []})
        return {"items": []}

    monkeypatch.setattr(media_daily, "export_source_library_feed", fake_export)
    monkeypatch.setattr(
        media_daily,
        "safe_movie_source_status",
        lambda **kwargs: {
            "job": {"db_path": f"/{kwargs['source_id']}.db", "status": "success", "covered_count": kwargs["target_count"]},
            "source": {"last_completed_at": media_daily._iso()},
        },
    )

    def fake_aggregate(_feeds, **kwargs):
        movie = _media_feed("movie")
        series = _media_feed("series")
        _write(Path(kwargs["output_path"]), {"schema_version": "media-feed/1", "items": movie["items"] + series["items"]})
        _write(Path(kwargs["movie_output_path"]), movie)
        _write(Path(kwargs["series_output_path"]), series)
        _write(Path(kwargs["quarantine_output_path"]), {"items": []})
        _write(Path(kwargs["quality_output_path"]), {"status": "pass"})
        return {"summary": {"record_count": 2, "resource_count": 2}}

    monkeypatch.setattr(media_daily, "aggregate_media_feeds", fake_aggregate)
    monkeypatch.setattr(media_daily, "RatingResolver", lambda **_kwargs: object())
    monkeypatch.setattr(media_daily, "enrich_feed_file", lambda *_args, **_kwargs: {"changed_items": 0, "errors": 0})

    def fake_bundle(*, feed_path, output_dir, content_kind, **_kwargs):
        source = json.loads(Path(feed_path).read_text(encoding="utf-8"))
        app = {
            "schema_version": "media-app-feed/1",
            "content_kind": content_kind,
            "items": source["items"],
            "summary": {"record_count": len(source["items"]), "resource_count": 1},
        }
        root = Path(output_dir)
        _write(root / "feed.json", app)
        _write(root / "cover_failures.json", {"failed_count": 0, "items": []})
        return MediaAppBundleResult(
            content_kind=content_kind,
            item_count=1,
            cover_count=1,
            resource_count=1,
            downloaded=0,
            reused=1,
            failed=0,
            http_requests=0,
            feed_path=str(root / "feed.json"),
            cover_dir=str(root / "covers"),
            manifest_path=str(root / "cover_manifest.json"),
        )

    monkeypatch.setattr(media_daily, "build_media_app_bundle", fake_bundle)
    monkeypatch.setattr(media_daily, "audit_media_app_bundle", lambda **_kwargs: {"status": "pass"})
    monkeypatch.setattr(media_daily, "verify_document", lambda *_args, **_kwargs: None)
    previous = Path("previous-manifest.json")
    def fake_online_control(_base, run_dir):
        current = run_dir / "previous-current.json"
        manifest = run_dir / previous
        _write(
            current,
            {
                "pointer_revision": 6,
                "release_id": "20260729T000000Z-b07630f3",
                "manifest_path": "/v1/releases/previous/manifest.json",
                "manifest_sha256": "d" * 64,
            },
        )
        _write(manifest, {"release_id": "20260729T000000Z-b07630f3"})
        return (
            {
                "pointer_revision": 6,
                "release_id": "20260729T000000Z-b07630f3",
                "manifest_path": "/v1/releases/previous/manifest.json",
                "manifest_sha256": "d" * 64,
            },
            manifest,
        )

    monkeypatch.setattr(media_daily, "_online_control", fake_online_control)
    monkeypatch.setattr(
        media_daily,
        "_verify_public_control",
        lambda base, _path: {
            "base": base,
            "pointer_revision": 6,
            "release_id": "20260729T000000Z-b07630f3",
        },
    )

    def fake_release(config):
        release_dir = Path(config.output_dir) / "staging" / "releases" / "candidate-release"
        current_path = Path(config.output_dir) / "staging" / "pointers" / "candidate.json"
        _write(release_dir / "v1" / "releases" / "candidate-release" / "manifest.json", {"release_id": "candidate-release"})
        _write(
            current_path,
            {
                "pointer_revision": config.pointer_revision,
                "release_id": "candidate-release",
                "manifest_path": "/v1/releases/candidate-release/manifest.json",
                "manifest_sha256": "c" * 64,
            },
        )
        return SimpleNamespace(
            release_id="candidate-release",
            release_dir=str(release_dir),
            current_path=str(current_path),
            manifest_path=str(release_dir / "v1" / "releases" / "candidate-release" / "manifest.json"),
            manifest_sha256="c" * 64,
            object_count=1,
            reused=False,
            release_reused=False,
            pointer_reused=False,
            counts={"movie": 1, "series": 1, "resources": 2},
        )

    monkeypatch.setattr(media_daily, "build_media_release", fake_release)


def _control(revision: int, release_id: str) -> dict:
    return {
        "pointer_revision": revision,
        "release_id": release_id,
        "manifest_path": f"/v1/releases/{release_id}/manifest.json",
        "manifest_sha256": "d" * 64,
    }


def _config(tmp_path: Path) -> MediaDailyConfig:
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    private_key.write_text("candidate-private", encoding="utf-8")
    public_key.write_text("candidate-public", encoding="utf-8")
    return MediaDailyConfig(
        state_root=tmp_path / "state",
        public_root=tmp_path / "public",
        private_key_path=private_key,
        public_key_path=public_key,
        worker_url="https://worker.example",
        worker_token_env="TOKEN",
        r2_public_base="https://media.example",
        aliyun_public_base="https://cn.example/media",
        min_app_version="0.2.3",
        sources=(DailySourceConfig("sixv", 10),),
        disk_max_used_percent=99.9,
        disk_min_free_bytes=1,
    )


def test_rating_next_offset_preserves_zero_wraparound() -> None:
    assert _rating_next_offset({"next_offset": 0}, 42) == 0
    assert _rating_next_offset({"next_offset": None}, 42) == 42
    assert _rating_next_offset({"next_offset": "0"}, 42) == 42


def test_media_daily_config_defaults_to_v023(tmp_path: Path) -> None:
    config_path = tmp_path / "media-daily.json"
    _write(
        config_path,
        {
            "state_root": str(tmp_path / "state"),
            "public_root": str(tmp_path / "public"),
            "private_key_path": str(tmp_path / "private.pem"),
            "public_key_path": str(tmp_path / "public.pem"),
            "sources": [{"source_id": "sixv", "count": 100}],
        },
    )
    loaded = load_media_daily_config(config_path)
    assert loaded.min_app_version == "0.2.3"
    assert loaded.source_fallback_retry_delay_seconds == 900
    assert loaded.sources[0].freshness_required is False


def test_media_daily_config_rejects_non_boolean_freshness_flag(tmp_path: Path) -> None:
    config_path = tmp_path / "media-daily.json"
    _write(
        config_path,
        {
            "state_root": str(tmp_path / "state"),
            "public_root": str(tmp_path / "public"),
            "private_key_path": str(tmp_path / "private.pem"),
            "public_key_path": str(tmp_path / "public.pem"),
            "sources": [{"source_id": "sixv", "count": 100, "freshness_required": "yes"}],
        },
    )
    with pytest.raises(ResourceIndexError, match="freshness flag"):
        load_media_daily_config(config_path)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("rating_lookup_limit_per_feed", 0),
        ("retention_runs", 0),
        ("retention_status_history", -1),
        ("retention_releases", "3"),
        ("disk_max_used_percent", 100),
        ("disk_min_free_bytes", -1),
        ("source_fallback_max_age_hours", 0),
        ("source_fallback_retry_delay_seconds", -1),
    ],
)
def test_media_daily_config_rejects_unsafe_maintenance_settings(
    tmp_path: Path,
    name: str,
    value: object,
) -> None:
    config_path = tmp_path / "media-daily.json"
    payload = {
        "state_root": str(tmp_path / "state"),
        "public_root": str(tmp_path / "public"),
        "private_key_path": str(tmp_path / "private.pem"),
        "public_key_path": str(tmp_path / "public.pem"),
        "sources": [{"source_id": "sixv", "count": 100}],
        name: value,
    }
    _write(config_path, payload)
    with pytest.raises(ResourceIndexError):
        load_media_daily_config(config_path)


def test_run_lock_does_not_remove_another_process_lock(tmp_path: Path) -> None:
    lock = tmp_path / "daily.lock"
    lock.write_text(f"pid={os.getpid()}\n", encoding="ascii")
    with pytest.raises(ResourceIndexError):
        with _run_lock(lock, started_at="2026-07-31T00:00:00Z"):
            pass
    assert lock.read_text(encoding="ascii") == f"pid={os.getpid()}\n"


def test_lock_conflict_does_not_overwrite_active_latest_status(tmp_path: Path) -> None:
    config = _config(tmp_path)
    latest = config.state_root / "status" / "latest.json"
    active = {"schema_version": "media-daily-status/1", "status": "running", "run_id": "active-run"}
    _write(latest, active)
    lock = config.state_root / "locks" / "media-daily.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"pid={os.getpid()}\n", encoding="ascii")

    with pytest.raises(ResourceIndexError, match="already active"):
        run_media_daily(config, publish=False)

    assert json.loads(latest.read_text(encoding="utf-8")) == active
    assert not list((config.state_root / "status").glob("20*.json"))


def test_daily_pipeline_short_circuits_when_content_hash_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    config = _config(tmp_path)

    first = run_media_daily(config, publish=False)
    assert first["publish_candidate"] is True
    assert first["candidate_verified"] is True
    assert first["stages"]["release"]["release_id"] == "candidate-release"
    assert first["stages"]["soak"]["consecutive_days"] == 1
    assert first["stages"]["soak"]["ready_for_promotion"] is False
    _write(
        config.state_root / "status" / "state.json",
        {
            "schema_version": "media-daily-state/1",
            "content_sha256": first["content_sha256"],
            "current_revision": 6,
            "release_id": "20260729T000000Z-b07630f3",
        },
    )

    second = run_media_daily(config, publish=True)
    assert second["status"] == "success"
    assert second["no_change"] is True
    assert second["published"] is False
    assert second["public_verified"] is True
    assert second["current_revision"] == 6
    assert second["resource_count"] == 2
    assert second["mode"] == "publish"
    assert json.loads(
        (config.state_root / "status" / "latest-publish.json").read_text(encoding="utf-8")
    )["run_id"] == second["run_id"]
    assert second["stages"]["magnet_only"]["movie"]["removed_non_magnet_resource_count"] == 1
    assert second["stages"]["magnet_only"]["series"]["removed_non_magnet_resource_count"] == 1


def test_public_control_recovery_repairs_aliyun_when_r2_is_one_revision_ahead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    promoted: list[dict] = []

    def online(base: str, run_dir: Path):
        document = _control(7, "20260730T000000Z-r2ahead0") if base == config.r2_public_base else _control(6, "20260729T000000Z-old00000")
        current = run_dir / "previous-current.json"
        manifest = run_dir / "previous-manifest.json"
        _write(current, document)
        _write(manifest, {"release_id": document["release_id"]})
        return document, manifest

    class LocalBackend:
        def __init__(self, *_args, **_kwargs):
            pass

        def promote_current(self, path):
            promoted.append(json.loads(Path(path).read_text(encoding="utf-8")))

    monkeypatch.setattr(media_daily, "_online_control", online)
    monkeypatch.setattr(media_daily, "verify_document", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(media_daily, "_verify_manifest_available", lambda *_args, **_kwargs: "d" * 64)
    monkeypatch.setattr(media_daily, "_verify_public_control", lambda base, _path: {"base": base, "pointer_revision": 7})
    monkeypatch.setattr(media_daily, "FilesystemPublisherBackend", LocalBackend)

    current, _manifest, _path, stage = media_daily._reconcile_online_controls(config, tmp_path / "run", publish=True)

    assert current["pointer_revision"] == 7
    assert promoted == [_control(7, "20260730T000000Z-r2ahead0")]
    assert stage["action"] == "repair_aliyun_from_r2_authority"
    assert stage["r2_revision_after"] == stage["aliyun_revision_after"] == 7


def test_public_control_recovery_repairs_r2_from_signed_legacy_aliyun_ahead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    promoted: list[dict] = []

    def online(base: str, run_dir: Path):
        document = _control(6, "20260729T000000Z-old00000") if base == config.r2_public_base else _control(7, "20260730T000000Z-aliyahead")
        current = run_dir / "previous-current.json"
        manifest = run_dir / "previous-manifest.json"
        _write(current, document)
        _write(manifest, {"release_id": document["release_id"]})
        return document, manifest

    class R2Backend:
        def __init__(self, *_args, **_kwargs):
            pass

        def promote_current(self, path):
            promoted.append(json.loads(Path(path).read_text(encoding="utf-8")))

    monkeypatch.setattr(media_daily, "_online_control", online)
    monkeypatch.setattr(media_daily, "verify_document", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(media_daily, "_verify_manifest_available", lambda *_args, **_kwargs: "d" * 64)
    monkeypatch.setattr(media_daily, "_verify_public_control", lambda base, _path: {"base": base, "pointer_revision": 7})
    monkeypatch.setattr(media_daily, "WorkerR2PublisherBackend", R2Backend)
    monkeypatch.setenv("TOKEN", "t" * 64)

    current, _manifest, _path, stage = media_daily._reconcile_online_controls(config, tmp_path / "run", publish=True)

    assert current["pointer_revision"] == 7
    assert promoted == [_control(7, "20260730T000000Z-aliyahead")]
    assert stage["action"] == "repair_r2_from_signed_aliyun_ahead"


def test_public_control_recovery_rejects_same_revision_rebind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    def online(base: str, run_dir: Path):
        release_id = "20260730T000000Z-releasea" if base == config.r2_public_base else "20260730T000000Z-releaseb"
        document = _control(7, release_id)
        current = run_dir / "previous-current.json"
        manifest = run_dir / "previous-manifest.json"
        _write(current, document)
        _write(manifest, {"release_id": release_id})
        return document, manifest

    monkeypatch.setattr(media_daily, "_online_control", online)
    monkeypatch.setattr(media_daily, "verify_document", lambda *_args, **_kwargs: None)

    with pytest.raises(ResourceIndexError, match="rebind the same revision"):
        media_daily._reconcile_online_controls(config, tmp_path / "run", publish=True)


def test_public_control_recovery_rejects_unsafe_revision_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    def online(base: str, run_dir: Path):
        document = _control(9, "20260731T000000Z-release9") if base == config.r2_public_base else _control(6, "20260729T000000Z-release6")
        current = run_dir / "previous-current.json"
        manifest = run_dir / "previous-manifest.json"
        _write(current, document)
        _write(manifest, {"release_id": document["release_id"]})
        return document, manifest

    monkeypatch.setattr(media_daily, "_online_control", online)
    monkeypatch.setattr(media_daily, "verify_document", lambda *_args, **_kwargs: None)

    with pytest.raises(ResourceIndexError, match="gap is unsafe"):
        media_daily._reconcile_online_controls(config, tmp_path / "run", publish=True)


def test_daily_pipeline_keeps_running_when_rating_provider_stage_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)

    def fail_ratings(*_args, **_kwargs):
        raise RuntimeError("all rating providers unavailable")

    monkeypatch.setattr(media_daily, "enrich_feed_file", fail_ratings)
    config = _config(tmp_path)

    result = run_media_daily(config, publish=False)
    assert result["status"] == "success"
    assert result["publish_candidate"] is True
    assert result["stages"]["rating"]["status"] == "warning"
    assert result["stages"]["rating"]["lookup"]["error"]["type"] == "RuntimeError"
    assert result["resource_count"] == 2


def test_candidate_and_audit_release_artifacts_are_run_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    config = _config(tmp_path)
    outputs: list[Path] = []
    fake_release = media_daily.build_media_release

    def capture_release(release_config):
        outputs.append(Path(release_config.output_dir))
        return fake_release(release_config)

    monkeypatch.setattr(media_daily, "build_media_release", capture_release)
    result = run_media_daily(config, publish=False, skip_crawl=True, skip_ratings=True)

    expected = config.state_root.resolve() / "runs" / result["run_id"] / "release-candidate"
    assert outputs == [expected]
    assert not (config.state_root / "releases" / "staging" / "pointers").exists()


def test_publish_release_is_run_scoped_and_promotes_r2_before_aliyun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    config = _config(tmp_path)
    outputs: list[Path] = []
    promotions: list[str] = []
    fake_release = media_daily.build_media_release

    def capture_release(release_config):
        outputs.append(Path(release_config.output_dir))
        return fake_release(release_config)

    class LocalBackend:
        def __init__(self, *_args, **_kwargs):
            pass

        def promote_current(self, _path):
            promotions.append("aliyun")

    class R2Backend:
        def __init__(self, *_args, **_kwargs):
            pass

        def promote_current(self, _path):
            promotions.append("r2")

    monkeypatch.setattr(media_daily, "build_media_release", capture_release)
    monkeypatch.setattr(media_daily, "FilesystemPublisherBackend", LocalBackend)
    monkeypatch.setattr(media_daily, "WorkerR2PublisherBackend", R2Backend)
    monkeypatch.setattr(
        media_daily,
        "publish_media_release",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="success",
            object_count=1,
            uploaded_count=0,
            reused_count=1,
            current_promoted=False,
        ),
    )
    monkeypatch.setenv("TOKEN", "t" * 64)

    result = run_media_daily(config, publish=True, force_publish=True)

    expected = config.state_root.resolve() / "runs" / result["run_id"] / "release-candidate"
    assert outputs == [expected]
    assert promotions == ["r2", "aliyun"]
    assert result["status"] == "success"
    assert result["current_revision"] == 7


def test_publish_recovers_durable_state_after_post_promotion_crash_without_revision_bump(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    config = _config(tmp_path)

    def same_public_release(release_config):
        output = Path(release_config.output_dir)
        current = output / "staging" / "pointers" / "candidate.json"
        release_dir = output / "staging" / "releases" / "20260729T000000Z-b07630f3"
        _write(
            current,
            {
                "pointer_revision": release_config.pointer_revision,
                "release_id": "20260729T000000Z-b07630f3",
                "manifest_path": "/v1/releases/previous/manifest.json",
                "manifest_sha256": "d" * 64,
            },
        )
        return SimpleNamespace(
            release_id="20260729T000000Z-b07630f3",
            release_dir=str(release_dir),
            current_path=str(current),
            manifest_path=str(release_dir / "v1" / "releases" / "20260729T000000Z-b07630f3" / "manifest.json"),
            manifest_sha256="d" * 64,
            object_count=1,
            reused=True,
            release_reused=True,
            pointer_reused=False,
            counts={"movie": 1, "series": 1, "resources": 2},
        )

    monkeypatch.setattr(media_daily, "build_media_release", same_public_release)

    result = run_media_daily(config, publish=True)

    assert result["status"] == "success"
    assert result["no_change"] is True
    assert result["state_recovered"] is True
    assert result["current_revision"] == 6
    durable = json.loads((config.state_root / "status" / "state.json").read_text(encoding="utf-8"))
    assert durable["current_revision"] == 6
    assert durable["release_id"] == "20260729T000000Z-b07630f3"


def test_publish_archives_only_unpromoted_future_pointer_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer_dir = tmp_path / "releases" / "staging" / "pointers"
    published = pointer_dir / "00000000000000000010-current.json"
    stale_audit = pointer_dir / "00000000000000000011-audit.json"
    stale_failed_publish = pointer_dir / "00000000000000000012-failed.json"
    _write(published, {"pointer_revision": 10, "release_id": "release-10"})
    _write(stale_audit, {"pointer_revision": 11, "release_id": "audit-11"})
    _write(stale_failed_publish, {"pointer_revision": 12, "release_id": "failed-12"})
    monkeypatch.setattr(media_daily, "verify_document", lambda *_args, **_kwargs: None)

    evidence = tmp_path / "run" / "unpromoted-pointer-evidence"
    archived = _archive_unpromoted_pointer_candidates(
        pointer_dir,
        public_revision=10,
        public_release_id="release-10",
        config=_config(tmp_path),
        evidence_dir=evidence,
    )

    assert published.exists()
    assert not stale_audit.exists()
    assert not stale_failed_publish.exists()
    assert (evidence / stale_audit.name).exists()
    assert (evidence / stale_failed_publish.name).exists()
    assert [item["pointer_revision"] for item in archived] == [11, 12]


def test_publish_refuses_to_recover_when_public_revision_conflicts_with_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer_dir = tmp_path / "releases" / "staging" / "pointers"
    conflict = pointer_dir / "00000000000000000010-conflict.json"
    _write(conflict, {"pointer_revision": 10, "release_id": "other-release"})
    monkeypatch.setattr(media_daily, "verify_document", lambda *_args, **_kwargs: None)

    with pytest.raises(ResourceIndexError, match="conflicts with public current"):
        _archive_unpromoted_pointer_candidates(
            pointer_dir,
            public_revision=10,
            public_release_id="release-10",
            config=_config(tmp_path),
            evidence_dir=tmp_path / "evidence",
        )

    assert conflict.exists()


def test_daily_pipeline_can_skip_rating_lookup_for_weekly_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    monkeypatch.setattr(
        media_daily,
        "enrich_feed_file",
        lambda *_args, **_kwargs: pytest.fail("rating lookup must be skipped"),
    )
    config = _config(tmp_path)
    result = run_media_daily(config, publish=False, skip_crawl=True, skip_ratings=True)
    assert result["status"] == "success"
    assert result["candidate_verified"] is True
    assert result["mode"] == "audit"
    assert result["stages"]["rating"]["status"] == "skipped"
    assert "soak" not in result["stages"]
    assert json.loads(
        (config.state_root / "status" / "latest-audit.json").read_text(encoding="utf-8")
    )["run_id"] == result["run_id"]


def test_daily_pipeline_falls_back_to_recent_source_database_on_transient_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    db_path = tmp_path / "state" / "sources" / "sixv_latest_10.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"sqlite-placeholder")
    monkeypatch.setattr(
        media_daily,
        "run_safe_movie_source",
        lambda **_kwargs: (_ for _ in ()).throw(
            ResourceIndexError("LIVE_HTTP_ERROR", "temporary DNS failure", {})
        ),
    )
    monkeypatch.setattr(
        media_daily,
        "safe_movie_source_status",
        lambda **_kwargs: {
            "job": {
                "status": "success",
                "covered_count": 10,
                "db_path": str(db_path),
                "completed_at": media_daily._iso(),
            },
            "source": {"last_completed_at": media_daily._iso()},
        },
    )

    result = run_media_daily(_config(tmp_path), publish=False)
    crawl = result["stages"]["crawl"]
    assert crawl[0]["status"] == "fallback"
    assert crawl[0]["reason"] == "last_known_good_database"
    assert crawl[0]["error"]["error_code"] == "LIVE_HTTP_ERROR"
    assert result["status"] == "success"


def test_daily_pipeline_recovers_required_source_after_one_fallback_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    db_path = tmp_path / "state" / "sources" / "sixv_latest_10.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"sqlite-placeholder")
    calls = {"count": 0}

    def run_source(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ResourceIndexError("LIVE_EMPTY_RESULT", "temporary empty listing", {"http_requests": 1})
        return SimpleNamespace(
            source_id=kwargs["source_id"],
            status="ran",
            reason="scheduled_check",
            target_count=10,
            invocation_http_requests=5,
            reserved_requests=10,
            snapshot_changed=True,
            job_status="success",
            covered_count=10,
            remaining_daily_requests=84,
            db_path=str(db_path),
            feed_path=str(tmp_path / "feed.json"),
        )

    monkeypatch.setattr(media_daily, "run_safe_movie_source", run_source)
    monkeypatch.setattr(
        media_daily,
        "safe_movie_source_status",
        lambda **_kwargs: {
            "job": {
                "status": "success",
                "covered_count": 10,
                "db_path": str(db_path),
                "completed_at": media_daily._iso(),
            },
            "source": {"last_completed_at": media_daily._iso()},
        },
    )
    base = _config(tmp_path)
    config = MediaDailyConfig(
        **{
            **base.__dict__,
            "sources": (DailySourceConfig("sixv", 10, True),),
            "source_fallback_retry_delay_seconds": 0,
        }
    )
    result = run_media_daily(config, publish=False)
    assert calls["count"] == 2
    assert result["quality_status"] == "healthy"
    assert result["degraded_sources"] == []
    assert result["required_degraded_sources"] == []
    assert result["stages"]["crawl"][0]["status"] == "recovered"
    assert result["stages"]["crawl"][0]["reason"] == "fallback_retry"


def test_daily_pipeline_surfaces_required_source_when_recovery_retry_still_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    db_path = tmp_path / "state" / "sources" / "sixv_latest_10.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"sqlite-placeholder")
    calls = {"count": 0}

    def run_source(**_kwargs):
        calls["count"] += 1
        raise ResourceIndexError("LIVE_EMPTY_RESULT", "temporary empty listing", {"http_requests": 1})

    monkeypatch.setattr(media_daily, "run_safe_movie_source", run_source)
    monkeypatch.setattr(
        media_daily,
        "safe_movie_source_status",
        lambda **_kwargs: {
            "job": {
                "status": "success",
                "covered_count": 10,
                "db_path": str(db_path),
                "completed_at": media_daily._iso(),
            },
            "source": {"last_completed_at": media_daily._iso()},
        },
    )
    base = _config(tmp_path)
    config = MediaDailyConfig(
        **{
            **base.__dict__,
            "sources": (DailySourceConfig("sixv", 10, True),),
            "source_fallback_retry_delay_seconds": 0,
        }
    )
    result = run_media_daily(config, publish=False)
    assert calls["count"] == 2
    assert result["status"] == "success"
    assert result["quality_status"] == "degraded"
    assert result["degraded_sources"] == ["sixv"]
    assert result["required_degraded_sources"] == ["sixv"]
    crawl = result["stages"]["crawl"][0]
    assert crawl["status"] == "fallback"
    assert crawl["recovery"]["succeeded"] is False


def test_daily_pipeline_retries_required_source_blocked_by_failure_backoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    db_path = tmp_path / "state" / "sources" / "sixv_latest_10.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"sqlite-placeholder")
    calls = {"count": 0}

    def run_source(**kwargs):
        calls["count"] += 1
        if not kwargs.get("recovery_retry"):
            return SimpleNamespace(
                source_id="sixv",
                status="skipped",
                reason="failure_backoff",
                target_count=10,
                invocation_http_requests=0,
                reserved_requests=0,
                snapshot_changed=None,
                job_status="success",
                covered_count=10,
                remaining_daily_requests=99,
                db_path=str(db_path),
                feed_path=str(tmp_path / "feed.json"),
            )
        return SimpleNamespace(
            source_id="sixv",
            status="ran",
            reason="scheduled_check",
            target_count=10,
            invocation_http_requests=2,
            reserved_requests=10,
            snapshot_changed=True,
            job_status="success",
            covered_count=10,
            remaining_daily_requests=88,
            db_path=str(db_path),
            feed_path=str(tmp_path / "feed.json"),
        )

    monkeypatch.setattr(media_daily, "run_safe_movie_source", run_source)
    monkeypatch.setattr(
        media_daily,
        "safe_movie_source_status",
        lambda **_kwargs: {
            "job": {
                "status": "success",
                "covered_count": 10,
                "db_path": str(db_path),
                "completed_at": media_daily._iso(),
            },
            "source": {"last_completed_at": media_daily._iso()},
        },
    )
    base = _config(tmp_path)
    config = MediaDailyConfig(
        **{
            **base.__dict__,
            "sources": (DailySourceConfig("sixv", 10, True),),
            "source_fallback_retry_delay_seconds": 0,
        }
    )
    result = run_media_daily(config, publish=False)
    assert calls["count"] == 2
    assert result["quality_status"] == "healthy"
    assert result["stages"]["crawl"][0]["status"] == "recovered"


def test_daily_pipeline_retries_required_source_that_returns_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    db_path = tmp_path / "state" / "sources" / "sixv_latest_10.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"sqlite-placeholder")
    calls = {"count": 0}

    def run_source(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return SimpleNamespace(
                source_id="sixv",
                status="ran",
                reason="scheduled_check",
                target_count=10,
                invocation_http_requests=10,
                reserved_requests=10,
                snapshot_changed=True,
                job_status="pending",
                covered_count=8,
                remaining_daily_requests=90,
                db_path=str(db_path),
                feed_path=str(tmp_path / "feed.json"),
            )
        assert kwargs.get("recovery_retry") is True
        return SimpleNamespace(
            source_id="sixv",
            status="ran",
            reason="resume",
            target_count=10,
            invocation_http_requests=2,
            reserved_requests=2,
            snapshot_changed=True,
            job_status="success",
            covered_count=10,
            remaining_daily_requests=88,
            db_path=str(db_path),
            feed_path=str(tmp_path / "feed.json"),
        )

    monkeypatch.setattr(media_daily, "run_safe_movie_source", run_source)
    monkeypatch.setattr(
        media_daily,
        "safe_movie_source_status",
        lambda **_kwargs: {
            "job": {
                "status": "success",
                "covered_count": 10,
                "db_path": str(db_path),
                "completed_at": media_daily._iso(),
            },
            "source": {"last_completed_at": media_daily._iso()},
        },
    )
    base = _config(tmp_path)
    config = MediaDailyConfig(
        **{
            **base.__dict__,
            "sources": (DailySourceConfig("sixv", 10, True),),
            "source_fallback_retry_delay_seconds": 0,
        }
    )
    result = run_media_daily(config, publish=False)
    assert calls["count"] == 2
    assert result["quality_status"] == "healthy"
    assert result["stages"]["crawl"][0]["status"] == "recovered"
    assert result["stages"]["crawl"][0]["initial_result"]["initial_result"]["job_status"] == "pending"


def test_daily_pipeline_marks_nonrequired_pending_source_degraded_without_required_alert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    db_path = tmp_path / "state" / "sources" / "sixv-series_latest_10.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"sqlite-placeholder")

    monkeypatch.setattr(
        media_daily,
        "run_safe_movie_source",
        lambda **_kwargs: SimpleNamespace(
            source_id="sixv-series",
            status="ran",
            reason="scheduled_check",
            target_count=10,
            invocation_http_requests=3,
            reserved_requests=10,
            snapshot_changed=True,
            job_status="pending",
            covered_count=9,
            remaining_daily_requests=91,
            db_path=str(db_path),
            feed_path=str(tmp_path / "feed.json"),
        ),
    )
    base = _config(tmp_path)
    config = MediaDailyConfig(
        **{
            **base.__dict__,
            "sources": (DailySourceConfig("sixv-series", 10, False),),
        }
    )
    result = run_media_daily(config, publish=False)
    assert result["status"] == "success"
    assert result["quality_status"] == "degraded"
    assert result["degraded_sources"] == ["sixv-series"]
    assert result["required_degraded_sources"] == []
    assert result["stages"]["crawl"][0]["job_status"] == "pending"


def test_daily_pipeline_rejects_stale_source_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    db_path = tmp_path / "state" / "sources" / "sixv_latest_10.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"sqlite-placeholder")
    monkeypatch.setattr(
        media_daily,
        "run_safe_movie_source",
        lambda **_kwargs: (_ for _ in ()).throw(
            ResourceIndexError("LIVE_HTTP_ERROR", "temporary DNS failure", {})
        ),
    )
    monkeypatch.setattr(
        media_daily,
        "safe_movie_source_status",
        lambda **_kwargs: {
            "job": {
                "status": "success",
                "covered_count": 10,
                "db_path": str(db_path),
                "completed_at": "2020-01-01T00:00:00Z",
            },
            "source": {"last_completed_at": "2020-01-01T00:00:00Z"},
        },
    )
    base = _config(tmp_path)
    config = MediaDailyConfig(**{**base.__dict__, "source_fallback_max_age_hours": 1})

    with pytest.raises(ResourceIndexError, match="fallback database is too old"):
        run_media_daily(config, publish=False)


def test_candidate_requires_trusted_previous_public_key_when_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    base = _config(tmp_path)
    config = MediaDailyConfig(
        **{
            **base.__dict__,
            "previous_public_key_path": tmp_path / "missing-production-public.pem",
        }
    )
    with pytest.raises(ResourceIndexError, match="trusted previous"):
        run_media_daily(config, publish=False)


def test_candidate_failure_resets_soak_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    config = _config(tmp_path)
    run_media_daily(config, publish=False)
    monkeypatch.setattr(
        media_daily,
        "build_media_release",
        lambda _config: (_ for _ in ()).throw(ResourceIndexError("CONFIG_ERROR", "candidate failed", {})),
    )

    with pytest.raises(ResourceIndexError, match="candidate failed"):
        run_media_daily(config, publish=False)

    soak = json.loads((config.state_root / "status" / "candidate-soak.json").read_text(encoding="utf-8"))
    assert soak["last_status"] == "failed"
    assert soak["consecutive_days"] == 0
    assert soak["ready_for_promotion"] is False


def test_cleanup_failure_does_not_mask_successful_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    real_prune = media_daily.prune_media_state
    calls = 0

    def flaky_prune(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("cleanup unavailable")
        return real_prune(*args, **kwargs)

    monkeypatch.setattr(media_daily, "prune_media_state", flaky_prune)
    result = run_media_daily(_config(tmp_path), publish=False)
    assert result["status"] == "success"
    assert result["stages"]["maintenance"]["cleanup_warning"]["type"] == "OSError"


def test_daily_pipeline_persists_and_rotates_rating_lookup_offsets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    offsets: list[int] = []

    def enrich(_path: Path, _resolver, **kwargs):
        start = int(kwargs["start_offset"])
        offsets.append(start)
        return {
            "changed_items": 0,
            "errors": 0,
            "next_offset": start + 2,
            "lookup_attempts": kwargs["lookup_limit"],
        }

    monkeypatch.setattr(media_daily, "enrich_feed_file", enrich)
    base = _config(tmp_path)
    config = MediaDailyConfig(
        **{
            **base.__dict__,
            "rating_lookup_limit_per_feed": 2,
        }
    )

    first = run_media_daily(config, publish=False)
    second = run_media_daily(config, publish=False, force_publish=True)

    assert offsets == [0, 0, 2, 2]
    assert first["stages"]["rating"]["progress"]["movie_offset"] == 2
    assert second["stages"]["rating"]["progress"]["series_offset"] == 4
    progress = json.loads(
        (config.state_root / "ratings" / "progress.json").read_text(encoding="utf-8")
    )
    assert progress["movie_offset"] == 4
    assert progress["series_offset"] == 4
    assert progress["lookup_limit_per_feed"] == 2


def test_daily_pipeline_restores_persisted_four_source_ratings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fakes(monkeypatch)
    seen_before_lookup: list[dict] = []

    def enrich(path: Path, _resolver, **_kwargs):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        item = payload["items"][0]
        seen_before_lookup.append(dict(item))
        item.update(
            {
                "imdb_rating": item.get("imdb_rating") or 7.7,
                "imdb_rating_text": item.get("imdb_rating_text") or "7.7/10",
                "douban_rating": item.get("douban_rating") or 8.2,
                "douban_rating_text": item.get("douban_rating_text") or "8.2/10",
                "rotten_tomatoes_rating": item.get("rotten_tomatoes_rating") or 90,
                "rotten_tomatoes_rating_text": item.get("rotten_tomatoes_rating_text") or "90%",
                "rotten_tomatoes_url": item.get("rotten_tomatoes_url") or "https://www.rottentomatoes.com/m/test",
                "bangumi_rating": item.get("bangumi_rating") or 7.3,
                "bangumi_rating_text": item.get("bangumi_rating_text") or "7.3/10",
                "bangumi_subject_id": item.get("bangumi_subject_id") or "123",
            }
        )
        _write(Path(path), payload)
        return {"changed_items": 1, "errors": 0}

    monkeypatch.setattr(media_daily, "enrich_feed_file", enrich)
    config = _config(tmp_path)

    run_media_daily(config, publish=False)
    run_media_daily(config, publish=False, force_publish=True)

    assert len(seen_before_lookup) == 4
    assert seen_before_lookup[0].get("rotten_tomatoes_rating") is None
    assert seen_before_lookup[1].get("bangumi_rating") is None
    assert seen_before_lookup[2]["rotten_tomatoes_rating"] == 90.0
    assert seen_before_lookup[2]["bangumi_rating"] == 7.3
    assert seen_before_lookup[3]["rotten_tomatoes_rating"] == 90.0
    assert seen_before_lookup[3]["bangumi_rating"] == 7.3

    state = json.loads(
        (config.state_root / "ratings" / "media-ratings.json").read_text(encoding="utf-8")
    )
    assert len(state["items"]) == 2
    assert state["items"]["movie:1"]["ratings"]["rotten_tomatoes_rating"] == 90.0
    assert state["items"]["series:1"]["ratings"]["bangumi_rating"] == 7.3
