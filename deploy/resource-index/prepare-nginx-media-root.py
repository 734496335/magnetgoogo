"""Validate and atomically seed the Nginx media root before configuration cutover."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unable to read media JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"media JSON must be an object: {path}")
    return value


def _public_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.startswith("/v1/") or "\\" in value:
        raise RuntimeError(f"unsafe media public path: {value!r}")
    relative = PurePosixPath(value.lstrip("/"))
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise RuntimeError(f"unsafe media public path: {value!r}")
    return root.joinpath(*relative.parts)


def validate_media_root(root: Path) -> dict[str, Any]:
    current_path = root / "v1" / "current.json"
    current_bytes = current_path.read_bytes()
    current = _load_json(current_path)
    if current.get("schema_version") != "media-current/1":
        raise RuntimeError("media current schema mismatch")
    revision = current.get("pointer_revision")
    release_id = current.get("release_id")
    if type(revision) is not int or revision < 1 or not isinstance(release_id, str) or not release_id:
        raise RuntimeError("media current identity is invalid")

    manifest_path = _public_path(root, current.get("manifest_path"))
    manifest_bytes = manifest_path.read_bytes()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_hash != current.get("manifest_sha256"):
        raise RuntimeError("media manifest hash mismatch")
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != "media-manifest/1" or manifest.get("release_id") != release_id:
        raise RuntimeError("media manifest identity mismatch")
    objects = manifest.get("objects")
    if not isinstance(objects, list) or not objects:
        raise RuntimeError("media manifest objects are missing")

    verified_bytes = len(current_bytes) + len(manifest_bytes)
    verified_objects = 0
    for index, raw in enumerate(objects):
        if not isinstance(raw, dict):
            raise RuntimeError(f"media object reference is invalid: {index}")
        path = _public_path(root, raw.get("path"))
        payload = path.read_bytes()
        if len(payload) != raw.get("size"):
            raise RuntimeError(f"media object size mismatch: {path}")
        if hashlib.sha256(payload).hexdigest() != raw.get("hash"):
            raise RuntimeError(f"media object hash mismatch: {path}")
        verified_objects += 1
        verified_bytes += len(payload)

    return {
        "status": "pass",
        "root": str(root),
        "pointer_revision": revision,
        "release_id": release_id,
        "manifest_sha256": manifest_hash,
        "verified_objects": verified_objects,
        "verified_bytes": verified_bytes,
    }


def _directory_is_empty(path: Path) -> bool:
    return path.is_dir() and next(path.iterdir(), None) is None


def prepare_media_root(source: Path, target: Path) -> dict[str, Any]:
    if target.exists():
        try:
            report = validate_media_root(target)
        except (OSError, RuntimeError):
            if not _directory_is_empty(target):
                raise RuntimeError(f"target media root exists but is invalid and non-empty: {target}")
        else:
            return {**report, "action": "already_ready"}

    source_report = validate_media_root(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.bootstrap-{uuid.uuid4().hex}"
    try:
        shutil.copytree(source, staging, copy_function=shutil.copy2)
        staged_report = validate_media_root(staging)
        if target.exists():
            target.rmdir()
        os.replace(staging, target)
        try:
            descriptor = os.open(target.parent, os.O_RDONLY)
        except OSError:
            descriptor = None
        if descriptor is not None:
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    final_report = validate_media_root(target)
    if final_report["manifest_sha256"] != source_report["manifest_sha256"]:
        raise RuntimeError("atomic media bootstrap changed the manifest")
    return {
        **final_report,
        "action": "bootstrapped",
        "source_verified_objects": staged_report["verified_objects"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    report = prepare_media_root(Path(args.source).resolve(), Path(args.target).resolve())
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
