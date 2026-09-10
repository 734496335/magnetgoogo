from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import uuid
from pathlib import Path
from typing import Any

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.release.protocol import canonical_json_bytes


SCHEMA = "media-compute-handoff/1"
POINTER_SCHEMA = "media-compute-handoff-pointer/1"


def _fail(message: str, **context: Any) -> None:
    raise ResourceIndexError(CONFIG_ERROR, message, context)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_key(value: str) -> str:
    normalized = value.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ".." in Path(normalized).parts:
        _fail("compute handoff path is unsafe", path=value)
    return normalized


def _files_under(root: Path, prefix: str) -> list[tuple[str, Path]]:
    output: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            _fail("compute handoff refuses symlinks", path=str(path))
        if not path.is_file():
            continue
        output.append((_safe_key(f"{prefix}/{path.relative_to(root).as_posix()}"), path))
    return output


def build_compute_handoff(
    *,
    outbox_root: str | Path,
    run_id: str,
    status: dict[str, Any],
    movie_feed_path: str | Path,
    series_feed_path: str | Path,
    movie_bundle: str | Path,
    series_bundle: str | Path,
) -> dict[str, Any]:
    root = Path(outbox_root).resolve()
    package_dir = root / "packages"
    staging = root / ".staging" / f"{run_id}-{uuid.uuid4().hex}"
    package_dir.mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        status_path = staging / "status.json"
        status_path.write_bytes(canonical_json_bytes(status))
        sources: list[tuple[str, Path]] = [
            ("status.json", status_path),
            ("feeds/movies-final.json", Path(movie_feed_path).resolve()),
            ("feeds/series-final.json", Path(series_feed_path).resolve()),
        ]
        sources.extend(_files_under(Path(movie_bundle).resolve(), "bundles/movie"))
        sources.extend(_files_under(Path(series_bundle).resolve(), "bundles/series"))
        seen: set[str] = set()
        files: list[dict[str, Any]] = []
        for key, path in sources:
            key = _safe_key(key)
            if key in seen:
                _fail("compute handoff contains duplicate path", path=key)
            seen.add(key)
            if not path.is_file() or path.is_symlink():
                _fail("compute handoff source is not a regular file", path=str(path))
            files.append({"path": key, "sha256": _sha256(path), "size": path.stat().st_size})
        manifest = {
            "schema_version": SCHEMA,
            "run_id": run_id,
            "previous_revision": status.get("previous_revision"),
            "content_sha256": status.get("content_sha256"),
            "movie_count": status.get("movie_count"),
            "series_count": status.get("series_count"),
            "resource_count": status.get("resource_count"),
            "files": files,
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        package_path = package_dir / f"{run_id}.tar"
        temporary = package_dir / f".{run_id}.{uuid.uuid4().hex}.tmp"
        with tarfile.open(temporary, "w") as archive:
            for key, path in [("manifest.json", manifest_path), *sources]:
                info = archive.gettarinfo(str(path), arcname=key)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                info.mode = 0o644
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
        os.replace(temporary, package_path)
        package_sha = _sha256(package_path)
        pointer = {
            "schema_version": POINTER_SCHEMA,
            "run_id": run_id,
            "package": f"packages/{package_path.name}",
            "package_sha256": package_sha,
            "package_size": package_path.stat().st_size,
            "previous_revision": status.get("previous_revision"),
            "movie_count": status.get("movie_count"),
            "series_count": status.get("series_count"),
            "resource_count": status.get("resource_count"),
        }
        root.mkdir(parents=True, exist_ok=True)
        pointer_tmp = root / f".current.{uuid.uuid4().hex}.tmp"
        pointer_tmp.write_bytes(canonical_json_bytes(pointer))
        os.replace(pointer_tmp, root / "current.json")
        return {
            "schema_version": POINTER_SCHEMA,
            "status": "pass",
            "run_id": run_id,
            "package_path": str(package_path),
            "package_sha256": package_sha,
            "package_size": package_path.stat().st_size,
            "file_count": len(files),
            "pointer_path": str(root / "current.json"),
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def extract_compute_handoff(package_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    package = Path(package_path).resolve()
    target = Path(output_dir).resolve()
    if target.exists():
        if any(target.iterdir()):
            _fail("compute handoff extraction target must be empty", path=str(target))
    else:
        target.mkdir(parents=True)
    with tarfile.open(package, "r") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            _fail("compute handoff archive contains duplicate members")
        for member in members:
            key = _safe_key(member.name)
            if not member.isfile():
                _fail("compute handoff archive contains non-file member", path=member.name)
            source = archive.extractfile(member)
            if source is None:
                _fail("compute handoff archive member cannot be read", path=member.name)
            destination = target / key
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    manifest_path = target / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("compute handoff manifest is invalid", error=type(exc).__name__)
    if manifest.get("schema_version") != SCHEMA or not isinstance(manifest.get("files"), list):
        _fail("compute handoff manifest contract mismatch")
    expected = {"manifest.json"}
    for item in manifest["files"]:
        if not isinstance(item, dict):
            _fail("compute handoff file descriptor is invalid")
        key = _safe_key(str(item.get("path") or ""))
        if key in expected:
            _fail("compute handoff manifest contains duplicate file", path=key)
        expected.add(key)
        path = target / key
        if not path.is_file() or path.is_symlink():
            _fail("compute handoff file is missing", path=key)
        if path.stat().st_size != item.get("size") or _sha256(path) != item.get("sha256"):
            _fail("compute handoff file hash/size mismatch", path=key)
    actual = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    if actual != expected:
        _fail("compute handoff archive contains unplanned files", extra=sorted(actual - expected), missing=sorted(expected - actual))
    return {"status": "pass", "manifest": manifest, "root": str(target)}
