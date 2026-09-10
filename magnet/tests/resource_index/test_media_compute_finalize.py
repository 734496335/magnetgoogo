from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline import media_compute_finalize as finalize
from magnet.resource_index.pipeline.media_compute_handoff import build_compute_handoff
from magnet.resource_index.pipeline.media_daily import DailySourceConfig, FreshnessGroupConfig, MediaDailyConfig


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(json.dumps(value), encoding="utf-8")


def _config(tmp_path: Path) -> MediaDailyConfig:
    private = tmp_path / "private.pem"
    public = tmp_path / "public.pem"
    private.write_text("private", encoding="utf-8")
    public.write_text("public", encoding="utf-8")
    return MediaDailyConfig(
        state_root=tmp_path / "state",
        public_root=tmp_path / "public-root",
        private_key_path=private,
        public_key_path=public,
        worker_url="https://worker.example",
        worker_token_env="TOKEN",
        r2_public_base="https://media.example",
        aliyun_public_base="https://cn.example/media",
        min_app_version="0.2.3",
        min_movies=1,
        min_series=1,
        sources=(DailySourceConfig("sixv", 1, True), DailySourceConfig("meijumi", 1, False, "series")),
        freshness_groups=(FreshnessGroupConfig("series", 1),),
    )


def _handoff(
    tmp_path: Path,
    *,
    previous_revision: int = 40,
    run_id: str = "compute-run",
    content_sha256: str = "a" * 64,
    accepted_cross_season_count: int = 0,
    required_degraded_sources: list[str] | None = None,
    failed_freshness_groups: list[str] | None = None,
    fresh_count: int = 1,
    finished_at: str | None = None,
    include_finished_at: bool = True,
) -> str:
    movie_feed = tmp_path / "movie.json"
    series_feed = tmp_path / "series.json"
    movie_bundle = tmp_path / "movie-bundle"
    series_bundle = tmp_path / "series-bundle"
    _write(movie_feed, {"items": [{"movie_id": "m", "resources": [{"resource_type": "magnet"}]}]})
    _write(series_feed, {"items": [{"movie_id": "s", "resources": [{"resource_type": "magnet"}]}]})
    _write(movie_bundle / "feed.json", {"items": [{"movie_id": "m"}]})
    _write(movie_bundle / "cover_failures.json", {"failed_count": 0})
    _write(series_bundle / "feed.json", {"items": [{"movie_id": "s"}]})
    _write(series_bundle / "cover_failures.json", {"failed_count": 0})
    status = {
        "status": "success",
        "mode": "compute",
        "run_id": run_id,
        "compute_candidate": True,
        "compute_verified": True,
        "published": False,
        "previous_revision": previous_revision,
        "content_sha256": content_sha256,
        "movie_count": 1,
        "series_count": 1,
        "resource_count": 2,
        "required_degraded_sources": required_degraded_sources or [],
        "failed_freshness_groups": failed_freshness_groups or [],
        "freshness_groups": {"series": {"status": "pass" if fresh_count >= 1 else "fail", "fresh_count": fresh_count, "member_count": 1, "min_fresh": 1}},
        "stages": {
            "aggregate": {"quality": {"status": "pass" if accepted_cross_season_count == 0 else "fail", "bad_label_count": 0, "accepted_cross_season_count": accepted_cross_season_count, "weak_episode_title_count": 0, "empty_resource_item_count": 0}},
            "magnet_only": {"status": "pass", "total_magnet_resource_count": 2, "total_item_count": 2},
            "covers": {"movie": {"audit": {"status": "pass"}}, "series": {"audit": {"status": "pass"}}},
        },
    }
    if include_finished_at:
        status["finished_at"] = finished_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return build_compute_handoff(outbox_root=tmp_path / "outbox", run_id=run_id, status=status, movie_feed_path=movie_feed, series_feed_path=series_feed, movie_bundle=movie_bundle, series_bundle=series_bundle)["package_path"]


def _install_fakes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, revision: int = 40) -> None:
    current = tmp_path / "previous-current.json"
    manifest = tmp_path / "previous-manifest.json"
    _write(current, {"pointer_revision": revision, "release_id": "old", "manifest_path": "/v1/releases/old/manifest.json", "manifest_sha256": "d" * 64})
    _write(manifest, {"release_id": "old"})
    monkeypatch.setattr(finalize, "_reconcile_online_controls", lambda *_args, **_kwargs: ({"pointer_revision": revision, "release_id": "old"}, manifest, current, {"status": "pass"}))

    def build(config):
        release_dir = Path(config.output_dir) / "staging" / "releases" / "new"
        pointer = Path(config.output_dir) / "staging" / "pointers" / "new.json"
        _write(release_dir / "v1" / "releases" / "new" / "manifest.json", {"release_id": "new"})
        _write(pointer, {"pointer_revision": config.pointer_revision, "release_id": "new", "manifest_path": "/v1/releases/new/manifest.json", "manifest_sha256": "c" * 64})
        return SimpleNamespace(release_id="new", release_dir=str(release_dir), current_path=str(pointer), manifest_path=str(release_dir / "v1/releases/new/manifest.json"), manifest_sha256="c" * 64, object_count=1, reused=False, release_reused=False, pointer_reused=False, counts={"movie": 1, "series": 1, "resources": 2})

    monkeypatch.setattr(finalize, "build_media_release", build)


def _install_publish_fakes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, config: MediaDailyConfig, events: list[str]) -> None:
    _install_fakes(monkeypatch, tmp_path)
    previous = tmp_path / "previous-current.json"
    live_local = config.public_root / "v1" / "current.json"
    live_local.parent.mkdir(parents=True, exist_ok=True)
    live_local.write_bytes(previous.read_bytes())

    class AliyunBackend:
        def __init__(self, _root: Path) -> None:
            pass

        def promote_current(self, _current: Path) -> None:
            events.append("aliyun-promote")

    class R2Backend:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def promote_current(self, _current: Path) -> None:
            events.append("r2-promote")

    monkeypatch.setattr(finalize, "FilesystemPublisherBackend", AliyunBackend)
    monkeypatch.setattr(finalize, "WorkerR2PublisherBackend", R2Backend)
    monkeypatch.setattr(finalize, "publish_media_release", lambda backend, _config: SimpleNamespace(status="pass", backend=type(backend).__name__))
    monkeypatch.setattr(finalize, "_verify_public_control", lambda base, _current: {"status": "pass", "base": base})
    monkeypatch.setenv("TOKEN", "x" * 32)


def test_finalize_compute_handoff_builds_signed_candidate_without_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path)
    _install_fakes(monkeypatch, tmp_path)
    result = finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=False)
    assert result["status"] == "success"
    assert result["candidate_verified"] is True
    assert result["candidate_revision"] == 41
    assert result["published"] is False


def test_finalize_compute_handoff_rejects_stale_compute_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path, previous_revision=39)
    _install_fakes(monkeypatch, tmp_path, revision=40)
    with pytest.raises(ResourceIndexError, match="stale"):
        finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=False)


def test_finalize_compute_handoff_rejects_degraded_quality_before_signing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path, accepted_cross_season_count=1)
    _install_fakes(monkeypatch, tmp_path)
    with pytest.raises(ResourceIndexError, match="aggregate quality did not pass"):
        finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=False)


def test_finalize_compute_handoff_rejects_required_degradation_before_signing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path, required_degraded_sources=["sixv"])
    monkeypatch.setattr(finalize, "build_media_release", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not sign degraded handoff")))
    with pytest.raises(ResourceIndexError, match="degraded required sources"):
        finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=False)


def test_finalize_compute_handoff_rejects_failed_freshness_group_before_signing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path, failed_freshness_groups=["series"], fresh_count=0)
    monkeypatch.setattr(finalize, "build_media_release", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not sign stale handoff")))
    with pytest.raises(ResourceIndexError, match="failed freshness groups"):
        finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=False)


def test_finalize_same_compute_run_is_idempotent_after_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path)
    config = _config(tmp_path)
    state = config.state_root / "status" / "compute-finalizer-state.json"
    _write(state, {"schema_version": "media-compute-finalizer-state/1", "compute_run_id": "compute-run", "content_sha256": "a" * 64, "current_revision": 41, "release_id": "new"})
    monkeypatch.setattr(finalize, "build_media_release", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not rebuild")))

    result = finalize.finalize_compute_handoff(config, package_path=package, publish=True)

    assert result["already_finalized"] is True
    assert result["no_change"] is True
    assert result["current_revision"] == 41
    assert result["published"] is False


def test_finalize_new_run_with_unchanged_content_does_not_advance_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path, run_id="compute-run-2")
    config = _config(tmp_path)
    state = config.state_root / "status" / "compute-finalizer-state.json"
    _write(state, {"schema_version": "media-compute-finalizer-state/1", "compute_run_id": "compute-run-1", "content_sha256": "a" * 64, "current_revision": 40, "release_id": "old"})
    _install_fakes(monkeypatch, tmp_path, revision=40)
    monkeypatch.setattr(finalize, "build_media_release", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not rebuild unchanged content")))

    result = finalize.finalize_compute_handoff(config, package_path=package, publish=True)

    assert result["content_unchanged"] is True
    assert result["published"] is False
    assert result["current_revision"] == 40
    updated = json.loads(state.read_text(encoding="utf-8"))
    assert updated["compute_run_id"] == "compute-run-2"


def test_finalize_rejects_missing_finished_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path, include_finished_at=False)
    with pytest.raises(ResourceIndexError, match="finished_at is required"):
        finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=False)


def test_finalize_rejects_expired_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(finalize, "_utc_now", lambda: now)
    package = _handoff(tmp_path, finished_at=(now - timedelta(hours=13)).isoformat())
    with pytest.raises(ResourceIndexError, match="older than maximum age"):
        finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=False)


def test_finalize_rejects_far_future_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(finalize, "_utc_now", lambda: now)
    package = _handoff(tmp_path, finished_at=(now + timedelta(minutes=16)).isoformat())
    with pytest.raises(ResourceIndexError, match="too far in the future"):
        finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=False)


def test_finalize_rejects_naive_finished_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path, finished_at="2026-09-10T07:00:00")
    with pytest.raises(ResourceIndexError, match="timezone-aware"):
        finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=False)


def test_finalize_publish_requires_worker_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path)
    _install_fakes(monkeypatch, tmp_path)
    monkeypatch.delenv("TOKEN", raising=False)
    with pytest.raises(ResourceIndexError, match="Worker credentials"):
        finalize.finalize_compute_handoff(_config(tmp_path), package_path=package, publish=True)


def test_finalize_publish_rejects_changed_local_pointer_before_r2_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path)
    config = _config(tmp_path)
    events: list[str] = []
    _install_publish_fakes(monkeypatch, tmp_path, config, events)
    _write(config.public_root / "v1" / "current.json", {"pointer_revision": 999})

    with pytest.raises(ResourceIndexError, match="local current changed"):
        finalize.finalize_compute_handoff(config, package_path=package, publish=True)

    assert events == []


def test_finalize_publish_promotes_r2_before_aliyun_and_persists_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path)
    config = _config(tmp_path)
    events: list[str] = []
    _install_publish_fakes(monkeypatch, tmp_path, config, events)

    result = finalize.finalize_compute_handoff(config, package_path=package, publish=True)

    assert events == ["r2-promote", "aliyun-promote"]
    assert result["published"] is True
    assert result["current_revision"] == 41
    state = json.loads((config.state_root / "status" / "compute-finalizer-state.json").read_text(encoding="utf-8"))
    assert state["compute_run_id"] == "compute-run"
    assert state["current_revision"] == 41


def test_finalize_publish_recovers_after_aliyun_promotion_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path)
    config = _config(tmp_path)
    events: list[str] = []
    _install_publish_fakes(monkeypatch, tmp_path, config, events)
    reconcile_calls = 0
    previous = tmp_path / "previous-current.json"
    manifest = tmp_path / "previous-manifest.json"

    def reconcile(_config: MediaDailyConfig, _output: Path, *, publish: bool):
        nonlocal reconcile_calls
        reconcile_calls += 1
        if reconcile_calls == 1:
            return ({"pointer_revision": 40, "release_id": "old"}, manifest, previous, {"status": "pass"})
        events.append("recovery")
        assert publish is True
        return ({"pointer_revision": 41, "release_id": "new"}, manifest, previous, {"status": "pass", "action": "recovered"})

    class FailingAliyunBackend:
        def __init__(self, _root: Path) -> None:
            pass

        def promote_current(self, _current: Path) -> None:
            events.append("aliyun-promote")
            raise RuntimeError("simulated Aliyun promotion failure")

    monkeypatch.setattr(finalize, "_reconcile_online_controls", reconcile)
    monkeypatch.setattr(finalize, "FilesystemPublisherBackend", FailingAliyunBackend)

    result = finalize.finalize_compute_handoff(config, package_path=package, publish=True)

    assert events == ["r2-promote", "aliyun-promote", "recovery"]
    assert reconcile_calls == 2
    assert result["published"] is True


def test_finalize_publish_surfaces_aliyun_failure_when_recovery_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _handoff(tmp_path)
    config = _config(tmp_path)
    events: list[str] = []
    _install_publish_fakes(monkeypatch, tmp_path, config, events)
    previous = tmp_path / "previous-current.json"
    manifest = tmp_path / "previous-manifest.json"
    reconcile_calls = 0

    def reconcile(_config: MediaDailyConfig, _output: Path, *, publish: bool):
        nonlocal reconcile_calls
        reconcile_calls += 1
        if reconcile_calls == 1:
            return ({"pointer_revision": 40, "release_id": "old"}, manifest, previous, {"status": "pass"})
        events.append("recovery-failed")
        raise RuntimeError("simulated recovery failure")

    class FailingAliyunBackend:
        def __init__(self, _root: Path) -> None:
            pass

        def promote_current(self, _current: Path) -> None:
            events.append("aliyun-promote")
            raise RuntimeError("simulated Aliyun promotion failure")

    monkeypatch.setattr(finalize, "_reconcile_online_controls", reconcile)
    monkeypatch.setattr(finalize, "FilesystemPublisherBackend", FailingAliyunBackend)

    with pytest.raises(RuntimeError, match="simulated Aliyun promotion failure"):
        finalize.finalize_compute_handoff(config, package_path=package, publish=True)

    assert events == ["r2-promote", "aliyun-promote", "recovery-failed"]
    assert not (config.state_root / "status" / "compute-finalizer-state.json").exists()
