#!/usr/bin/env python3
"""Offline capacity checks plus read-only production observation; never sends."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("candidate_media_health", sys.argv[1])
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)

def indexed(checks):
    return {item["key"]: item for item in checks}

with tempfile.TemporaryDirectory(prefix="media-capacity-contract-") as folder:
    base = Path(folder)
    root = base / "public"
    release = root / "v1" / "releases" / "fixture-r1"
    release.mkdir(parents=True)
    pointer = root / "v1" / "current.json"
    pointer.write_text(json.dumps({"pointer_revision": 1, "manifest_path": "/v1/releases/fixture-r1/manifest.json"}))
    source = base / "publisher.py"
    source.write_text("_MAX_MANIFEST_BYTES = 1000\n")
    manifest = release / "manifest.json"
    for size, expected in ((799, "success"), (800, "failure"), (1001, "failure")):
        manifest.write_bytes(b"x" * size)
        checks = indexed(health.manifest_capacity_checks(root, source))
        assert checks["media-publish-capacity"]["state"] == expected
        assert "media-publish" not in checks
    source.write_text("_MAX_MANIFEST_BYTES = True\n")
    checks = indexed(health.manifest_capacity_checks(root, source))
    assert set(checks) == {"media-publish-capacity-observation"}
    assert checks["media-publish-capacity-observation"]["state"] == "failure"
    source.write_text("_MAX_MANIFEST_BYTES = 1000\n")
    outside = base / "outside.json"
    outside.write_bytes(b"x" * 100)
    manifest.unlink()
    manifest.symlink_to(outside)
    checks = indexed(health.manifest_capacity_checks(root, source))
    assert set(checks) == {"media-publish-capacity-observation"}
    manifest.unlink()
    manifest.write_bytes(b"x" * 100)
    pointer.unlink()
    outside.write_text(json.dumps({"pointer_revision": 1, "manifest_path": "/v1/releases/fixture-r1/manifest.json"}))
    pointer.symlink_to(outside)
    checks = indexed(health.manifest_capacity_checks(root, source))
    assert set(checks) == {"media-publish-capacity-observation"}

live = health.manifest_capacity_checks(sys.argv[2], sys.argv[3])
assert all(item["state"] == "success" for item in live), live
print(json.dumps({"status": "PASS", "python": sys.version.split()[0], "offline_contract_cases": 6,
                  "symlink_escape_tests": 2, "live_read_only": live, "notifications_sent": 0}, ensure_ascii=False))
