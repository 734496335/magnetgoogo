"""Verify and atomically install a pre-audited media candidate seed."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from pathlib import Path, PurePosixPath
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unable to read seed JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"seed JSON must be an object: {path}")
    return value


def _safe_relative(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RuntimeError(f"unsafe seed path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"unsafe seed path: {value!r}")
    return path


def verify_seed(seed_root: Path) -> dict[str, Any]:
    manifest_path = seed_root / "seed-manifest.json"
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != "media-candidate-seed/1":
        raise RuntimeError("candidate seed schema mismatch")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise RuntimeError("candidate seed file manifest is missing")

    expected: set[str] = set()
    total_bytes = 0
    for index, raw in enumerate(raw_files):
        if not isinstance(raw, dict):
            raise RuntimeError(f"candidate seed file entry is invalid: {index}")
        relative = _safe_relative(raw.get("path"))
        relative_text = relative.as_posix()
        if relative_text in expected:
            raise RuntimeError(f"duplicate candidate seed path: {relative_text}")
        expected.add(relative_text)
        path = seed_root.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"candidate seed file is missing or unsafe: {path}")
        payload = path.read_bytes()
        if len(payload) != raw.get("size"):
            raise RuntimeError(f"candidate seed size mismatch: {path}")
        if hashlib.sha256(payload).hexdigest() != raw.get("sha256"):
            raise RuntimeError(f"candidate seed hash mismatch: {path}")
        total_bytes += len(payload)

    actual = {
        path.relative_to(seed_root).as_posix()
        for path in seed_root.rglob("*")
        if path.is_file() and path.name != "seed-manifest.json"
    }
    if actual != expected:
        raise RuntimeError(
            f"candidate seed file set mismatch: missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    if len(expected) != manifest.get("file_count") or total_bytes != manifest.get("total_bytes"):
        raise RuntimeError("candidate seed aggregate counts do not match")

    databases = manifest.get("databases")
    if not isinstance(databases, dict) or not databases:
        raise RuntimeError("candidate seed database evidence is missing")
    database_report: dict[str, Any] = {}
    for relative_text, expected_db in databases.items():
        relative = _safe_relative(relative_text)
        path = seed_root.joinpath(*relative.parts)
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro&immutable=1",
            uri=True,
        )
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            movie_items = connection.execute("SELECT COUNT(*) FROM movie_items").fetchone()[0]
        finally:
            connection.close()
        if integrity != "ok":
            raise RuntimeError(f"candidate seed SQLite integrity failed: {path}")
        if isinstance(expected_db, dict) and movie_items != expected_db.get("movie_items"):
            raise RuntimeError(f"candidate seed SQLite row count mismatch: {path}")
        database_report[relative_text] = {"integrity": integrity, "movie_items": movie_items}

    return {
        "status": "pass",
        "seed_root": str(seed_root),
        "file_count": len(expected),
        "total_bytes": total_bytes,
        "candidate": manifest.get("candidate") or {},
        "databases": database_report,
    }


def _replace_directory(source: Path, target: Path) -> None:
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{target.name}.seed-{uuid.uuid4().hex}"
    backup = parent / f".{target.name}.backup-{uuid.uuid4().hex}"
    replaced = False
    try:
        shutil.copytree(source, staging, copy_function=shutil.copy2)
        if target.exists():
            os.replace(target, backup)
            replaced = True
        os.replace(staging, target)
        if backup.exists():
            shutil.rmtree(backup)
    except BaseException:
        if target.exists() and replaced:
            shutil.rmtree(target)
        if replaced and backup.exists():
            os.replace(backup, target)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists():
            shutil.rmtree(backup)


def _replace_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.seed-{uuid.uuid4().hex}"
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def install_seed(seed_root: Path, state_root: Path) -> dict[str, Any]:
    if (state_root / "locks" / "media-daily.lock").exists():
        raise RuntimeError("media daily lock exists; refuse candidate seed installation")
    verification = verify_seed(seed_root)
    for name in ("sources", "bundles"):
        source = seed_root / name
        if not source.is_dir():
            raise RuntimeError(f"candidate seed component is missing: {source}")
        _replace_directory(source, state_root / name)
    _replace_file(
        seed_root / "ratings" / "media-ratings.json",
        state_root / "ratings" / "media-ratings.json",
    )
    receipt_root = state_root / "seed"
    _replace_file(seed_root / "seed-manifest.json", receipt_root / "seed-manifest.json")
    if (seed_root / "candidate-audit.json").is_file():
        _replace_file(seed_root / "candidate-audit.json", receipt_root / "candidate-audit.json")
    installed = verify_seed(seed_root)
    return {
        **installed,
        "action": "installed",
        "state_root": str(state_root),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-root", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    seed_root = Path(args.seed_root).resolve()
    state_root = Path(args.state_root).resolve()
    result = verify_seed(seed_root) if args.verify_only else install_seed(seed_root, state_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
