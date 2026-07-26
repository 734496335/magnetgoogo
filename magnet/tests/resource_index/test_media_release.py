from __future__ import annotations

import json
from pathlib import Path

import pytest

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.release.builder import (
    MediaReleaseConfig,
    _acquire_release_lock,
    _release_release_lock,
    build_media_release,
    verify_media_release,
)
from magnet.resource_index.release.protocol import (
    generate_ed25519_keypair,
    sha256_bytes,
    sign_document,
    verify_document,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_signed_json(path: Path, value: dict[str, object], private_key: Path) -> None:
    _write_json(path, sign_document(value, private_key))


def _item(
    media_id: str,
    *,
    kind: str,
    cover_url: str,
    country: str,
    season: int | None = None,
    resource_season: int | None = None,
) -> dict[str, object]:
    return {
        "rank": 1,
        "movie_id": media_id,
        "source_id": "source-must-not-leak",
        "detail_url": "https://source.invalid/detail",
        "content_kind": kind,
        "title": f"Title {media_id}",
        "original_title": "Original",
        "year": 2026,
        "update_date": "2026-07-26",
        "release_date": "2026-07-20",
        "countries": [country],
        "genres": ["剧情"],
        "languages": ["中文"],
        "directors": ["Director"],
        "actors": ["Actor"],
        "synopsis": "A full synopsis that belongs in detail only.",
        "recommended": kind == "movie",
        "highlight_labels": ["推荐"] if kind == "movie" else [],
        "update_status": "更新至第2集" if kind == "series" else None,
        "season_number": season,
        "cover_source_url": cover_url,
        "resources": [
            {
                "display_title": "S01E01 · 1080P" if kind == "series" else "1080P",
                "info_hash": ("a" if kind == "movie" else "b") * 40,
                "provider": "magnet",
                "quality_tags": ["1080P"],
                "resource_type": "magnet",
                "season_number": resource_season,
                "episode_start": 1 if kind == "series" else None,
                "episode_end": 1 if kind == "series" else None,
                "url": "magnet:?xt=urn:btih:" + (("a" if kind == "movie" else "b") * 40),
            }
        ],
    }


def _cover_bundle(root: Path, name: str, source_url: str, payload: bytes) -> Path:
    bundle = root / name
    digest = sha256_bytes(payload)
    cover_path = bundle / "covers" / f"{digest}.jpg"
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(payload)
    _write_json(
        bundle / "cover_manifest.json",
        {
            "schema_version": "media-cover-manifest/1",
            "assets": {
                source_url: {
                    "path": f"covers/{digest}.jpg",
                    "source_url": source_url,
                    "mime_type": "image/jpeg",
                    "content_hash": digest,
                    "width": 300,
                    "height": 480,
                    "byte_size": len(payload),
                }
            },
        },
    )
    return bundle


def _setup(tmp_path: Path, *, cross_season: bool = False) -> MediaReleaseConfig:
    movie_cover_url = "https://covers.invalid/movie.jpg"
    series_cover_url = "https://covers.invalid/series.jpg"
    movie_feed = tmp_path / "movies.json"
    series_feed = tmp_path / "series.json"
    generated_at = "2026-07-26T15:00:00Z"
    _write_json(
        movie_feed,
        {
            "schema_version": "media-feed/1",
            "generated_at": generated_at,
            "content_kind_filter": "movie",
            "items": [
                _item(
                    "movie:1",
                    kind="movie",
                    cover_url=movie_cover_url,
                    country="中国",
                )
            ],
        },
    )
    _write_json(
        series_feed,
        {
            "schema_version": "media-feed/1",
            "generated_at": generated_at,
            "content_kind_filter": "series",
            "items": [
                _item(
                    "series:1",
                    kind="series",
                    cover_url=series_cover_url,
                    country="美国",
                    season=1,
                    resource_season=2 if cross_season else 1,
                )
            ],
        },
    )
    private_key = tmp_path / "keys" / "private.pem"
    public_key = tmp_path / "keys" / "public.pem"
    generate_ed25519_keypair(private_key, public_key)
    return MediaReleaseConfig(
        movie_feed_path=movie_feed,
        series_feed_path=series_feed,
        movie_cover_bundle=_cover_bundle(tmp_path, "movie-bundle", movie_cover_url, b"movie-cover"),
        series_cover_bundle=_cover_bundle(tmp_path, "series-bundle", series_cover_url, b"series-cover"),
        output_dir=tmp_path / "release-output",
        private_key_path=private_key,
        public_key_path=public_key,
        pointer_revision=7,
        min_movies=1,
        min_series=1,
        max_object_bytes=64 * 1024,
    )


def test_signing_key_initialization_is_idempotent(tmp_path: Path) -> None:
    private_key = tmp_path / "keys" / "private.pem"
    public_key = tmp_path / "keys" / "public.pem"
    first = generate_ed25519_keypair(private_key, public_key)
    second = generate_ed25519_keypair(private_key, public_key)

    assert second["key_state"] == "existing"
    assert second["signature_key_id"] == first["signature_key_id"]


def test_signing_key_public_half_recovers_from_private_key(tmp_path: Path) -> None:
    private_key = tmp_path / "keys" / "private.pem"
    public_key = tmp_path / "keys" / "public.pem"
    first = generate_ed25519_keypair(private_key, public_key)
    public_key.unlink()

    recovered = generate_ed25519_keypair(private_key, public_key)
    assert recovered["key_state"] == "public_key_recovered"
    assert recovered["signature_key_id"] == first["signature_key_id"]
    verify_document(sign_document({"value": 1}, private_key), public_key)


def test_signing_key_mismatch_repairs_public_from_private(tmp_path: Path) -> None:
    private_key = tmp_path / "keys-a" / "private.pem"
    public_key = tmp_path / "keys-a" / "public.pem"
    first = generate_ed25519_keypair(private_key, public_key)
    other_private = tmp_path / "keys-b" / "private.pem"
    other_public = tmp_path / "keys-b" / "public.pem"
    generate_ed25519_keypair(other_private, other_public)
    public_key.write_bytes(other_public.read_bytes())

    repaired = generate_ed25519_keypair(private_key, public_key)
    assert repaired["key_state"] == "public_key_repaired"
    assert repaired["signature_key_id"] == first["signature_key_id"]
    verify_document(sign_document({"value": 1}, private_key), public_key)


def test_signing_key_paths_must_be_distinct(tmp_path: Path) -> None:
    shared = tmp_path / "same.pem"
    with pytest.raises(ResourceIndexError, match="different paths"):
        generate_ed25519_keypair(shared, shared)


def test_builds_signed_content_addressed_release_and_verifies(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    result = build_media_release(config)

    assert result.reused is False
    assert result.release_reused is False
    assert result.pointer_reused is False
    assert result.release_id == "20260726T000000Z-" + result.release_id.rsplit("-", 1)[1]
    assert result.counts == {
        "movie": 1,
        "series": 1,
        "resources": 2,
        "covers": 2,
        "details": 2,
        "catalog_objects": 4,
    }

    report = verify_media_release(
        result.release_dir,
        config.public_key_path,
        result.current_path,
    )
    assert report["status"] == "pass"
    assert report["pointer_revision"] == 7
    assert report["verified_objects"] == result.object_count

    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    movie_catalog_ref = manifest["channels"]["movie"]["latest_pages"][0]
    catalog_path = Path(result.release_dir) / movie_catalog_ref["path"].lstrip("/")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    card = catalog["items"][0]
    assert "synopsis" not in card
    assert "resources" not in card
    assert "source_id" not in card
    assert card["detail_object"]["hash"]
    assert card["cover"]["hash"]


def test_identical_build_reuses_the_same_immutable_release(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    first = build_media_release(config)
    second = build_media_release(config)

    assert second.reused is True
    assert second.release_reused is True
    assert second.pointer_reused is True
    assert second.release_id == first.release_id
    assert second.manifest_sha256 == first.manifest_sha256


def test_crawler_timestamp_change_does_not_create_a_new_release(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    first = build_media_release(config)
    for feed_path in (config.movie_feed_path, config.series_feed_path):
        feed = json.loads(feed_path.read_text(encoding="utf-8"))
        feed["generated_at"] = "2026-07-26T23:59:59Z"
        _write_json(feed_path, feed)

    second = build_media_release(config)
    assert second.reused is True
    assert second.release_reused is True
    assert second.pointer_reused is True
    assert second.release_id == first.release_id
    assert second.manifest_sha256 == first.manifest_sha256


def test_higher_pointer_revision_reuses_release_but_creates_new_pointer(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    first = build_media_release(config)
    second_config = MediaReleaseConfig(**{**config.__dict__, "pointer_revision": 8})
    second = build_media_release(second_config)

    assert second.reused is False
    assert second.release_reused is True
    assert second.pointer_reused is False
    assert second.release_id == first.release_id
    assert second.manifest_sha256 == first.manifest_sha256
    assert second.current_path != first.current_path
    report = verify_media_release(
        second.release_dir,
        second_config.public_key_path,
        second.current_path,
    )
    assert report["pointer_revision"] == 8


def test_concurrent_build_is_rejected_and_lock_is_released(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    lock_path = config.output_dir / "staging" / ".build.lock"
    lock = _acquire_release_lock(lock_path)
    try:
        with pytest.raises(ResourceIndexError, match="already running"):
            build_media_release(config)
    finally:
        _release_release_lock(lock)

    result = build_media_release(config)
    assert result.release_reused is False


def test_pointer_revision_cannot_be_reassigned(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    build_media_release(config)
    conflicting = MediaReleaseConfig(**{**config.__dict__, "min_app_version": "0.2.2"})

    with pytest.raises(ResourceIndexError, match="already assigned"):
        build_media_release(conflicting)


def test_pointer_revision_cannot_move_backwards(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    build_media_release(config)
    build_media_release(MediaReleaseConfig(**{**config.__dict__, "pointer_revision": 8}))
    lower = MediaReleaseConfig(**{**config.__dict__, "pointer_revision": 6})

    with pytest.raises(ResourceIndexError, match="increase monotonically"):
        build_media_release(lower)


def test_identical_cover_bytes_reuse_one_content_addressed_path(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    movie_manifest = json.loads(
        (config.movie_cover_bundle / "cover_manifest.json").read_text(encoding="utf-8")
    )
    movie_asset = next(iter(movie_manifest["assets"].values()))
    payload = (config.movie_cover_bundle / movie_asset["path"]).read_bytes()
    digest = sha256_bytes(payload)

    series_manifest_path = config.series_cover_bundle / "cover_manifest.json"
    series_manifest = json.loads(series_manifest_path.read_text(encoding="utf-8"))
    series_url = next(iter(series_manifest["assets"]))
    webp_path = config.series_cover_bundle / "covers" / f"{digest}.webp"
    webp_path.write_bytes(payload)
    series_manifest["assets"][series_url].update(
        {
            "path": f"covers/{digest}.webp",
            "content_hash": digest,
            "byte_size": len(payload),
            "mime_type": "image/webp",
        }
    )
    _write_json(series_manifest_path, series_manifest)

    result = build_media_release(config)
    assert result.counts["covers"] == 1
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    cover_paths = {ref["path"] for ref in manifest["covers"].values()}
    assert len(cover_paths) == 1


def test_cross_season_resource_is_blocked_before_release_creation(tmp_path: Path) -> None:
    config = _setup(tmp_path, cross_season=True)

    with pytest.raises(ResourceIndexError, match="cross-season"):
        build_media_release(config)

    staging = config.output_dir / "staging"
    assert not list((staging / "releases").glob("*/v1/releases/*/manifest.json"))
    assert not list((staging / "pointers").glob("*.json"))


def test_missing_cover_blocks_release_and_leaves_no_final_pointer(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    movie_manifest = config.movie_cover_bundle / "cover_manifest.json"
    movie_manifest.unlink()

    with pytest.raises(ResourceIndexError, match="failed to read"):
        build_media_release(config)

    assert not list((config.output_dir / "staging" / "pointers").glob("*.json"))


def test_tampered_pointer_fails_release_verification(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    result = build_media_release(config)
    current_path = Path(result.current_path)
    current = json.loads(current_path.read_text(encoding="utf-8"))
    current["pointer_revision"] = 999
    _write_json(current_path, current)

    with pytest.raises(ResourceIndexError, match="signature verification failed"):
        verify_media_release(
            result.release_dir,
            config.public_key_path,
            result.current_path,
        )


def test_missing_manifest_fails_release_verification(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    result = build_media_release(config)
    Path(result.manifest_path).unlink()

    with pytest.raises(ResourceIndexError, match="missing manifest"):
        verify_media_release(
            result.release_dir,
            config.public_key_path,
            result.current_path,
        )


def test_tampered_object_fails_release_verification(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    result = build_media_release(config)
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    target_ref = next(ref for ref in manifest["objects"] if "/objects/detail/" in ref["path"])
    target = Path(result.release_dir) / target_ref["path"].lstrip("/")
    target.write_bytes(target.read_bytes() + b"tamper")

    with pytest.raises(ResourceIndexError, match="verification failed"):
        verify_media_release(
            result.release_dir,
            config.public_key_path,
            result.current_path,
        )


def test_episode_range_title_is_not_counted_as_unknown(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    series = json.loads(config.series_feed_path.read_text(encoding="utf-8"))
    resource = series["items"][0]["resources"][0]
    resource["season_number"] = None
    resource["episode_start"] = None
    resource["episode_end"] = None
    resource["episode_label"] = None
    resource["display_title"] = "01-04.1080p.mkv"
    _write_json(config.series_feed_path, series)

    result = build_media_release(config)
    assert result.quality["unknown_series_resources"] == 0
    assert result.quality["title_inferred_series_resources"] == 1


def test_unknown_series_resource_increase_is_a_regression(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    series = json.loads(config.series_feed_path.read_text(encoding="utf-8"))
    resource = series["items"][0]["resources"][0]
    resource["season_number"] = None
    resource["episode_start"] = None
    resource["episode_end"] = None
    resource["episode_label"] = None
    resource["display_title"] = "1080P"
    _write_json(config.series_feed_path, series)

    previous = tmp_path / "previous-quality-manifest.json"
    _write_signed_json(
        previous,
        {
            "schema_version": "media-manifest/1",
            "counts": {"movie": 1, "series": 1, "resources": 2, "covers": 2},
            "quality": {"unknown_series_resources": 0},
        },
        config.private_key_path,
    )
    blocked = MediaReleaseConfig(**{**config.__dict__, "previous_manifest_path": previous})
    with pytest.raises(ResourceIndexError, match="regression gate failed"):
        build_media_release(blocked)


def test_tampered_previous_manifest_cannot_drive_regression_gate(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    previous = tmp_path / "tampered-previous-manifest.json"
    _write_signed_json(
        previous,
        {
            "schema_version": "media-manifest/1",
            "counts": {"movie": 1, "series": 1, "resources": 2, "covers": 2},
            "quality": {"unknown_series_resources": 0},
        },
        config.private_key_path,
    )
    document = json.loads(previous.read_text(encoding="utf-8"))
    document["counts"]["movie"] = 999
    _write_json(previous, document)

    blocked = MediaReleaseConfig(**{**config.__dict__, "previous_manifest_path": previous})
    with pytest.raises(ResourceIndexError, match="signature verification failed"):
        build_media_release(blocked)


def test_regression_requires_explicit_reason(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    previous = tmp_path / "previous-manifest.json"
    _write_signed_json(
        previous,
        {
            "schema_version": "media-manifest/1",
            "counts": {"movie": 10, "series": 10, "resources": 20, "covers": 20},
        },
        config.private_key_path,
    )
    blocked = MediaReleaseConfig(**{**config.__dict__, "previous_manifest_path": previous})
    with pytest.raises(ResourceIndexError, match="regression gate failed"):
        build_media_release(blocked)

    allowed = MediaReleaseConfig(
        **{
            **config.__dict__,
            "previous_manifest_path": previous,
            "allow_regression_reason": "intentional fixture contraction",
        }
    )
    result = build_media_release(allowed)
    assert result.quality["regression_gate"]["override_reason"] == "intentional fixture contraction"
