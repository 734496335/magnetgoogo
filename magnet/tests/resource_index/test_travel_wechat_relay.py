import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "deploy" / "alerts" / "linux" / "travel-wechat-relay.py"
SPEC = importlib.util.spec_from_file_location("travel_wechat_relay", SOURCE)
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)
NOW = 1800000000
EVENT_ID = "travel-" + "a" * 32


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(relay.time, "time", lambda: NOW)


def write_event(tmp_path, **changes):
    event = {"version": 1, "event_id": EVENT_ID, "key": "travel-low-price",
             "title": "低价提醒", "message": "测试详情",
             "created_at_epoch": NOW, "expires_at_epoch": NOW + 1800}
    event.update(changes)
    path = tmp_path / (event["event_id"] + ".json")
    path.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
    return path


def result(returncode, stdout):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def test_failed_enqueue_retained_then_duplicate_ack_removed(tmp_path, monkeypatch):
    path = write_event(tmp_path)
    calls = []
    replies = [result(2, ""), result(0, "ALERT_ENQUEUE accepted=true provider=xtuis_queued_duplicate\n")]
    def fake_run(command, **kwargs):
        calls.append(command)
        return replies.pop(0)
    monkeypatch.setattr(relay.subprocess, "run", fake_run)
    first = relay.relay_once(tmp_path, "/fake/notifier.py", expected_uid=None)
    assert first["retry"] == 1 and path.exists()
    second = relay.relay_once(tmp_path, "/fake/notifier.py", expected_uid=None)
    assert second["accepted"] == 1 and not path.exists()
    for command in calls:
        assert command[command.index("--event-id") + 1] == EVENT_ID
        assert command[command.index("--ttl-seconds") + 1] == "1800"
        assert "--strict" in command and "--dry-run" not in command


@pytest.mark.parametrize("reply", [
    result(0, "ALERT_ENQUEUE accepted=true provider=dry_run\n"),
    result(0, "prefix ALERT_ENQUEUE accepted=true provider=xtuis_queued\n"),
    result(2, "ALERT_ENQUEUE accepted=true provider=xtuis_queued\n"),
])
def test_only_exact_success_ack_can_remove_file(tmp_path, monkeypatch, reply):
    path = write_event(tmp_path)
    monkeypatch.setattr(relay.subprocess, "run", lambda *a, **k: reply)
    counts = relay.relay_once(tmp_path, "/fake/notifier.py", expected_uid=None)
    assert counts["retry"] == 1 and path.exists()


def test_expired_message_removed_without_enqueue(tmp_path, monkeypatch):
    path = write_event(tmp_path, created_at_epoch=NOW - 1801, expires_at_epoch=NOW - 1)
    def forbidden(*args, **kwargs):
        raise AssertionError("Expired opportunity must not be enqueued")
    monkeypatch.setattr(relay.subprocess, "run", forbidden)
    counts = relay.relay_once(tmp_path, "/fake/notifier.py", expected_uid=None)
    assert counts["expired"] == 1 and not path.exists()


def test_utf8_combined_limit_is_enforced(tmp_path):
    path = write_event(tmp_path, title="测", message="字" * 15665 + "ab")
    assert relay.read_event(path, expected_uid=None)["title"] == "测"
    write_event(tmp_path, title="测", message="字" * 15665 + "abc")
    with pytest.raises(ValueError):
        relay.read_event(path, expected_uid=None)


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_version_must_be_integer_one(tmp_path, version):
    path = write_event(tmp_path, version=version)
    with pytest.raises(ValueError):
        relay.read_event(path, expected_uid=None)


def test_timeout_retains_message(tmp_path, monkeypatch):
    path = write_event(tmp_path)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("fake", 20)
    monkeypatch.setattr(relay.subprocess, "run", timeout)
    counts = relay.relay_once(tmp_path, "/fake/notifier.py", expected_uid=None)
    assert counts["retry"] == 1 and path.exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"), reason="FIFO behavior requires POSIX")
def test_fifo_is_rejected_without_waiting_for_writer(tmp_path):
    path = tmp_path / (EVENT_ID + ".json")
    os.mkfifo(str(path), 0o600)
    with pytest.raises(ValueError):
        relay.read_event(path, expected_uid=None)


def test_top_level_error_does_not_expose_exception_message(tmp_path, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE-SENTINEL")
    monkeypatch.setattr(relay, "relay_once", fail)
    assert relay.main(["--spool-dir", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err) == {"error_type": "RuntimeError"}
    assert "PRIVATE-SENTINEL" not in captured.out + captured.err
