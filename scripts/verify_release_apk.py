#!/usr/bin/env python3
"""Verify a signed Android release APK against an optional prior APK."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path


def find_sdk_tool(name: str) -> Path:
    sdk = Path(
        os.environ.get("ANDROID_SDK_ROOT")
        or os.environ.get("ANDROID_HOME")
        or Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk"
    )
    matches = sorted((sdk / "build-tools").glob(f"*/{name}"))
    if not matches:
        raise FileNotFoundError(f"Android SDK tool not found: {name}")
    return matches[-1]


def cert_digest(apksigner: Path, apk: Path) -> str:
    output = subprocess.check_output(
        [str(apksigner), "verify", "--print-certs", str(apk)],
        text=True,
        errors="replace",
    )
    match = re.search(r"Signer #1 certificate SHA-256 digest: ([0-9a-f]+)", output, re.I)
    if not match:
        raise RuntimeError(f"certificate digest missing for {apk}")
    return match.group(1).lower()


def package_identity(aapt: Path, apk: Path) -> tuple[str, str, str]:
    output = subprocess.check_output(
        [str(aapt), "dump", "badging", str(apk)],
        text=True,
        errors="replace",
    )
    match = re.search(
        r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'",
        output,
    )
    if not match:
        raise RuntimeError(f"package identity missing for {apk}")
    return match.group(1), match.group(2), match.group(3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--expect-version")
    parser.add_argument("--expect-code")
    parser.add_argument("--expect-package", default="com.magnetgoogo.app")
    parser.add_argument("--max-bytes", type=int, default=40 * 1024 * 1024)
    args = parser.parse_args()

    apk = args.apk.resolve()
    if not apk.is_file():
        raise FileNotFoundError(apk)

    apksigner = find_sdk_tool("apksigner.bat")
    aapt = find_sdk_tool("aapt.exe")
    package_name, version_code, version_name = package_identity(aapt, apk)
    digest = cert_digest(apksigner, apk)

    with zipfile.ZipFile(apk) as archive:
        abis = sorted(
            {
                name.split("/")[1]
                for name in archive.namelist()
                if name.startswith("lib/") and name.count("/") >= 2
            }
        )

    result = {
        "status": "PASS",
        "path": str(apk),
        "bytes": apk.stat().st_size,
        "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
        "package": package_name,
        "versionCode": version_code,
        "versionName": version_name,
        "abis": abis,
        "certificate_sha256": digest,
    }

    if package_name != args.expect_package:
        raise AssertionError(f"package mismatch: {package_name}")
    if args.expect_version and version_name != args.expect_version:
        raise AssertionError(f"versionName mismatch: {version_name}")
    if args.expect_code and version_code != args.expect_code:
        raise AssertionError(f"versionCode mismatch: {version_code}")
    if abis != ["arm64-v8a"]:
        raise AssertionError(f"unexpected ABI set: {abis}")
    if apk.stat().st_size > args.max_bytes:
        raise AssertionError(f"APK exceeds size limit: {apk.stat().st_size}")

    if args.previous:
        previous = args.previous.resolve()
        previous_digest = cert_digest(apksigner, previous)
        result["previous_certificate_sha256"] = previous_digest
        result["matches_previous_certificate"] = digest == previous_digest
        if digest != previous_digest:
            raise AssertionError("release certificate differs from previous APK")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
