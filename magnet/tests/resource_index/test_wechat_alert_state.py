import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "deploy" / "alerts" / "linux" / "magnet-alert.py"


@pytest.fixture
def alert(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("alert_state_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("MAGNET_ALERT_TRANSPORT", "xtuis")
    monkeypatch.setenv("MAGNET_ALERT_OUTBOX_DB", str(tmp_path / "outbox.sqlite3"))
    def forbid(*_args, **_kwargs):
        raise AssertionError("unexpected network")
    monkeypatch.setattr(module.outbox, "_http_json", forbid)
    return module


def test_network_unavailable_then_recovery_keeps_both_durable_events(alert, tmp_path):
    state = tmp_path / "health.json"
    first = alert.record_failure(state, "health", 1, 6, "P1", "failed", "detail", 100, False)
    recovered = alert.record_success(state, "health", "recovered", "detail", 200, False)
    assert first == (True, "xtuis_queued")
    assert recovered == (True, "xtuis_queued")
    assert alert.outbox.status(now=200)["counts"] == {"pending": 2}
    assert json.loads(state.read_text())["health"]["alert_open"] is False
    assert alert.record_success(state, "health", "recovered", "detail", 201, False) == (False, "suppressed")
    assert alert.outbox.status(now=201)["counts"] == {"pending": 2}


def test_failed_legacy_recovery_does_not_suppress_new_incident(alert, tmp_path, monkeypatch):
    events = []
    results = iter([(True, "fake"), (False, "network"), (True, "fake")])
    def deliver(title, *_args, **_kwargs):
        events.append(title)
        return next(results)
    monkeypatch.setattr(alert, "_deliver", deliver)
    state = tmp_path / "state.json"
    alert.record_failure(state, "health", 1, 24, "P1", "first", "x", 100, False)
    alert.record_success(state, "health", "recovery", "x", 200, False)
    assert alert.record_failure(state, "health", 1, 24, "P1", "new", "x", 300, False) == (True, "fake")
    assert events == ["first", "recovery", "new"]


def test_dry_run_does_not_create_state_lock_or_outbox(alert, tmp_path):
    state = tmp_path / "missing" / "state.json"
    alert.record_failure(state, "health", 1, 6, "P1", "failed", "x", 100, True)
    alert.record_success(state, "health", "recovery", "x", 200, True)
    assert list(tmp_path.iterdir()) == []


def test_mirror_cloud_success_never_skips_wechat_queue(alert, monkeypatch):
    calls = []
    monkeypatch.setenv("MAGNET_ALERT_TRANSPORT", "mirror")
    def enqueue(*_args, **_kwargs):
        calls.append("queue")
        return True, "xtuis_queued"
    def cloud(*_args):
        calls.append("cloud")
        return True, "cloudmonitor"
    monkeypatch.setattr(alert.outbox, "enqueue", enqueue)
    monkeypatch.setattr(alert, "_cloudmonitor_send", cloud)
    assert alert._deliver("title", "body") == (True, "xtuis_queued;cloudmonitor")
    assert calls == ["queue", "cloud"]


def test_mirror_cloud_success_does_not_hide_queue_failure(alert, monkeypatch):
    monkeypatch.setenv("MAGNET_ALERT_TRANSPORT", "mirror")
    monkeypatch.setattr(alert.outbox, "enqueue", lambda *_a, **_k: (False, "xtuis_queue_unavailable"))
    monkeypatch.setattr(alert, "_cloudmonitor_send", lambda *_: (True, "cloudmonitor"))
    assert alert._deliver("title", "body")[0] is False


def test_concurrent_state_updates_are_serialized(alert, tmp_path, monkeypatch):
    deliveries = []
    def deliver(*_args, **_kwargs):
        deliveries.append(1)
        return True, "fake"
    monkeypatch.setattr(alert, "_deliver", deliver)
    state = tmp_path / "state.json"
    def fail(_):
        return alert.record_failure(state, "health", 1, 24, "P1", "fault", "body", 100, False)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fail, range(8)))
    assert len(deliveries) == 1
    assert json.loads(state.read_text())["health"]["consecutive_failures"] == 8


@pytest.mark.parametrize("raw", [b"not-json", b"{}", b'{"message":"accepted"}', b'{"code":500}'])
def test_cloudmonitor_invalid_200_cannot_count_as_success(alert, monkeypatch, raw):
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self):
            return raw
    monkeypatch.setenv("MAGNET_ALERT_CLOUDMONITOR_URL", "https://example.invalid/endpoint")
    monkeypatch.delenv("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_SECRET", raising=False)
    monkeypatch.setattr(alert.urllib.request, "urlopen", lambda *_a, **_k: Response())
    assert alert._cloudmonitor_send("title", "body")[0] is False
