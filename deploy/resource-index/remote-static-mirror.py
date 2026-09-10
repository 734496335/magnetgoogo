from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


_PRODUCTION_ROOT = Path("/var/lib/magnet-media/public").resolve()


def fail(message: str, **context: Any) -> None:
    print(json.dumps({"status": "failed", "message": message, "context": context}, ensure_ascii=False, sort_keys=True))
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_key(value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        fail("plan contains an unsafe key", key=value)
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        fail("plan contains an unsafe path component", key=value)
    key = "/".join(parts)
    allowed = (
        key.startswith("v1/objects/")
        or key.startswith("v1/covers/")
        or key.startswith("v1/releases/")
    )
    if not allowed or key == "v1/current.json":
        fail("plan key is outside the immutable mirror allowlist", key=key)
    return key


def load_plan(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("failed to read mirror plan", path=str(path), error=type(exc).__name__)
    if not isinstance(value, dict) or value.get("schema_version") != "media-publish-plan/1":
        fail("mirror plan schema is invalid", path=str(path))
    files = value.get("files")
    if not isinstance(files, list) or not files:
        fail("mirror plan has no files", path=str(path))
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            fail("mirror plan file entry is invalid", index=index)
        key = safe_key(item.get("key"))
        digest = item.get("sha256")
        size = item.get("size")
        if key in seen:
            fail("mirror plan contains a duplicate key", key=key)
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            fail("mirror plan contains an invalid SHA-256", key=key)
        if type(size) is not int or size < 0:
            fail("mirror plan contains an invalid size", key=key)
        seen.add(key)
        normalized.append({"key": key, "sha256": digest, "size": size})
    if value.get("total_file_count") != len(normalized):
        fail("mirror plan total_file_count mismatch", expected=value.get("total_file_count"), actual=len(normalized))
    return value, normalized


def resolve_key(root: Path, key: str) -> Path:
    candidate = (root / key).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        fail("mirror key escapes root", key=key)
    return candidate


def diff_root(root: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    missing: list[str] = []
    reused = 0
    verified_bytes = 0
    for item in files:
        path = resolve_key(root, item["key"])
        if not path.exists():
            missing.append(item["key"])
            continue
        if not path.is_file():
            fail("mirror target path is not a file", key=item["key"], path=str(path))
        size = path.stat().st_size
        digest = sha256_file(path)
        if size != item["size"] or digest != item["sha256"]:
            fail(
                "immutable mirror target conflicts with plan",
                key=item["key"],
                expected_size=item["size"],
                actual_size=size,
                expected_sha256=item["sha256"],
                actual_sha256=digest,
            )
        reused += 1
        verified_bytes += size
    return {"missing": missing, "missing_count": len(missing), "reused_count": reused, "verified_bytes": verified_bytes}


def verify_root(root: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    report = diff_root(root, files)
    if report["missing"]:
        fail("mirror target is incomplete", missing=report["missing"][:20], missing_count=report["missing_count"])
    return {"verified_files": len(files), "verified_bytes": report["verified_bytes"]}


def promote_payload(payload_root: Path, target_root: Path, files: list[dict[str, Any]]) -> dict[str, int]:
    copied = 0
    reused = 0
    target_root.mkdir(parents=True, exist_ok=True)
    for item in files:
        source = resolve_key(payload_root, item["key"])
        if not source.is_file() or source.stat().st_size != item["size"] or sha256_file(source) != item["sha256"]:
            fail("payload file failed verification", key=item["key"])
        target = resolve_key(target_root, item["key"])
        target.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(target.parent, 0o755)
        if target.exists():
            if not target.is_file() or target.stat().st_size != item["size"] or sha256_file(target) != item["sha256"]:
                fail("immutable mirror target conflicts with payload", key=item["key"], path=str(target))
            os.chmod(target, 0o644)
            reused += 1
            continue
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(source, temporary)
            if temporary.stat().st_size != item["size"] or sha256_file(temporary) != item["sha256"]:
                fail("temporary mirror copy failed verification", key=item["key"])
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        copied += 1
    return {"copied": copied, "reused": reused}


def promote_archive(archive_path: Path, target_root: Path, files: list[dict[str, Any]]) -> dict[str, int]:
    expected = {f"payload/{item['key']}": item for item in files}
    copied = 0
    reused = 0
    target_root.mkdir(parents=True, exist_ok=True)
    try:
        archive = tarfile.open(archive_path, "r")
    except (OSError, tarfile.TarError) as exc:
        fail("failed to open mirror payload archive", error=type(exc).__name__)
    with archive:
        members = archive.getmembers()
        member_names = [member.name for member in members]
        actual_names: set[str] = set()
        duplicate_names: set[str] = set()
        for name in member_names:
            if name in actual_names:
                duplicate_names.add(name)
            actual_names.add(name)
        duplicate_names = sorted(duplicate_names)
        if duplicate_names:
            fail("mirror payload archive contains duplicate members", duplicates=duplicate_names[:20])
        if actual_names != set(expected):
            fail(
                "mirror payload archive members do not exactly match plan",
                missing=sorted(set(expected) - actual_names)[:20],
                unexpected=sorted(actual_names - set(expected))[:20],
            )
        for member in members:
            if not member.isfile():
                fail("mirror payload archive contains a non-regular file", member=member.name)
            item = expected[member.name]
            if member.size != item["size"]:
                fail("mirror payload archive size mismatch", key=item["key"])
            target = resolve_key(target_root, item["key"])
            target.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(target.parent, 0o755)
            if target.exists():
                if not target.is_file() or target.stat().st_size != item["size"] or sha256_file(target) != item["sha256"]:
                    fail("immutable mirror target conflicts with payload", key=item["key"], path=str(target))
                os.chmod(target, 0o644)
                reused += 1
                continue
            source = archive.extractfile(member)
            if source is None:
                fail("failed to read mirror payload archive member", member=member.name)
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            os.close(descriptor)
            temporary = Path(temporary_name)
            digest = hashlib.sha256()
            size = 0
            try:
                with temporary.open("wb") as handle:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                if size != item["size"] or digest.hexdigest() != item["sha256"]:
                    fail("mirror payload archive member failed verification", key=item["key"])
                os.chmod(temporary, 0o644)
                os.replace(temporary, target)
            finally:
                source.close()
                temporary.unlink(missing_ok=True)
            copied += 1
    return {"copied": copied, "reused": reused}


def load_candidate(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("current pointer candidate is invalid", path=str(path), error=type(exc).__name__)
    if not isinstance(value, dict):
        fail("current pointer candidate must be an object", path=str(path))
    revision = value.get("pointer_revision")
    release_id = value.get("release_id")
    manifest_path = value.get("manifest_path")
    manifest_sha256 = value.get("manifest_sha256")
    if type(revision) is not int or revision < 1:
        fail("current pointer revision is invalid", pointer_revision=revision)
    if not isinstance(release_id, str) or not release_id or "/" in release_id or "\\" in release_id:
        fail("current pointer release_id is invalid", release_id=release_id)
    expected_manifest_path = f"/v1/releases/{release_id}/manifest.json"
    if manifest_path != expected_manifest_path:
        fail("current pointer manifest_path does not match release_id", manifest_path=manifest_path, release_id=release_id)
    safe_key(expected_manifest_path.lstrip("/"))
    if (
        not isinstance(manifest_sha256, str)
        or len(manifest_sha256) != 64
        or any(char not in "0123456789abcdef" for char in manifest_sha256)
    ):
        fail("current pointer manifest hash is invalid")
    return raw, value


def preflight_current(root: Path, candidate_path: Path, expected_existing_sha256: str) -> dict[str, Any]:
    if len(expected_existing_sha256) != 64 or any(char not in "0123456789abcdef" for char in expected_existing_sha256):
        fail("expected existing current SHA-256 is invalid")
    candidate_bytes, candidate = load_candidate(candidate_path)
    target = root / "v1" / "current.json"
    if not target.is_file():
        fail("existing current pointer is missing", path=str(target))
    existing_bytes, existing = load_candidate(target)
    actual_existing_sha = hashlib.sha256(existing_bytes).hexdigest()
    existing_revision = existing["pointer_revision"]
    candidate_revision = candidate["pointer_revision"]
    if candidate_bytes == existing_bytes:
        state = "already-promoted"
    else:
        if actual_existing_sha != expected_existing_sha256:
            fail(
                "existing current pointer changed since preflight authority read",
                expected_sha256=expected_existing_sha256,
                actual_sha256=actual_existing_sha,
            )
        if candidate_revision == existing_revision:
            fail("current pointer revision cannot be rebound", pointer_revision=candidate_revision)
        if candidate_revision == existing_revision + 1:
            state = "ready"
        else:
            fail(
                "current pointer revision must advance exactly one step",
                existing_revision=existing_revision,
                candidate_revision=candidate_revision,
            )
    if candidate_revision not in {existing_revision, existing_revision + 1}:
        fail(
            "current pointer revision must advance exactly one step",
            existing_revision=existing_revision,
            candidate_revision=candidate_revision,
        )
    manifest = resolve_key(root, candidate["manifest_path"].lstrip("/"))
    if not manifest.is_file():
        fail("candidate manifest is missing from mirror", path=str(manifest))
    actual_manifest_sha = sha256_file(manifest)
    if actual_manifest_sha != candidate["manifest_sha256"]:
        fail(
            "candidate manifest hash mismatch on mirror",
            expected_sha256=candidate["manifest_sha256"],
            actual_sha256=actual_manifest_sha,
        )
    return {
        "status": "pass",
        "state": state,
        "existing_revision": existing_revision,
        "candidate_revision": candidate_revision,
        "existing_sha256": actual_existing_sha,
        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "manifest_sha256": actual_manifest_sha,
    }


def promote_current(root: Path, candidate_path: Path, expected_existing_sha256: str) -> dict[str, Any]:
    report = preflight_current(root, candidate_path, expected_existing_sha256)
    if report["state"] == "already-promoted":
        return report
    target = root / "v1" / "current.json"
    candidate_bytes = candidate_path.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".current.", suffix=".tmp", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(candidate_bytes)
        os.chmod(temporary, 0o644)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != report["candidate_sha256"]:
            fail("temporary current pointer failed verification")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    if sha256_file(target) != report["candidate_sha256"]:
        fail("promoted current pointer failed verification")
    return {**report, "state": "promoted"}


def healthcheck_root(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        fail("mirror root is missing", root=str(root))
    probe = root / f".media-health-{os.getpid()}"
    descriptor: int | None = None
    try:
        descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(descriptor, b"ok")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        if probe.read_bytes() != b"ok":
            fail("mirror root healthcheck verification failed", root=str(root))
    except OSError as exc:
        fail("mirror root healthcheck failed", root=str(root), error=type(exc).__name__)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        probe.unlink(missing_ok=True)
    return {"status": "pass", "root": str(root), "writable": True}


def enforce_privileged_root(root: Path, *, effective_uid: int | None = None) -> None:
    uid = effective_uid
    if uid is None:
        get_euid = getattr(os, "geteuid", None)
        uid = int(get_euid()) if get_euid is not None else -1
    if uid == 0 and root.resolve() != _PRODUCTION_ROOT:
        fail("privileged remote helper refuses a non-production mirror root", root=str(root))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    item = sub.add_parser("healthcheck")
    item.add_argument("--root", required=True)
    for command in ("diff", "verify"):
        item = sub.add_parser(command)
        item.add_argument("--root", required=True)
        item.add_argument("--plan", required=True)
    item = sub.add_parser("promote")
    item.add_argument("--root", required=True)
    item.add_argument("--plan", required=True)
    item.add_argument("--payload", required=True)
    item = sub.add_parser("promote-archive")
    item.add_argument("--root", required=True)
    item.add_argument("--plan", required=True)
    item.add_argument("--archive", required=True)
    for command in ("preflight-current", "promote-current"):
        item = sub.add_parser(command)
        item.add_argument("--root", required=True)
        item.add_argument("--candidate", required=True)
        item.add_argument("--expected-existing-sha256", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    enforce_privileged_root(root)
    if args.command == "healthcheck":
        result = healthcheck_root(root)
    elif args.command in {"diff", "verify", "promote", "promote-archive"}:
        plan, files = load_plan(Path(args.plan).resolve())
        if args.command == "diff":
            result = {"status": "pass", "release_id": plan.get("release_id"), "pointer_revision": plan.get("pointer_revision"), **diff_root(root, files)}
        elif args.command == "verify":
            result = {"status": "pass", "release_id": plan.get("release_id"), "pointer_revision": plan.get("pointer_revision"), **verify_root(root, files)}
        elif args.command == "promote":
            result = {
                "status": "pass",
                "release_id": plan.get("release_id"),
                "pointer_revision": plan.get("pointer_revision"),
                "promotion": promote_payload(Path(args.payload).resolve(), root, files),
                "target": verify_root(root, files),
            }
        else:
            result = {
                "status": "pass",
                "release_id": plan.get("release_id"),
                "pointer_revision": plan.get("pointer_revision"),
                "promotion": promote_archive(Path(args.archive).resolve(), root, files),
                "target": verify_root(root, files),
            }
    elif args.command == "preflight-current":
        result = preflight_current(root, Path(args.candidate).resolve(), args.expected_existing_sha256)
    else:
        result = promote_current(root, Path(args.candidate).resolve(), args.expected_existing_sha256)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
