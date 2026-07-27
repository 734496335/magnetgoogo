"""Verify and optionally promote one canonical media publish plan on a static mirror."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fail(message: str, **context: Any) -> None:
    payload = {"status": "failed", "message": message, "context": context}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
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
    if key == "v1/current.json":
        fail("production current.json is forbidden in the immutable mirror plan")
    allowed = (
        key.startswith("v1/objects/")
        or key.startswith("v1/covers/")
        or key.startswith("v1/releases/")
        or key.startswith("staging/pointers/")
    )
    if not allowed:
        fail("plan key is outside the frozen mirror allowlist", key=key)
    return key


def load_plan(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("failed to read mirror plan", path=str(path), error=type(exc).__name__)
    if not isinstance(value, dict) or value.get("schema_version") != "media-publish-plan/1":
        fail("mirror plan schema is invalid", path=str(path))
    files = value.get("files")
    if not isinstance(files, list) or not files:
        fail("mirror plan has no files", path=str(path))
    normalized = []  # type: List[Dict[str, Any]]
    seen = set()  # type: Set[str]
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
        fail(
            "mirror plan total_file_count mismatch",
            expected=value.get("total_file_count"),
            actual=len(normalized),
        )
    return value, normalized


def resolve_key(root: Path, key: str) -> Path:
    candidate = (root / key).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        fail("mirror key escapes the root", key=key)
    return candidate


def verify_root(root: Path, files: List[Dict[str, Any]], *, exact: bool) -> Dict[str, Any]:
    expected = {item["key"] for item in files}
    total_bytes = 0
    for item in files:
        path = resolve_key(root, item["key"])
        if not path.is_file():
            fail("mirror file is missing", key=item["key"], path=str(path))
        size = path.stat().st_size
        digest = sha256_file(path)
        if size != item["size"] or digest != item["sha256"]:
            fail(
                "mirror file verification failed",
                key=item["key"],
                expected_size=item["size"],
                actual_size=size,
                expected_sha256=item["sha256"],
                actual_sha256=digest,
            )
        total_bytes += size
    if exact:
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        }
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing or unexpected:
            fail("mirror file set is not exact", missing=missing[:20], unexpected=unexpected[:20])
    return {"verified_files": len(files), "verified_bytes": total_bytes}


def promote(source_root: Path, target_root: Path, files: List[Dict[str, Any]]) -> Dict[str, int]:
    copied = 0
    reused = 0
    target_root.mkdir(parents=True, exist_ok=True)
    for item in files:
        source = resolve_key(source_root, item["key"])
        target = resolve_key(target_root, item["key"])
        target.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(str(target.parent), 0o755)
        if target.exists():
            if not target.is_file() or target.stat().st_size != item["size"] or sha256_file(target) != item["sha256"]:
                fail("immutable mirror target conflicts with the plan", key=item["key"], path=str(target))
            os.chmod(str(target), 0o644)
            reused += 1
            continue
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(source, temporary)
            if temporary.stat().st_size != item["size"] or sha256_file(temporary) != item["sha256"]:
                fail("temporary mirror copy failed verification", key=item["key"])
            os.chmod(str(temporary), 0o644)
            os.replace(str(temporary), str(target))
        finally:
            if temporary.exists():
                temporary.unlink()
        copied += 1
    return {"copied": copied, "reused": reused}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--promote-to")
    parser.add_argument("--exact", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    plan, files = load_plan(Path(args.plan).resolve())
    source_report = verify_root(root, files, exact=args.exact)
    result = {  # type: Dict[str, Any]
        "status": "pass",
        "release_id": plan.get("release_id"),
        "pointer_revision": plan.get("pointer_revision"),
        "source": source_report,
        "current_promoted": False,
    }
    if args.promote_to:
        target = Path(args.promote_to).resolve()
        result["promotion"] = promote(root, target, files)
        result["target"] = verify_root(target, files, exact=False)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
