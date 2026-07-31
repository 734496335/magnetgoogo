from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[3] / "deploy" / "resource-index" / "prepare-nginx-media-root.py"
SPEC = importlib.util.spec_from_file_location("prepare_nginx_media_root", MODULE_PATH)
assert SPEC and SPEC.loader
prepare_nginx_media_root = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_nginx_media_root)

prepare_media_root = prepare_nginx_media_root.prepare_media_root
validate_media_root = prepare_nginx_media_root.validate_media_root


def _write_json(path: Path, value: object) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def _media_root(root: Path, *, revision: int = 7) -> dict[str, str]:
    object_payload = _write_json(root / "v1" / "objects" / "detail" / "item.json", {"title": "test"})
    object_hash = hashlib.sha256(object_payload).hexdigest()
    release_id = "20260730T000000Z-test"
    manifest_path = root / "v1" / "releases" / release_id / "manifest.json"
    manifest_payload = _write_json(
        manifest_path,
        {
            "schema_version": "media-manifest/1",
            "release_id": release_id,
            "objects": [
                {
                    "path": "/v1/objects/detail/item.json",
                    "hash": object_hash,
                    "size": len(object_payload),
                }
            ],
        },
    )
    manifest_hash = hashlib.sha256(manifest_payload).hexdigest()
    _write_json(
        root / "v1" / "current.json",
        {
            "schema_version": "media-current/1",
            "pointer_revision": revision,
            "release_id": release_id,
            "manifest_path": f"/v1/releases/{release_id}/manifest.json",
            "manifest_sha256": manifest_hash,
        },
    )
    return {"release_id": release_id, "manifest_sha256": manifest_hash}


def test_prepare_media_root_bootstraps_complete_tree_atomically(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "state" / "public"
    identity = _media_root(source)
    target.mkdir(parents=True)

    report = prepare_media_root(source, target)

    assert report["action"] == "bootstrapped"
    assert report["pointer_revision"] == 7
    assert report["manifest_sha256"] == identity["manifest_sha256"]
    assert report["verified_objects"] == 1
    assert validate_media_root(target)["release_id"] == identity["release_id"]
    assert not list(target.parent.glob(".public.bootstrap-*"))


def test_prepare_media_root_is_idempotent_when_target_is_valid(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _media_root(source)
    prepare_media_root(source, target)

    report = prepare_media_root(tmp_path / "missing-source", target)

    assert report["action"] == "already_ready"
    assert report["verified_objects"] == 1


def test_prepare_media_root_rejects_corrupt_source_without_creating_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _media_root(source)
    (source / "v1" / "objects" / "detail" / "item.json").write_text("corrupt", encoding="utf-8")

    with pytest.raises(RuntimeError, match="(size|hash) mismatch"):
        prepare_media_root(source, target)

    assert not target.exists()


def test_prepare_media_root_refuses_nonempty_invalid_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _media_root(source)
    target.mkdir(parents=True)
    (target / "unknown.txt").write_text("do not delete", encoding="utf-8")

    with pytest.raises(RuntimeError, match="invalid and non-empty"):
        prepare_media_root(source, target)

    assert (target / "unknown.txt").read_text(encoding="utf-8") == "do not delete"


def test_validate_media_root_rejects_unsafe_manifest_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _media_root(root)
    current_path = root / "v1" / "current.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    current["manifest_path"] = "/v1/../secret.json"
    _write_json(current_path, current)

    with pytest.raises(RuntimeError, match="unsafe media public path"):
        validate_media_root(root)
