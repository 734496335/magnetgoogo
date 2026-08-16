#!/usr/bin/env python3
"""K30S release-candidate main-flow smoke without Accessibility/UIAutomator.

Evidence comes from Android activity state, MagGoogo's own logs, and its private
source/media caches. This avoids MIUI's unreliable accessibility hierarchy.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERIAL = "a1ea223a"
DEBUG_PACKAGE = "com.magnetgoogo.app.debug"
FORMAL_PACKAGE = "com.magnetgoogo.app"
ACTIVITY = "com.magnetgoogo.app.MainActivity"
INTERFERERS = ("uni.UNIB56C11F",)


def adb(*args: str, timeout: int = 30) -> tuple[str, int]:
    proc = subprocess.run(
        ["adb", "-s", SERIAL, *args],
        capture_output=True,
        timeout=timeout,
    )
    return proc.stdout.decode("utf-8", errors="ignore").strip(), proc.returncode


def shell(*args: str, timeout: int = 30) -> tuple[str, int]:
    return adb("shell", *args, timeout=timeout)


def run_as(package: str, *args: str, timeout: int = 30) -> tuple[str, int]:
    return shell("run-as", package, *args, timeout=timeout)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def package_info(package: str) -> dict[str, Any]:
    out, rc = shell("dumpsys", "package", package)
    require(rc == 0 and f"Package [{package}]" in out, f"package not installed: {package}")
    version_name = re.search(r"versionName=([^\s]+)", out)
    version_code = re.search(r"versionCode=(\d+)", out)
    first_install = re.search(r"firstInstallTime=([^\r\n]+)", out)
    return {
        "package": package,
        "versionName": version_name.group(1) if version_name else "",
        "versionCode": int(version_code.group(1)) if version_code else 0,
        "firstInstallTime": first_install.group(1).strip() if first_install else "",
    }


def prepare_device() -> None:
    for package in INTERFERERS:
        shell("am", "force-stop", package)
    shell("input", "keyevent", "224")
    shell("wm", "dismiss-keyguard")
    shell("svc", "power", "stayon", "true")


def current_focus() -> str:
    out, _ = shell("dumpsys", "window")
    for line in out.splitlines():
        if "mCurrentFocus=" in line:
            return line.strip()
    return ""


def start_activity(package: str, *, uri: str | None = None) -> dict[str, Any]:
    if uri:
        out, rc = shell(
            "am", "start", "-W",
            "-a", "android.intent.action.VIEW",
            "-d", uri,
            f"{package}/{ACTIVITY}",
            timeout=40,
        )
    else:
        out, rc = shell("am", "start", "-W", "-n", f"{package}/{ACTIVITY}", timeout=40)
    require(rc == 0 and "Status: ok" in out, f"start failed {uri or 'main'}: {out}")
    time.sleep(1.5)
    focus = current_focus()
    require(package in focus, f"focus mismatch after {uri or 'main'}: {focus}")
    timings: dict[str, Any] = {"focus": focus}
    for key in ("LaunchState", "Activity", "TotalTime", "WaitTime"):
        match = re.search(rf"^{key}:\s*(.+)$", out, re.M)
        if match:
            value = match.group(1).strip()
            timings[key] = int(value) if key.endswith("Time") and value.isdigit() else value
    return timings


def read_private_json(package: str, relative_path: str) -> dict[str, Any] | None:
    out, rc = run_as(package, "cat", relative_path, timeout=20)
    if rc != 0 or not out.strip():
        return None
    try:
        value = json.loads(out)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def list_private(package: str, relative_path: str) -> list[str]:
    out, rc = run_as(package, "ls", "-1", relative_path, timeout=20)
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def logcat_for(package: str) -> str:
    pid, _ = shell("pidof", package)
    if not pid.strip():
        return ""
    out, _ = adb("logcat", "-d", "-v", "brief", "--pid", pid.strip(), timeout=30)
    return out


def source_cache_evidence(package: str) -> dict[str, Any]:
    cache = read_private_json(package, "files/source-cache/sources.cache.json")
    require(cache is not None, "source cache missing")
    require(isinstance(cache.get("count"), int) and cache["count"] >= 100, f"unexpected source count: {cache.get('count')}")
    require(isinstance(cache.get("encPayload"), str) and len(cache["encPayload"]) > 1000, "encrypted source payload missing")
    return {
        "count": cache.get("count"),
        "savedAt": cache.get("savedAt"),
        "expiryHours": cache.get("expiryHours"),
        "remoteUrl": cache.get("remoteUrl"),
        "encrypted": True,
    }


def media_cache_evidence(package: str) -> tuple[dict[str, Any], dict[str, Any]]:
    index = read_private_json(package, "files/media-release-cache-v2/index.json")
    movie = read_private_json(package, "files/media-release-cache-v2/feeds/movie.json")
    require(index is not None, "media cache index missing")
    require(movie is not None, "movie feed cache missing")
    identity = index.get("identity") if isinstance(index.get("identity"), dict) else {}
    feed = movie.get("feed") if isinstance(movie.get("feed"), dict) else {}
    items = feed.get("items") if isinstance(feed.get("items"), list) else []
    require(isinstance(identity.get("pointer_revision"), int) and identity["pointer_revision"] >= 1, "invalid media pointer revision")
    require(len(items) >= 50, f"movie feed unexpectedly small: {len(items)}")
    first = items[0] if items and isinstance(items[0], dict) else {}
    require(bool(first.get("movie_id")), "movie feed first item has no id")
    return {
        "pointer_revision": identity.get("pointer_revision"),
        "release_id": identity.get("release_id"),
        "pointer_sha256": identity.get("pointer_sha256"),
        "endpoint": index.get("endpoint"),
        "movie_count": len(items),
    }, first


def assert_no_fatal(package: str) -> dict[str, Any]:
    logs = logcat_for(package)
    bad = [
        line for line in logs.splitlines()
        if "FATAL EXCEPTION" in line or "AndroidRuntime" in line or "ANR in" in line
    ]
    require(not bad, "fatal/anr log detected: " + " | ".join(bad[-5:]))
    return {
        "fatal_or_anr": 0,
        "source_log_seen": "SourceStore" in logs,
        "config_log_seen": "ConfigChecker" in logs,
        "media_log_seen": "MediaRelease" in logs or "ResourceFeed" in logs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default=DEBUG_PACKAGE)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    package = args.package

    devices, _ = adb("devices")
    require(SERIAL in devices, f"device {SERIAL} unavailable")
    prepare_device()
    adb("logcat", "-c")

    report: dict[str, Any] = {
        "status": "PASS",
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "device": SERIAL,
        "package": package,
        "package_info_before": package_info(package),
    }

    shell("am", "force-stop", package)
    report["cold_start"] = start_activity(package)
    time.sleep(8)
    report["source_cache"] = source_cache_evidence(package)

    report["resources_route"] = start_activity(package, uri="magnetgoogo:///resources")
    time.sleep(10)
    media, first_movie = media_cache_evidence(package)
    report["media_cache"] = media

    movie_id = str(first_movie["movie_id"])
    movie_kind = str(first_movie.get("content_kind") or "movie")
    report["movie_detail_route"] = start_activity(
        package,
        uri=f"magnetgoogo:///movie/{movie_id}?kind={movie_kind}",
    )
    time.sleep(8)
    detail_files = [name for name in list_private(package, "files/media-release-cache-v2/details") if name.endswith(".json") and not name.startswith(".")]
    report["movie_detail"] = {"movie_id": movie_id, "cached_detail_files": len(detail_files)}
    require(detail_files, "movie detail route did not create/use a detail cache shard")

    report["favorites_route"] = start_activity(package, uri="magnetgoogo:///favorites")
    report["settings_route"] = start_activity(package, uri="magnetgoogo:///settings")

    shell("input", "keyevent", "3")  # HOME
    time.sleep(1)
    report["hot_resume"] = start_activity(package)

    shell("am", "force-stop", package)
    time.sleep(1)
    report["cold_resume"] = start_activity(package)
    time.sleep(2)

    report["runtime_logs"] = assert_no_fatal(package)
    report["package_info_after"] = package_info(package)
    require(
        report["package_info_before"]["versionName"] == report["package_info_after"]["versionName"]
        and report["package_info_before"]["versionCode"] == report["package_info_after"]["versionCode"],
        "package identity changed during smoke",
    )

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
