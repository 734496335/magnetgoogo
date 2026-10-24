import json
import os
from pathlib import Path

import pytest

from travel_monitor import notify, wechat_spool
from travel_monitor.notify import Notifier


def test_disabled_wechat_preserves_legacy_result(monkeypatch):
    monkeypatch.delenv("MAGNET_WECHAT_SPOOL_DIR", raising=False)
    notifier = Notifier(())
    calls = []
    monkeypatch.setattr(notifier, "_send_legacy_message", lambda *a: calls.append(a) or True)
    assert notifier.send_message("title", "body") is True
    assert calls == [("title", "body")]


def test_queue_success_is_independent_of_legacy_failure(monkeypatch):
    notifier = Notifier(())
    calls = []
    monkeypatch.setattr(notify, "enqueue_wechat", lambda *a: True)
    monkeypatch.setattr(notifier, "_send_legacy_message", lambda *a: calls.append(a) or False)
    assert notifier.send_message("title", "body") is True
    assert len(calls) == 1


def test_queue_failure_cannot_be_hidden_by_legacy_success(monkeypatch):
    notifier = Notifier(())
    monkeypatch.setattr(notify, "enqueue_wechat", lambda *a: False)
    monkeypatch.setattr(notifier, "_send_legacy_message", lambda *a: True)
    assert notifier.send_message("title", "body") is False


def test_legacy_exception_does_not_undo_durable_wechat(monkeypatch, caplog):
    notifier = Notifier(())
    monkeypatch.setattr(notify, "enqueue_wechat", lambda *a: True)
    def fail(*a):
        raise RuntimeError("PRIVATE-SENTINEL")
    monkeypatch.setattr(notifier, "_send_legacy_message", fail)
    assert notifier.send_message("title", "body") is True
    assert "PRIVATE-SENTINEL" not in caplog.text


def test_atomic_spool_and_expiry(tmp_path):
    folder = tmp_path / "spool"
    assert wechat_spool.enqueue_wechat("标题", "测试正文", env={"MAGNET_WECHAT_SPOOL_DIR": str(folder)}, now=100)
    paths = list(folder.glob("*.json"))
    assert len(paths) == 1
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["event_id"] == paths[0].stem
    assert payload["expires_at_epoch"] == 1900
    assert payload["key"] == "travel-low-price"
    assert list(folder.glob("*.tmp")) == []
    if os.name == "posix":
        assert paths[0].stat().st_mode & 0o777 == 0o600


def test_failed_atomic_rename_never_claims_success(tmp_path, monkeypatch):
    def fail(*a):
        raise OSError("PRIVATE")
    monkeypatch.setattr(wechat_spool.os, "replace", fail)
    assert wechat_spool.enqueue_wechat("title", "body", env={"MAGNET_WECHAT_SPOOL_DIR": str(tmp_path)}) is False
    assert list(tmp_path.iterdir()) == []


def test_combined_utf8_limit(tmp_path):
    env = {"MAGNET_WECHAT_SPOOL_DIR": str(tmp_path)}
    assert wechat_spool.enqueue_wechat("测", "字" * 15665 + "ab", env=env) is True
    assert wechat_spool.enqueue_wechat("测", "字" * 15665 + "abc", env=env) is False
