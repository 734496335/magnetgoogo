from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
import uuid
from pathlib import Path


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MagnetGoogo-Compute-Finalizer/1.0", "Cache-Control": "no-cache"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=60) as response:
        if int(response.status) != 200:
            raise RuntimeError(f"unexpected HTTP status {response.status}: {url}")
        return response.read()


def _stream_package(url: str, destination: Path) -> tuple[str, int]:
    request = urllib.request.Request(url, headers={"User-Agent": "MagnetGoogo-Compute-Finalizer/1.0", "Cache-Control": "no-cache"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    digest = hashlib.sha256()
    size = 0
    with opener.open(request, timeout=60) as response, destination.open("wb") as output:
        if int(response.status) != 200:
            raise RuntimeError(f"unexpected HTTP status {response.status}: {url}")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:18766")
    parser.add_argument("--output-dir", default="/var/lib/magnet-media/compute-inbox")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    pointer_bytes = _get(f"{base}/current.json")
    pointer = json.loads(pointer_bytes.decode("utf-8"))
    if pointer.get("schema_version") != "media-compute-handoff-pointer/1":
        raise RuntimeError("compute handoff pointer schema mismatch")
    relative = str(pointer.get("package") or "")
    if not relative.startswith("packages/") or ".." in Path(relative).parts:
        raise RuntimeError("compute handoff package path is unsafe")
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    package_path = output / Path(relative).name
    temporary = output / f".{package_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        digest, package_size = _stream_package(f"{base}/{relative}", temporary)
        if package_size != int(pointer.get("package_size") or -1):
            raise RuntimeError("compute handoff package size mismatch")
        if digest != pointer.get("package_sha256"):
            raise RuntimeError("compute handoff package SHA-256 mismatch")
        os.replace(temporary, package_path)
    finally:
        temporary.unlink(missing_ok=True)
    pointer_tmp = output / f".current.{uuid.uuid4().hex}.tmp"
    pointer_tmp.write_bytes(pointer_bytes)
    os.replace(pointer_tmp, output / "current.json")
    print(json.dumps({"status": "pass", "run_id": pointer.get("run_id"), "package_path": str(package_path), "package_sha256": digest, "package_size": package_size}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
