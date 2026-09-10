from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.request
import uuid
from pathlib import Path


_PACKAGE_RE = re.compile(r"^packages/[A-Za-z0-9._-]+\.tar$")
_REMOTE_OUTBOX_ROOT = "/var/lib/magnet-media/outbox"


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


def _validate_ssh_inputs(target: str, identity: Path, known_hosts: Path) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+", target):
        raise RuntimeError("compute handoff SSH target is invalid")
    for label, path in (("identity", identity), ("known_hosts", known_hosts)):
        if not path.is_absolute() or not path.is_file():
            raise RuntimeError(f"compute handoff SSH {label} file is invalid")


def _ssh_command(target: str, identity: Path, known_hosts: Path, remote_path: str) -> list[str]:
    if not remote_path.startswith(f"{_REMOTE_OUTBOX_ROOT}/") or any(char.isspace() for char in remote_path):
        raise RuntimeError("compute handoff remote path is invalid")
    return [
        "/usr/bin/ssh",
        "-T",
        "-i",
        str(identity),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "ConnectTimeout=20",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=4",
        target,
        f"cat -- {remote_path}",
    ]


def _ssh_get(target: str, identity: Path, known_hosts: Path, remote_path: str) -> bytes:
    process = subprocess.run(
        _ssh_command(target, identity, known_hosts, remote_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace")[-1000:].strip()
        raise RuntimeError(f"compute handoff SSH read failed: {message or process.returncode}")
    if len(process.stdout) > 64 * 1024:
        raise RuntimeError("compute handoff pointer is unexpectedly large")
    return process.stdout


def _ssh_stream_package(target: str, identity: Path, known_hosts: Path, remote_path: str, destination: Path) -> tuple[str, int]:
    process = subprocess.Popen(
        _ssh_command(target, identity, known_hosts, remote_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("compute handoff SSH stream could not start")
    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("wb") as output:
            while True:
                chunk = process.stdout.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        stderr = process.stderr.read(64 * 1024)
        returncode = process.wait(timeout=60)
    except BaseException:
        process.kill()
        process.wait()
        raise
    if returncode != 0:
        message = stderr.decode("utf-8", errors="replace")[-1000:].strip()
        raise RuntimeError(f"compute handoff SSH stream failed: {message or returncode}")
    return digest.hexdigest(), size


def _load_pointer(pointer_bytes: bytes) -> dict[str, object]:
    try:
        pointer = json.loads(pointer_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("compute handoff pointer is invalid JSON") from exc
    if not isinstance(pointer, dict) or pointer.get("schema_version") != "media-compute-handoff-pointer/1":
        raise RuntimeError("compute handoff pointer schema mismatch")
    relative = str(pointer.get("package") or "")
    if not _PACKAGE_RE.fullmatch(relative) or ".." in Path(relative).parts:
        raise RuntimeError("compute handoff package path is unsafe")
    expected_sha = str(pointer.get("package_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise RuntimeError("compute handoff package SHA-256 is invalid")
    expected_size = pointer.get("package_size")
    if type(expected_size) is not int or expected_size <= 0:
        raise RuntimeError("compute handoff package size is invalid")
    return pointer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--ssh-target")
    parser.add_argument("--ssh-identity")
    parser.add_argument("--ssh-known-hosts")
    parser.add_argument("--output-dir", default="/var/lib/magnet-media/compute-inbox")
    args = parser.parse_args()
    use_ssh = bool(args.ssh_target)
    if use_ssh:
        if args.base or not args.ssh_identity or not args.ssh_known_hosts:
            parser.error("SSH mode requires --ssh-target/--ssh-identity/--ssh-known-hosts and no --base")
        identity = Path(args.ssh_identity).resolve()
        known_hosts = Path(args.ssh_known_hosts).resolve()
        _validate_ssh_inputs(args.ssh_target, identity, known_hosts)
        pointer_bytes = _ssh_get(args.ssh_target, identity, known_hosts, f"{_REMOTE_OUTBOX_ROOT}/current.json")
    else:
        if args.ssh_identity or args.ssh_known_hosts:
            parser.error("SSH identity options require --ssh-target")
        base = (args.base or "http://127.0.0.1:18766").rstrip("/")
        if not base.startswith("http://127.0.0.1:"):
            raise RuntimeError("HTTP compute handoff base must remain loopback-only")
        pointer_bytes = _get(f"{base}/current.json")
    pointer = _load_pointer(pointer_bytes)
    relative = str(pointer["package"])
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    package_path = output / Path(relative).name
    temporary = output / f".{package_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        if use_ssh:
            digest, package_size = _ssh_stream_package(
                args.ssh_target,
                identity,
                known_hosts,
                f"{_REMOTE_OUTBOX_ROOT}/{relative}",
                temporary,
            )
        else:
            digest, package_size = _stream_package(f"{base}/{relative}", temporary)
        if package_size != pointer["package_size"]:
            raise RuntimeError("compute handoff package size mismatch")
        if digest != pointer["package_sha256"]:
            raise RuntimeError("compute handoff package SHA-256 mismatch")
        os.replace(temporary, package_path)
    finally:
        temporary.unlink(missing_ok=True)
    pointer_tmp = output / f".current.{uuid.uuid4().hex}.tmp"
    pointer_tmp.write_bytes(pointer_bytes)
    os.replace(pointer_tmp, output / "current.json")
    print(json.dumps({"status": "pass", "transport": "ssh" if use_ssh else "http", "run_id": pointer.get("run_id"), "package_path": str(package_path), "package_sha256": digest, "package_size": package_size}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
