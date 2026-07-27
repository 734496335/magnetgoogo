from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from magnet.resource_index.release.protocol import sign_document


SCRIPT = Path("deploy/resource-index/verify-media-control.py")


def _keypair(tmp_path: Path) -> tuple[Path, Path]:
    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


def _pointer(tmp_path: Path, private: Path, revision: int, release: str = "release-a") -> Path:
    value = sign_document(
        {
            "schema_version": "media-current/1",
            "pointer_revision": revision,
            "release_id": release,
            "manifest_path": f"/v1/releases/{release}/manifest.json",
            "manifest_sha256": "a" * 64,
            "published_at": "2026-07-27T00:00:00Z",
            "min_app_version": "0.2.1",
        },
        private,
    )
    path = tmp_path / f"current-{revision}-{release}.json"
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def test_media_control_verifier_accepts_newer_signed_pointer(tmp_path: Path) -> None:
    private, public = _keypair(tmp_path)
    old = _pointer(tmp_path, private, 1)
    candidate = _pointer(tmp_path, private, 2, "release-b")

    result = _run("--pointer", str(candidate), "--public-key", str(public), "--existing", str(old))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["pointer_revision"] == 2
    assert payload["existing_state"] == "older"


def test_media_control_verifier_blocks_same_revision_different_content(tmp_path: Path) -> None:
    private, public = _keypair(tmp_path)
    old = _pointer(tmp_path, private, 2, "release-a")
    candidate = _pointer(tmp_path, private, 2, "release-b")

    result = _run("--pointer", str(candidate), "--public-key", str(public), "--existing", str(old))

    assert result.returncode == 1
    assert "same media pointer revision" in result.stdout


def test_media_control_verifier_blocks_newer_existing_pointer(tmp_path: Path) -> None:
    private, public = _keypair(tmp_path)
    existing = _pointer(tmp_path, private, 3)
    candidate = _pointer(tmp_path, private, 2)

    result = _run("--pointer", str(candidate), "--public-key", str(public), "--existing", str(existing))

    assert result.returncode == 1
    assert "existing media pointer revision is newer" in result.stdout


def test_media_control_verifier_rejects_tampered_signature(tmp_path: Path) -> None:
    private, public = _keypair(tmp_path)
    candidate = _pointer(tmp_path, private, 2)
    value = json.loads(candidate.read_text(encoding="utf-8"))
    value["pointer_revision"] = 4
    candidate.write_text(json.dumps(value), encoding="utf-8")

    result = _run("--pointer", str(candidate), "--public-key", str(public))

    assert result.returncode != 0
