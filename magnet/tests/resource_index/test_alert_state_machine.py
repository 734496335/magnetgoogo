from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ALERT_PATH = ROOT / "deploy" / "alerts" / "linux" / "magnet-alert.py"
SPEC = importlib.util.spec_from_file_location("magnet_alert", ALERT_PATH)
assert SPEC is not None and SPEC.loader is not None
magnet_alert = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(magnet_alert)


def test_failure_threshold_and_repeat_suppression(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state.json"
    sent: list[str] = []

    def deliver(title: str, message: str, dry_run: bool = False):
        sent.append(title)
        return True, "test"

    monkeypatch.setattr(magnet_alert, "_deliver", deliver)

    for now in (1000, 1100):
        delivered, _ = magnet_alert.record_failure(
            state, "source-sync", 3, 24, "P1", "title", "message", now, False
        )
        assert delivered is False
    delivered, _ = magnet_alert.record_failure(
        state, "source-sync", 3, 24, "P1", "title", "message", 1200, False
    )
    assert delivered is True
    assert sent == ["title"]

    delivered, _ = magnet_alert.record_failure(
        state, "source-sync", 3, 24, "P1", "title", "message", 1300, False
    )
    assert delivered is False
    assert sent == ["title"]

    delivered, _ = magnet_alert.record_failure(
        state, "source-sync", 3, 24, "P1", "title", "message", 1200 + 24 * 3600, False
    )
    assert delivered is True
    assert sent == ["title", "title"]


def test_recovery_only_sends_after_open_alert(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state.json"
    sent: list[str] = []

    def deliver(title: str, message: str, dry_run: bool = False):
        sent.append(title)
        return True, "test"

    monkeypatch.setattr(magnet_alert, "_deliver", deliver)

    delivered, _ = magnet_alert.record_success(state, "media-publish", "recover", "ok", 1000, False)
    assert delivered is False
    assert sent == []

    delivered, _ = magnet_alert.record_failure(
        state, "media-publish", 1, 24, "P0", "failed", "bad", 1100, False
    )
    assert delivered is True
    delivered, _ = magnet_alert.record_success(state, "media-publish", "recover", "ok", 1200, False)
    assert delivered is True
    assert sent == ["failed", "recover"]

    delivered, _ = magnet_alert.record_success(state, "media-publish", "recover", "ok", 1300, False)
    assert delivered is False
    assert sent == ["failed", "recover"]


def test_delivery_falls_back_to_smtp_when_cloudmonitor_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(magnet_alert, "_cloudmonitor_send", lambda *_args, **_kwargs: (False, "cloud_down"))
    monkeypatch.setattr(magnet_alert, "_smtp_send", lambda *_args, **_kwargs: (True, "smtp"))
    assert magnet_alert._deliver("title", "message") == (True, "smtp")


def test_no_provider_does_not_open_alert_state(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state.json"
    monkeypatch.setattr(
        magnet_alert,
        "_deliver",
        lambda *_args, **_kwargs: (False, "cloudmonitor_not_configured;smtp_not_configured"),
    )
    delivered, _ = magnet_alert.record_failure(
        state, "source-sync", 1, 24, "P1", "title", "message", 1000, False
    )
    assert delivered is False
    stored = magnet_alert._load_state(state)["source-sync"]
    assert stored["alert_open"] is False
    assert stored["consecutive_failures"] == 1
