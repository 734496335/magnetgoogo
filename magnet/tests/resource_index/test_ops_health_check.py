import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load():
    spec = importlib.util.spec_from_file_location("ops_health_test", ROOT / "deploy/ops-health/linux/ops-health-check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def completed(**overrides):
    result = {"LoadState": "loaded", "ActiveState": "inactive", "Result": "success",
              "ExecMainStatus": "0", "ExecMainStartTimestampMonotonic": "900000000",
              "ExecMainExitTimestampMonotonic": "950000000"}
    result.update(overrides)
    return result


def test_oneshot_inactive_after_success_is_healthy():
    h = load()
    assert h.job_finding({"unit": "job.service", "max_age_seconds": 100}, completed(), 1000)["healthy"] is True


def test_stale_success_is_a_failure():
    h = load()
    assert h.job_finding({"unit": "job.service", "max_age_seconds": 40}, completed(), 1000)["healthy"] is False


def test_running_job_is_not_failed_for_old_exit_code():
    h = load()
    state = completed(ActiveState="activating", Result="exit-code", ExecMainStatus="1")
    assert h.job_finding({"unit": "job.service"}, state, 1000)["healthy"] is None


def test_running_job_over_deadline_is_failure():
    h = load()
    state = completed(ActiveState="activating")
    assert h.job_finding({"unit": "job.service", "max_run_seconds": 50}, state, 1000)["healthy"] is False


def test_unknown_start_is_not_recovery():
    h = load()
    state = completed(ActiveState="activating", ExecMainStartTimestampMonotonic="0")
    assert h.job_finding({"unit": "job.service"}, state, 1000)["healthy"] is False


def test_missing_unit_fails():
    h = load()
    assert h.job_finding({"unit": "job.service"}, {}, 1000)["healthy"] is False


def test_first_boot_without_completed_run_does_not_emit_recovery(monkeypatch):
    h = load()
    state = completed(ExecMainStartTimestampMonotonic="0", ExecMainExitTimestampMonotonic="0")
    item = h.job_finding({"unit": "job.service", "max_age_seconds": 3600}, state, 1000)
    assert item["healthy"] is None
    monkeypatch.setattr(h, "command", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not send")))
    assert h.notify({"host_label": "test"}, [item], False) == 0


def test_dry_run_cannot_send(monkeypatch):
    h = load()
    monkeypatch.setattr(h, "command", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not send")))
    assert h.notify({"host_label": "test"}, [h.finding("a", "A", False, "failed")], True) == 0


def test_new_ops_alerts_use_wechat_without_changing_legacy_environment(monkeypatch):
    h = load()
    monkeypatch.setenv("MAGNET_ALERT_TRANSPORT", "mirror")
    captured = []
    def fake_command(args, timeout=12, env=None):
        captured.append(env["MAGNET_ALERT_TRANSPORT"])
        return 0, ""
    monkeypatch.setattr(h, "command", fake_command)
    h.notify({"host_label": "test"}, [h.finding("a", "A", False, "failed")], False)
    assert captured == ["xtuis"]
    assert h.os.environ["MAGNET_ALERT_TRANSPORT"] == "mirror"


def test_inactive_continuous_service_and_timer_fail(monkeypatch):
    h = load()
    monkeypatch.setattr(h, "unit_state", lambda _name: {"LoadState": "loaded", "ActiveState": "inactive"})
    results = h.collect({"services": [{"unit": "a.service"}], "timers": [{"unit": "a.timer"}]}, uptime=1000)
    assert len(results) == 2
    assert all(item["healthy"] is False for item in results)


def test_memory_uses_available_instead_of_free(monkeypatch):
    h = load()
    monkeypatch.setattr(h.Path, "read_text", lambda *_a, **_k: "MemTotal: 1000 kB\nMemFree: 1 kB\nMemAvailable: 500 kB\n")
    assert h.memory_finding({"min_available_percent": 5})["healthy"] is True


def test_unknown_memory_cannot_recover(monkeypatch):
    h = load()
    monkeypatch.setattr(h.Path, "read_text", lambda *_a, **_k: "MemTotal: 1000 kB\n")
    assert h.memory_finding({"min_available_percent": 5})["healthy"] is False


def test_sustained_load_is_scaled_by_cpu_count(monkeypatch):
    h = load()
    monkeypatch.setattr(h.os, "getloadavg", lambda: (1, 2, 12), raising=False)
    monkeypatch.setattr(h.os, "cpu_count", lambda: 4)
    assert h.load_finding({"max_load_per_cpu": 2})["healthy"] is False


def response(body):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, *_): return body
    return Response()


def test_health_response_requires_expected_field(monkeypatch):
    h = load()
    monkeypatch.setattr(h.urllib.request, "urlopen", lambda *_a, **_k: response(b'{"running":false,"last_error":null}'))
    ok, _ = h.probe_http({"url": "http://example.invalid/status", "json_checks": {"scheduler_running": True}})
    assert ok is False


def test_idle_travel_job_is_healthy_if_scheduler_runs(monkeypatch):
    h = load()
    monkeypatch.setattr(h.urllib.request, "urlopen", lambda *_a, **_k: response(b'{"running":false,"scheduler_running":true,"last_error":null}'))
    ok, _ = h.probe_http({"url": "http://example.invalid/status", "json_checks": {"scheduler_running": True}, "error_field": "last_error"})
    assert ok is True


def test_error_content_not_forwarded(monkeypatch):
    h = load()
    monkeypatch.setattr(h.urllib.request, "urlopen", lambda *_a, **_k: response(b'{"last_error":"private-token-value"}'))
    ok, detail = h.probe_http({"url": "http://example.invalid/status", "error_field": "last_error"})
    assert ok is False
    assert "private-token" not in detail


def test_job_finishing_during_probe_pass_uses_current_clock(monkeypatch):
    h = load()
    clocks = iter(["1000.0 0.0", "1002.0 0.0"])
    monkeypatch.setattr(h.Path, "read_text", lambda *_a, **_k: next(clocks))
    monkeypatch.setattr(h, "unit_state", lambda _name: completed(ExecMainExitTimestampMonotonic="1001000000"))
    checks = h.collect({"jobs": [{"unit": "worker.service", "max_age_seconds": 600}]})
    assert checks[0]["healthy"] is True


def test_future_task_completion_cannot_recover():
    h = load()
    value = completed(ExecMainExitTimestampMonotonic="2000000000")
    assert h.job_finding({"unit": "worker.service"}, value, 1000)["healthy"] is False


def test_proc_uptime_rounding_does_not_make_a_finished_task_invalid():
    h = load()
    value = completed(ExecMainExitTimestampMonotonic="1000005000")
    assert h.job_finding({"unit": "worker.service"}, value, 1000)["healthy"] is True
