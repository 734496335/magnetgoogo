from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "deploy" / "resource-index" / "remote-static-mirror.py"


def _run(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(HELPER), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _write(path: Path, payload: bytes) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest(), len(payload)


def _plan(path: Path, files: list[tuple[str, str, int]], revision: int = 7) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "media-publish-plan/1",
                "release_id": "release-7",
                "pointer_revision": revision,
                "total_file_count": len(files),
                "total_bytes": sum(size for _key, _sha, size in files),
                "files": [
                    {"key": key, "sha256": digest, "size": size, "object_kind": "detail"}
                    for key, digest, size in files
                ],
            }
        ),
        encoding="utf-8",
    )


def test_remote_static_mirror_diff_promote_verify(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = tmp_path / "payload"
    existing_sha, existing_size = _write(target / "v1/objects/detail/a.json", b"existing")
    missing_sha, missing_size = _write(payload / "v1/objects/detail/b.json", b"missing")
    plan = tmp_path / "plan.json"
    _plan(
        plan,
        [
            ("v1/objects/detail/a.json", existing_sha, existing_size),
            ("v1/objects/detail/b.json", missing_sha, missing_size),
        ],
    )

    diff = _run("diff", "--root", str(target), "--plan", str(plan))
    assert diff["missing"] == ["v1/objects/detail/b.json"]
    assert diff["reused_count"] == 1

    delta = tmp_path / "delta.json"
    _plan(delta, [("v1/objects/detail/b.json", missing_sha, missing_size)])
    archive_path = tmp_path / "payload.tar"
    with tarfile.open(archive_path, "w") as archive:
        archive.add(payload / "v1/objects/detail/b.json", arcname="payload/v1/objects/detail/b.json")
    promoted = _run(
        "promote-archive",
        "--root",
        str(target),
        "--plan",
        str(delta),
        "--archive",
        str(archive_path),
    )
    assert promoted["promotion"] == {"copied": 1, "reused": 0}

    verified = _run("verify", "--root", str(target), "--plan", str(plan))
    assert verified["verified_files"] == 2


def test_remote_static_mirror_archive_rejects_unplanned_member(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = tmp_path / "payload"
    expected_sha, expected_size = _write(payload / "v1/objects/detail/a.json", b"expected")
    _write(payload / "v1/objects/detail/extra.json", b"extra")
    plan = tmp_path / "plan.json"
    _plan(plan, [("v1/objects/detail/a.json", expected_sha, expected_size)])
    archive_path = tmp_path / "payload.tar"
    with tarfile.open(archive_path, "w") as archive:
        archive.add(payload / "v1/objects/detail/a.json", arcname="payload/v1/objects/detail/a.json")
        archive.add(payload / "v1/objects/detail/extra.json", arcname="payload/v1/objects/detail/extra.json")

    result = subprocess.run(
        [sys.executable, str(HELPER), "promote-archive", "--root", str(target), "--plan", str(plan), "--archive", str(archive_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    response = json.loads(result.stdout.strip().splitlines()[-1])
    assert "exactly match plan" in response["message"]
    assert not (target / "v1/objects/detail/a.json").exists()


def test_remote_static_mirror_archive_rejects_duplicate_member(tmp_path: Path) -> None:
    target = tmp_path / "target"
    payload = tmp_path / "payload"
    expected_sha, expected_size = _write(payload / "v1/objects/detail/a.json", b"expected")
    plan = tmp_path / "plan.json"
    _plan(plan, [("v1/objects/detail/a.json", expected_sha, expected_size)])
    archive_path = tmp_path / "payload.tar"
    with tarfile.open(archive_path, "w") as archive:
        source = payload / "v1/objects/detail/a.json"
        archive.add(source, arcname="payload/v1/objects/detail/a.json")
        archive.add(source, arcname="payload/v1/objects/detail/a.json")

    result = subprocess.run(
        [sys.executable, str(HELPER), "promote-archive", "--root", str(target), "--plan", str(plan), "--archive", str(archive_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    response = json.loads(result.stdout.strip().splitlines()[-1])
    assert "duplicate members" in response["message"]
    assert not (target / "v1/objects/detail/a.json").exists()


def test_remote_static_mirror_rejects_immutable_conflict(tmp_path: Path) -> None:
    target = tmp_path / "target"
    digest, size = _write(target / "v1/objects/detail/a.json", b"wrong")
    expected_sha = hashlib.sha256(b"expected").hexdigest()
    plan = tmp_path / "plan.json"
    _plan(plan, [("v1/objects/detail/a.json", expected_sha, size)])

    result = subprocess.run(
        [sys.executable, str(HELPER), "diff", "--root", str(target), "--plan", str(plan)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "conflicts" in payload["message"]
    assert digest != expected_sha


def test_remote_static_mirror_current_preflight_and_atomic_promotion(tmp_path: Path) -> None:
    root = tmp_path / "mirror"
    old_manifest = b'{"release_id":"old"}'
    new_manifest = b'{"release_id":"new"}'
    _write(root / "v1/releases/old/manifest.json", old_manifest)
    new_manifest_sha, _ = _write(root / "v1/releases/new/manifest.json", new_manifest)

    current = root / "v1/current.json"
    current.parent.mkdir(parents=True, exist_ok=True)
    old = {
        "pointer_revision": 6,
        "release_id": "old",
        "manifest_path": "/v1/releases/old/manifest.json",
        "manifest_sha256": hashlib.sha256(old_manifest).hexdigest(),
    }
    current.write_text(json.dumps(old, separators=(",", ":")), encoding="utf-8")
    old_sha = hashlib.sha256(current.read_bytes()).hexdigest()

    candidate = tmp_path / "candidate.json"
    new = {
        "pointer_revision": 7,
        "release_id": "new",
        "manifest_path": "/v1/releases/new/manifest.json",
        "manifest_sha256": new_manifest_sha,
    }
    candidate.write_text(json.dumps(new, separators=(",", ":")), encoding="utf-8")

    preflight = _run(
        "preflight-current",
        "--root",
        str(root),
        "--candidate",
        str(candidate),
        "--expected-existing-sha256",
        old_sha,
    )
    assert preflight["state"] == "ready"
    assert json.loads(current.read_text(encoding="utf-8"))["pointer_revision"] == 6

    promoted = _run(
        "promote-current",
        "--root",
        str(root),
        "--candidate",
        str(candidate),
        "--expected-existing-sha256",
        old_sha,
    )
    assert promoted["state"] == "promoted"
    assert json.loads(current.read_text(encoding="utf-8"))["pointer_revision"] == 7

    retried = _run(
        "promote-current",
        "--root",
        str(root),
        "--candidate",
        str(candidate),
        "--expected-existing-sha256",
        old_sha,
    )
    assert retried["state"] == "already-promoted"


def test_remote_static_mirror_current_rejects_release_manifest_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "mirror"
    _write(root / "v1/releases/other/manifest.json", b"other")
    current = root / "v1/current.json"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(
        json.dumps(
            {
                "pointer_revision": 6,
                "release_id": "old",
                "manifest_path": "/v1/releases/other/manifest.json",
                "manifest_sha256": hashlib.sha256(b"other").hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate.json"
    candidate.write_text(current.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(HELPER), "preflight-current", "--root", str(root), "--candidate", str(candidate), "--expected-existing-sha256", "0" * 64],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "does not match release_id" in payload["message"]


def test_remote_static_mirror_current_rejects_non_hex_expected_sha(tmp_path: Path) -> None:
    root = tmp_path / "mirror"
    candidate = tmp_path / "candidate.json"
    candidate.write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(HELPER), "preflight-current", "--root", str(root), "--candidate", str(candidate), "--expected-existing-sha256", "z" * 64],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "SHA-256 is invalid" in payload["message"]


def test_remote_static_mirror_current_rejects_stale_authority_read(tmp_path: Path) -> None:
    root = tmp_path / "mirror"
    old_manifest_sha, _ = _write(root / "v1/releases/old/manifest.json", b"old")
    new_manifest_sha, _ = _write(root / "v1/releases/new/manifest.json", b"new")
    current = root / "v1/current.json"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(
        json.dumps(
            {
                "pointer_revision": 6,
                "release_id": "old",
                "manifest_path": "/v1/releases/old/manifest.json",
                "manifest_sha256": old_manifest_sha,
            }
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "pointer_revision": 7,
                "release_id": "new",
                "manifest_path": "/v1/releases/new/manifest.json",
                "manifest_sha256": new_manifest_sha,
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "preflight-current",
            "--root",
            str(root),
            "--candidate",
            str(candidate),
            "--expected-existing-sha256",
            "0" * 64,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "changed since preflight" in payload["message"]
