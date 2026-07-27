"""Verify signed media control pointers and monotonic promotion rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from magnet.resource_index.release.protocol import verify_document  # noqa: E402


def fail(message: str, **context: Any) -> None:
    print(json.dumps({"status": "failed", "message": message, "context": context}, ensure_ascii=False, sort_keys=True))
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pointer(path: Path, public_key: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("failed to read media pointer", path=str(path), error=type(exc).__name__)
    if not isinstance(value, dict) or value.get("schema_version") != "media-current/1":
        fail("media pointer schema is invalid", path=str(path))
    verify_document(value, public_key)
    revision = value.get("pointer_revision")
    manifest_path = value.get("manifest_path")
    manifest_sha256 = value.get("manifest_sha256")
    if type(revision) is not int or revision < 1:
        fail("media pointer revision is invalid", path=str(path))
    if not isinstance(manifest_path, str) or not manifest_path.startswith("/v1/releases/") or not manifest_path.endswith("/manifest.json"):
        fail("media pointer manifest path is invalid", path=str(path))
    if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64:
        fail("media pointer manifest hash is invalid", path=str(path))
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pointer", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--existing")
    parser.add_argument("--manifest")
    args = parser.parse_args()

    pointer_path = Path(args.pointer).resolve()
    public_key_path = Path(args.public_key).resolve()
    pointer = load_pointer(pointer_path, public_key_path)
    pointer_hash = sha256_file(pointer_path)

    if args.manifest:
        manifest_path = Path(args.manifest).resolve()
        actual_manifest_hash = sha256_file(manifest_path)
        if actual_manifest_hash != pointer["manifest_sha256"]:
            fail(
                "manifest hash does not match the signed pointer",
                expected=pointer["manifest_sha256"],
                actual=actual_manifest_hash,
            )

    existing_state = "absent"
    if args.existing:
        existing_path = Path(args.existing).resolve()
        if existing_path.is_file() and existing_path.stat().st_size > 0:
            existing = load_pointer(existing_path, public_key_path)
            existing_hash = sha256_file(existing_path)
            if existing["pointer_revision"] > pointer["pointer_revision"]:
                fail(
                    "existing media pointer revision is newer",
                    existing_revision=existing["pointer_revision"],
                    candidate_revision=pointer["pointer_revision"],
                )
            if existing["pointer_revision"] == pointer["pointer_revision"] and existing_hash != pointer_hash:
                fail(
                    "same media pointer revision contains different signed content",
                    revision=pointer["pointer_revision"],
                    existing_sha256=existing_hash,
                    candidate_sha256=pointer_hash,
                )
            existing_state = "same" if existing_hash == pointer_hash else "older"

    print(json.dumps({
        "status": "pass",
        "release_id": pointer["release_id"],
        "pointer_revision": pointer["pointer_revision"],
        "pointer_sha256": pointer_hash,
        "manifest_path": pointer["manifest_path"],
        "manifest_sha256": pointer["manifest_sha256"],
        "existing_state": existing_state,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
