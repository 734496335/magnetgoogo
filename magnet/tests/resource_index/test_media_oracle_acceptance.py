from __future__ import annotations

import json
from pathlib import Path

import pytest

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline.media_daily import DailySourceConfig, FreshnessGroupConfig, MediaDailyConfig
from magnet.resource_index.pipeline.media_oracle_acceptance import verify_oracle_media_candidate


def _config(tmp_path: Path) -> MediaDailyConfig:
    return MediaDailyConfig(
        state_root=tmp_path / "state",
        public_root=tmp_path / "public",
        private_key_path=tmp_path / "private.pem",
        public_key_path=tmp_path / "public.pem",
        worker_url="https://worker.example",
        worker_token_env="TOKEN",
        r2_public_base="https://media.example",
        aliyun_public_base="https://cn.example/media",
        min_app_version="0.2.3",
        min_movies=190,
        min_series=200,
        sources=(
            DailySourceConfig("sixv", 100, True),
            DailySourceConfig("dytt8899", 250),
            DailySourceConfig("meijumi", 100, False, "series"),
            DailySourceConfig("sixv-series", 100, False, "series"),
            DailySourceConfig("bitba-series", 50, False, "series"),
            DailySourceConfig("mjf-series", 50, False, "series"),
        ),
        freshness_groups=(FreshnessGroupConfig("series", 2),),
    )


def _pointer(revision: int = 40) -> bytes:
    return json.dumps(
        {
            "pointer_revision": revision,
            "release_id": "public-release",
            "manifest_path": "/v1/releases/public-release/manifest.json",
            "manifest_sha256": "a" * 64,
        },
        separators=(",", ":"),
    ).encode()


def _status() -> dict:
    crawl = [
        {
            "source_id": "sixv",
            "status": "ran",
            "job_status": "success",
            "publish_ready": True,
            "magnet_item_count": 90,
            "magnet_resource_count": 120,
            "freshness_required": True,
            "freshness_group": None,
            "freshness_magnet_status": "pass",
        },
        {
            "source_id": "dytt8899",
            "status": "paused",
            "job_status": "partial",
            "magnet_item_count": 100,
            "magnet_resource_count": 150,
            "freshness_required": False,
            "freshness_group": None,
        },
    ]
    for source_id in ("meijumi", "sixv-series", "bitba-series", "mjf-series"):
        crawl.append(
            {
                "source_id": source_id,
                "status": "ran",
                "job_status": "success",
                "publish_ready": True,
                "magnet_item_count": 20,
                "magnet_resource_count": 100,
                "freshness_required": False,
                "freshness_group": "series",
                "freshness_magnet_status": "pass",
            }
        )
    return {
        "schema_version": "media-daily-status/1",
        "status": "success",
        "mode": "candidate",
        "run_id": "oracle-shadow-run",
        "publish_candidate": True,
        "candidate_verified": True,
        "previous_revision": 40,
        "candidate_revision": 41,
        "release_id": "candidate-release",
        "movie_count": 421,
        "series_count": 538,
        "resource_count": 6663,
        "required_degraded_sources": [],
        "failed_freshness_groups": [],
        "freshness_groups": {
            "series": {
                "status": "pass",
                "min_fresh": 2,
                "member_count": 4,
                "fresh_count": 4,
                "fresh_sources": ["meijumi", "sixv-series", "bitba-series", "mjf-series"],
                "degraded_sources": [],
                "no_magnet_sources": [],
            }
        },
        "stages": {
            "crawl": crawl,
            "aggregate": {
                "quality": {
                    "status": "pass",
                    "bad_label_count": 0,
                    "accepted_cross_season_count": 0,
                    "weak_episode_title_count": 0,
                    "empty_resource_item_count": 0,
                }
            },
            "magnet_only": {
                "status": "pass",
                "total_item_count": 959,
                "total_magnet_resource_count": 6663,
            },
            "covers": {
                "movie": {"audit": {"status": "pass"}},
                "series": {"audit": {"status": "pass"}},
            },
        },
    }


def _verify(tmp_path: Path, status: dict | None = None, **overrides):
    pointer = _pointer()
    values = {
        "status": status or _status(),
        "config": _config(tmp_path),
        "r2_before": pointer,
        "r2_after": pointer,
        "aliyun_before": pointer,
        "aliyun_after": pointer,
        "require_all_group_members_fresh": True,
    }
    values.update(overrides)
    return verify_oracle_media_candidate(**values)


def test_oracle_candidate_acceptance_passes_strict_migration_gate(tmp_path: Path) -> None:
    report = _verify(tmp_path)

    assert report["status"] == "pass"
    assert report["public_revision"] == 40
    assert report["candidate_revision"] == 41
    assert report["movie_count"] == 421
    assert report["series_count"] == 538
    assert report["resource_count"] == 6663
    assert report["public_pointer_unchanged"] is True
    assert report["required_sources_fresh"] is True
    assert report["freshness_groups_all_fresh"] is True


def test_oracle_candidate_acceptance_rejects_any_public_pointer_mutation(tmp_path: Path) -> None:
    with pytest.raises(ResourceIndexError, match="R2 current pointer changed"):
        _verify(tmp_path, r2_after=_pointer(41))


def test_oracle_candidate_acceptance_rejects_required_source_without_current_magnet(tmp_path: Path) -> None:
    status = _status()
    sixv = status["stages"]["crawl"][0]
    sixv["magnet_item_count"] = 0
    sixv["freshness_magnet_status"] = "fail"

    with pytest.raises(ResourceIndexError, match="no current magnet evidence"):
        _verify(tmp_path, status=status)


def test_oracle_candidate_acceptance_requires_all_series_sources_fresh_by_default(tmp_path: Path) -> None:
    status = _status()
    group = status["freshness_groups"]["series"]
    group["fresh_count"] = 3
    group["degraded_sources"] = ["meijumi"]

    with pytest.raises(ResourceIndexError, match="all freshness group members fresh"):
        _verify(tmp_path, status=status)

    report = _verify(tmp_path, status=status, require_all_group_members_fresh=False)
    assert report["status"] == "pass"
    assert report["freshness_groups_all_fresh"] is False


def test_oracle_candidate_acceptance_rejects_publish_stage_or_low_counts(tmp_path: Path) -> None:
    published = _status()
    published["stages"]["publish"] = {"r2": {"status": "success"}}
    with pytest.raises(ResourceIndexError, match="publication stage"):
        _verify(tmp_path, status=published)

    low = _status()
    low["movie_count"] = 189
    low["stages"]["magnet_only"]["total_item_count"] = 727
    with pytest.raises(ResourceIndexError, match="below production floor"):
        _verify(tmp_path, status=low)


def test_oracle_candidate_acceptance_rejects_aggregate_quality_regression(tmp_path: Path) -> None:
    bad_quality = _status()
    bad_quality["stages"]["aggregate"]["quality"]["accepted_cross_season_count"] = 1
    bad_quality["stages"]["aggregate"]["quality"]["status"] = "fail"
    with pytest.raises(ResourceIndexError, match="aggregate quality gate"):
        _verify(tmp_path, status=bad_quality)


def test_oracle_candidate_acceptance_rejects_magnet_or_cover_inconsistency(tmp_path: Path) -> None:
    wrong_magnets = _status()
    wrong_magnets["stages"]["magnet_only"]["total_magnet_resource_count"] = 6662
    with pytest.raises(ResourceIndexError, match="does not match magnet-only"):
        _verify(tmp_path, status=wrong_magnets)

    bad_cover = _status()
    bad_cover["stages"]["covers"]["series"]["audit"]["status"] = "fail"
    with pytest.raises(ResourceIndexError, match="cover audit"):
        _verify(tmp_path, status=bad_cover)
