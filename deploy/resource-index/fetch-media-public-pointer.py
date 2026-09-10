from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def fail(message: str, **context: Any) -> None:
    print(json.dumps({"status": "failed", "message": message, "context": context}, ensure_ascii=False, sort_keys=True))
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    if not base.startswith("https://"):
        fail("media public base must use HTTPS", base=base)
    if not 1 <= args.timeout <= 120:
        fail("pointer fetch timeout is out of range", timeout=args.timeout)
    request = urllib.request.Request(
        f"{base}/v1/current.json",
        headers={"User-Agent": "MagnetGoogo-Oracle-Acceptance/1", "Cache-Control": "no-cache"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=args.timeout) as response:
            if int(response.status) != 200:
                fail("media current pointer returned non-200", base=base, status=response.status)
            payload = response.read()
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        fail("media current pointer request failed", base=base, error=type(exc).__name__)
    try:
        pointer = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("media current pointer is invalid JSON", base=base, error=type(exc).__name__)
    if not isinstance(pointer, dict):
        fail("media current pointer must be an object", base=base)
    revision = pointer.get("pointer_revision")
    release_id = pointer.get("release_id")
    manifest_path = pointer.get("manifest_path")
    manifest_sha256 = pointer.get("manifest_sha256")
    if type(revision) is not int or revision < 1 or not isinstance(release_id, str) or not release_id:
        fail("media current pointer control fields are invalid", base=base)
    expected_manifest = f"/v1/releases/{release_id}/manifest.json"
    if manifest_path != expected_manifest:
        fail("media current pointer release/manifest binding is invalid", base=base, manifest_path=manifest_path)
    if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64 or any(char not in "0123456789abcdef" for char in manifest_sha256):
        fail("media current pointer manifest SHA-256 is invalid", base=base)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.name}.{uuid.uuid4().hex}.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    report = {
        "schema_version": "media-public-pointer-fetch/1",
        "status": "pass",
        "base": base,
        "pointer_revision": revision,
        "release_id": release_id,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "output": str(output),
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
