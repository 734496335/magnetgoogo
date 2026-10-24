import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "deploy/resource-index/linux/media-health-check.py"


@pytest.fixture
def health():
    spec = importlib.util.spec_from_file_location("media_health_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def fixture(health, role="compute"):
    now = health.parse_finished("2026-10-24T12:00:00Z")
    doc = {"mode": "compute" if role == "compute" else "publish", "status": "success", "finished_at": iso(now - 600),
           "required_degraded_sources": [], "failed_freshness_groups": [],
           "freshness_groups": {"series": {"status": "pass", "fresh_count": 4, "member_count": 4, "min_fresh": 2}}}
    unit = {"LoadState": "loaded", "ActiveState": "inactive", "SubState": "dead", "Result": "success", "ExecMainStatus": "0", "ExecMainStartTimestampMonotonic": "90000000000"}
    timer = {"LoadState": "loaded", "ActiveState": "active"}
    return {"role": role, "document": doc, "mtime": now - 600, "unit": unit, "timer": timer, "now": now, "monotonic_now": 100000}


def indexed(checks):
    return {item["key"]: item for item in checks}


def test_fresh_success_and_future_business_release_date(health):
    args = fixture(health)
    args["document"]["release_id"] = "20270101T000000Z-future-business-date"
    assert all(item["state"] == "success" for item in health.evaluate(**args))


def test_service_failure_is_detected_without_new_status(health):
    args = fixture(health)
    args["unit"].update(ActiveState="failed", Result="exit-code", ExecMainStatus="1", ExecMainStartTimestampMonotonic="99900000000")
    checks = indexed(health.evaluate(**args))
    assert checks["media-compute"]["state"] == "failure"
    assert checks["media-source-observation"]["state"] == "failure"
    assert "media-source-freshness" not in checks


def test_missing_status_never_generates_recovery(health):
    args = fixture(health)
    args.update(document={}, mtime=None)
    checks = indexed(health.evaluate(**args))
    assert checks["media-compute"]["state"] == "failure"
    assert checks["media-source-observation"]["state"] == "failure"
    assert "media-source-freshness" not in checks


def test_touched_old_status_still_overdue(health):
    args = fixture(health)
    args["document"]["finished_at"] = iso(args["now"] - 31 * 3600)
    args["mtime"] = args["now"]
    assert indexed(health.evaluate(**args))["media-compute"]["state"] == "failure"


def test_future_or_naive_finished_time_is_unknown(health):
    for value in ("2027-01-01T00:00:00Z", "2026-10-24T11:50:00", None):
        args = fixture(health)
        args["document"]["finished_at"] = value
        assert indexed(health.evaluate(**args))["media-compute"]["state"] == "failure"


def test_running_job_preserves_existing_incidents(health):
    args = fixture(health)
    args["unit"].update(ActiveState="activating", SubState="start", ExecMainStartTimestampMonotonic="99000000000")
    checks = indexed(health.evaluate(**args))
    assert checks["media-compute"]["state"] == "pending"
    assert not any(k.startswith("media-source") for k in checks)


def test_running_timeout_has_no_source_recovery(health):
    args = fixture(health)
    args["unit"].update(ActiveState="activating", SubState="start", ExecMainStartTimestampMonotonic="1000000")
    checks = indexed(health.evaluate(**args))
    assert checks["media-compute"]["state"] == "failure"
    assert checks["media-source-observation"]["state"] == "failure"
    assert "media-source-freshness" not in checks


def test_finalizer_without_source_fields_is_valid_and_no_change_is_success(health):
    args = fixture(health, "finalizer")
    args["document"] = {"status": "success", "mode": "publish", "finished_at": iso(args["now"] - 600), "result": {"no_change": True, "published": False}}
    checks = indexed(health.evaluate(**args))
    assert set(checks) == {"media-publish", "media-publish-schedule"}
    assert checks["media-publish"]["state"] == "success"


@pytest.mark.parametrize("field", ["error_code", "code"])
def test_failed_finalizer_only_emits_safe_error_code(health, field):
    args = fixture(health, "finalizer")
    args["document"].update(status="failed", error={field: "PUBLISH_CONFIG_ERROR", "message": "secret=https://example.invalid/path?token=do-not-send"})
    checks = indexed(health.evaluate(**args))
    assert checks["media-publish"]["state"] == "failure"
    body = json.dumps(checks)
    assert "PUBLISH_CONFIG_ERROR" in body
    assert "do-not-send" not in body and "example.invalid" not in body


def test_quorum_failure_and_redundancy_are_independent(health):
    args = fixture(health)
    group = args["document"]["freshness_groups"]["series"]
    group.update(fresh_count=3)
    checks = indexed(health.evaluate(**args))
    assert checks["media-source-freshness"]["state"] == "success"
    assert checks["media-source-redundancy"]["state"] == "failure"
    group.update(fresh_count=1, status="failed")
    checks = indexed(health.evaluate(**args))
    assert checks["media-source-freshness"]["state"] == "failure"
    assert checks["media-source-redundancy"]["state"] == "failure"
    group.update(fresh_count=4, status="pass")
    checks = indexed(health.evaluate(**args))
    assert checks["media-source-freshness"]["state"] == "success"
    assert checks["media-source-redundancy"]["state"] == "success"


def test_unknown_source_schema_does_not_clear_existing_source_incidents(health):
    args = fixture(health)
    del args["document"]["freshness_groups"]
    checks = indexed(health.evaluate(**args))
    assert checks["media-source-observation"]["state"] == "failure"
    assert "media-source-freshness" not in checks and "media-source-redundancy" not in checks


def test_disabled_timer_is_reported_independently(health):
    args = fixture(health)
    args["timer"]["ActiveState"] = "inactive"
    checks = indexed(health.evaluate(**args))
    assert checks["media-compute-schedule"]["state"] == "failure"
    assert checks["media-compute"]["state"] == "success"


def test_dry_run_cannot_spawn_notifier_or_write_state(health, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry-run called subprocess")
    monkeypatch.setattr(health.subprocess, "run", forbidden)
    state = tmp_path / "never-created"
    checks = [health.observation("media-compute", "failure", "test", "test")]
    assert health.dispatch(checks, Path("missing.py"), state, dry_run=True) == 0
    assert not state.exists()


def test_dispatch_preserves_pending_and_uses_six_hour_dedupe(health, monkeypatch, tmp_path):
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(health.subprocess, "run", fake_run)
    checks = [health.observation("media-compute", "pending", "running", "wait"), health.observation("media-source-freshness", "failure", "bad", "bad")]
    assert health.dispatch(checks, Path("notify.py"), tmp_path) == 0
    assert len(calls) == 1
    assert calls[0][calls[0].index("--repeat-hours") + 1] == "6"
    assert calls[0][calls[0].index("--state-file") + 1].endswith("media-source-freshness.json")


def test_corrupt_status_is_unknown(health, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")
    assert health.read_status(path) == ({}, None)


def test_new_host_scripts_are_lf_only():
    folder = ROOT / "deploy/resource-index/linux"
    for name in ("media-health-check.py", "magnet-media-health.service", "magnet-media-health.timer", "media-health.example.env", "install-media-health.sh"):
        assert b"\r\n" not in (folder / name).read_bytes()

def capacity_files(tmp_path, size=799, source_text="_MAX_MANIFEST_BYTES = 1000\n"):
    public = tmp_path / "public"
    manifest = public / "v1" / "releases" / "release-r68" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(b"x" * size)
    pointer = public / "v1" / "current.json"
    pointer.write_text(json.dumps({"pointer_revision": 68, "manifest_path": "/v1/releases/release-r68/manifest.json"}), encoding="utf-8")
    source = tmp_path / "worker_bridge.py"
    source.write_text(source_text, encoding="utf-8")
    return public, source, pointer, manifest


@pytest.mark.parametrize("size,expected", [(799, "success"), (800, "failure"), (1001, "failure")])
def test_capacity_warns_at_eighty_percent_without_changing_publish(health, tmp_path, size, expected):
    public, source, _, _ = capacity_files(tmp_path, size=size)
    checks = indexed(health.manifest_capacity_checks(public, source))
    assert checks["media-publish-capacity"]["state"] == expected
    assert checks["media-publish-capacity"]["severity"] == "P2"
    assert "1000" in checks["media-publish-capacity"]["message"]
    assert "media-publish" not in checks


def test_real_rev67_size_would_warn_before_oct18_capacity_outage(health, tmp_path):
    # Captured production values: rev67 used 99.57% of the former 2 MiB cap.
    public, source, pointer, _ = capacity_files(
        tmp_path, size=2088180, source_text="_MAX_MANIFEST_BYTES = 2 * 1024 * 1024\n")
    pointer.write_text(json.dumps({"pointer_revision": 67, "manifest_path": "/v1/releases/release-r68/manifest.json"}), encoding="utf-8")
    checks = indexed(health.manifest_capacity_checks(public, source))
    assert checks["media-publish-capacity"]["state"] == "failure"
    assert "99.57%" in checks["media-publish-capacity"]["message"]


def test_capacity_reads_installed_multiplier_and_never_executes_source(health, tmp_path):
    public, source, _, _ = capacity_files(tmp_path, source_text="_MAX_MANIFEST_BYTES = 8 * 1024 * 1024\nraise RuntimeError('must not execute')\n")
    checks = indexed(health.manifest_capacity_checks(public, source))
    assert checks["media-publish-capacity"]["state"] == "success"
    assert "8388608" in checks["media-publish-capacity"]["message"]


@pytest.mark.parametrize("source_text", [
    "_MAX_MANIFEST_BYTES = True\n",
    "_MAX_MANIFEST_BYTES = 0\n",
    "_MAX_MANIFEST_BYTES = -1000\n",
    "_MAX_MANIFEST_BYTES = int('1000')\n",
    "_MAX_MANIFEST_BYTES = 128 * 1024 * 1024\n",
    "_MAX_MANIFEST_BYTES = 1000\n_MAX_MANIFEST_BYTES = 2000\n",
    "_MAX_MANIFEST_BYTES = 1000\n_MAX_MANIFEST_BYTES += 1\n",
    "_MAX_MANIFEST_BYTES = 1000\n_MAX_MANIFEST_BYTES: int = 2000\n",
    "OTHER_LIMIT = 1000\n",
])
def test_capacity_unknown_contract_preserves_previous_capacity_incident(health, tmp_path, source_text):
    public, source, _, _ = capacity_files(tmp_path, source_text=source_text)
    checks = indexed(health.manifest_capacity_checks(public, source))
    assert set(checks) == {"media-publish-capacity-observation"}
    assert checks["media-publish-capacity-observation"]["state"] == "failure"


@pytest.mark.parametrize("manifest_path", [
    "/etc/shadow", "/v1/releases/../manifest.json", "/v1/releases/r68/../../manifest.json",
    "https://example.invalid/private.json",
])
def test_capacity_rejects_untrusted_pointer_paths_without_recovery(health, tmp_path, manifest_path):
    public, source, pointer, _ = capacity_files(tmp_path)
    pointer.write_text(json.dumps({"pointer_revision": 68, "manifest_path": manifest_path}), encoding="utf-8")
    checks = indexed(health.manifest_capacity_checks(public, source))
    assert set(checks) == {"media-publish-capacity-observation"}
    assert checks["media-publish-capacity-observation"]["state"] == "failure"


def test_capacity_missing_manifest_never_recovers_capacity_incident(health, tmp_path):
    public, source, _, manifest = capacity_files(tmp_path)
    manifest.unlink()
    checks = indexed(health.manifest_capacity_checks(public, source))
    assert set(checks) == {"media-publish-capacity-observation"}


def test_capacity_error_does_not_clear_or_hide_running_publish_incident(health, tmp_path):
    args = fixture(health, "finalizer")
    args["unit"].update(ActiveState="activating", SubState="start", ExecMainStartTimestampMonotonic="99000000000")
    checks = indexed(health.evaluate(**args) + health.manifest_capacity_checks(tmp_path, tmp_path / "missing.py"))
    assert checks["media-publish"]["state"] == "pending"
    assert checks["media-publish-capacity-observation"]["state"] == "failure"


def test_capacity_manifest_symlink_cannot_escape_public_root(health, tmp_path):
    public, source, _, manifest = capacity_files(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("not-a-public-manifest", encoding="utf-8")
    manifest.unlink()
    try:
        manifest.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable in this Windows environment")
    checks = indexed(health.manifest_capacity_checks(public, source))
    assert set(checks) == {"media-publish-capacity-observation"}
    assert checks["media-publish-capacity-observation"]["state"] == "failure"
