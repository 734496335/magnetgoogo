from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline.media_compute_handoff import build_compute_handoff, extract_compute_handoff


def _write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _package(tmp_path: Path):
    movie_feed = tmp_path / "movies.json"
    series_feed = tmp_path / "series.json"
    movie_bundle = tmp_path / "movie-bundle"
    series_bundle = tmp_path / "series-bundle"
    _write(movie_feed, b'{"items":[]}')
    _write(series_feed, b'{"items":[]}')
    _write(movie_bundle / "feed.json", b"movie")
    _write(movie_bundle / "covers" / "a.jpg", b"jpg")
    _write(series_bundle / "feed.json", b"series")
    status = {"status": "success", "mode": "compute", "previous_revision": 40, "content_sha256": "a" * 64, "movie_count": 421, "series_count": 538, "resource_count": 6663}
    return build_compute_handoff(outbox_root=tmp_path / "outbox", run_id="run-1", status=status, movie_feed_path=movie_feed, series_feed_path=series_feed, movie_bundle=movie_bundle, series_bundle=series_bundle)


def test_compute_handoff_round_trip_and_atomic_pointer(tmp_path: Path) -> None:
    report = _package(tmp_path)
    assert report["status"] == "pass"
    pointer = json.loads((tmp_path / "outbox" / "current.json").read_text())
    assert pointer["run_id"] == "run-1"
    extracted = extract_compute_handoff(report["package_path"], tmp_path / "extract")
    assert extracted["status"] == "pass"
    assert (tmp_path / "extract" / "bundles" / "movie" / "covers" / "a.jpg").read_bytes() == b"jpg"


def test_compute_handoff_rejects_tampered_payload(tmp_path: Path) -> None:
    report = _package(tmp_path)
    package = Path(report["package_path"])
    extract_compute_handoff(package, tmp_path / "raw")
    (tmp_path / "raw" / "feeds" / "movies-final.json").write_bytes(b"tampered")
    with tarfile.open(tmp_path / "tampered.tar", "w") as archive:
        for path in sorted((tmp_path / "raw").rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(tmp_path / "raw").as_posix())
    with pytest.raises(ResourceIndexError, match="hash/size mismatch"):
        extract_compute_handoff(tmp_path / "tampered.tar", tmp_path / "bad")


def test_compute_handoff_rejects_duplicate_archive_members(tmp_path: Path) -> None:
    package = tmp_path / "duplicate.tar"
    with tarfile.open(package, "w") as archive:
        for _ in range(2):
            info = tarfile.TarInfo("manifest.json")
            payload = b"{}"
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(ResourceIndexError, match="duplicate members"):
        extract_compute_handoff(package, tmp_path / "extract")


def test_compute_handoff_rejects_symlink_source(tmp_path: Path) -> None:
    movie_feed = tmp_path / "movies.json"
    series_feed = tmp_path / "series.json"
    _write(movie_feed, b"{}")
    _write(series_feed, b"{}")
    movie_bundle = tmp_path / "movie"
    series_bundle = tmp_path / "series"
    _write(movie_bundle / "feed.json", b"movie")
    _write(series_bundle / "feed.json", b"series")
    try:
        (movie_bundle / "bad-link").symlink_to(movie_bundle / "feed.json")
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ResourceIndexError, match="refuses symlinks"):
        build_compute_handoff(outbox_root=tmp_path / "outbox", run_id="run", status={}, movie_feed_path=movie_feed, series_feed_path=series_feed, movie_bundle=movie_bundle, series_bundle=series_bundle)
