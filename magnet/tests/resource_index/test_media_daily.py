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
    previous = Path("previous-manifest.json")
    monkeypatch.setattr(
        media_daily,
        "_online_control",
        lambda _base, run_dir: (
            {"pointer_revision": 6, "release_id": "20260729T000000Z-b07630f3"},
            run_dir / previous,
        ),
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
    assert load_media_daily_config(config_path).min_app_version == "0.2.3"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("rating_lookup_limit_per_feed", 0),
        ("retention_runs", 0),
        ("retention_status_history", -1),
        ("retention_releases", "3"),
        ("disk_max_used_percent", 100),
        ("disk_min_free_bytes", -1),
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
        {"schema_version": "media-daily-state/1", "content_sha256": first["content_sha256"]},
    )

    second = run_media_daily(config, publish=True)
    assert second["status"] == "success"
    assert second["no_change"] is True
    assert second["published"] is False
    assert second["resource_count"] == 2
    assert second["stages"]["magnet_only"]["movie"]["removed_non_magnet_resource_count"] == 1
    assert second["stages"]["magnet_only"]["series"]["removed_non_magnet_resource_count"] == 1


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
    result = run_media_daily(_config(tmp_path), publish=False, skip_ratings=True)
    assert result["status"] == "success"
    assert result["candidate_verified"] is True
    assert result["stages"]["rating"]["status"] == "skipped"
    assert "soak" not in result["stages"]


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
