from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[3] / "deploy" / "resource-index" / "install-media-candidate-seed.py"
SPEC = importlib.util.spec_from_file_location("install_media_candidate_seed", MODULE_PATH)
assert SPEC and SPEC.loader
install_media_candidate_seed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install_media_candidate_seed)

install_seed = install_media_candidate_seed.install_seed
verify_seed = install_media_candidate_seed.verify_seed


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _seed(root: Path) -> None:
    db = root / "sources" / "sixv_latest_100.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db)
    try:
        connection.execute("CREATE TABLE movie_items(movie_id TEXT PRIMARY KEY)")
        connection.executemany("INSERT INTO movie_items(movie_id) VALUES (?)", [("a",), ("b",)])
        connection.commit()
    finally:
        connection.close()
    _write(root / "bundles" / "movie" / "cover_manifest.json", b"{}")
    _write(root / "bundles" / "series" / "cover_manifest.json", b"{}")
    _write(root / "ratings" / "media-ratings.json", b'{"schema_version":"media-rating-state/1"}')
    _write(root / "candidate-audit.json", b'{"status":"success"}')

    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        payload = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "media-candidate-seed/1",
        "candidate": {"movie_count": 2},
        "databases": {
            "sources/sixv_latest_100.db": {"integrity": "ok", "movie_items": 2}
        },
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "files": files,
    }
    (root / "seed-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def test_verify_and_install_candidate_seed(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    state = tmp_path / "state"
    _seed(seed)
    (state / "sources").mkdir(parents=True)
    (state / "sources" / "old.db").write_bytes(b"old")

    verified = verify_seed(seed)
    assert not list(seed.rglob("*.db-wal"))
    assert not list(seed.rglob("*.db-shm"))
    installed = install_seed(seed, state)

    assert verified["status"] == "pass"
    assert installed["action"] == "installed"
    assert not (state / "sources" / "old.db").exists()
    assert (state / "sources" / "sixv_latest_100.db").is_file()
    assert (state / "bundles" / "movie" / "cover_manifest.json").is_file()
    assert (state / "ratings" / "media-ratings.json").is_file()
    assert (state / "seed" / "seed-manifest.json").is_file()


def test_candidate_seed_hash_corruption_is_rejected_before_install(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    state = tmp_path / "state"
    _seed(seed)
    (seed / "ratings" / "media-ratings.json").write_bytes(b"corrupt")

    with pytest.raises(RuntimeError, match="(size|hash) mismatch"):
        install_seed(seed, state)

    assert not (state / "sources").exists()


def test_candidate_seed_refuses_install_while_daily_lock_exists(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    state = tmp_path / "state"
    _seed(seed)
    lock = state / "locks" / "media-daily.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("pid=1", encoding="ascii")

    with pytest.raises(RuntimeError, match="lock exists"):
        install_seed(seed, state)

    assert not (state / "sources").exists()


def test_candidate_seed_rejects_extra_unmanifested_file(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    _seed(seed)
    _write(seed / "sources" / "unexpected.bin", b"unexpected")

    with pytest.raises(RuntimeError, match="file set mismatch"):
        verify_seed(seed)
