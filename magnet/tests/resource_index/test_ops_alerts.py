from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
ALERT_PATH = ROOT / "deploy" / "alerts" / "linux" / "magnet-alert.py"
MEDIA_LINUX = ROOT / "deploy" / "resource-index" / "linux"
SOURCE_LINUX = ROOT / "deploy" / "source-sync" / "linux"


def _load_alert_module():
    spec = importlib.util.spec_from_file_location("magnet_alert_test_module", ALERT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failure_threshold_deduplicates_until_single_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    alert = _load_alert_module()
    deliveries: list[tuple[str, str]] = []

    def deliver(title: str, message: str, dry_run: bool = False):
        deliveries.append((title, message))
        return True, "fake"

    monkeypatch.setattr(alert, "_deliver", deliver)
    state = tmp_path / "state.json"

    first = alert.record_failure(state, "source-sync", 2, 24, "P1", "failure", "one", 100, False)
    second = alert.record_failure(state, "source-sync", 2, 24, "P1", "failure", "two", 200, False)
    third = alert.record_failure(state, "source-sync", 2, 24, "P1", "failure", "three", 300, False)
    recovered = alert.record_success(state, "source-sync", "recovered", "ok", 400, False)
    repeated_success = alert.record_success(state, "source-sync", "recovered", "ok", 500, False)

    assert first == (False, "suppressed")
    assert second == (True, "fake")
    assert third == (False, "suppressed")
    assert recovered == (True, "fake")
    assert repeated_success == (False, "suppressed")
    assert [item[0] for item in deliveries] == ["failure", "recovered"]
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["source-sync"]["status"] == "success"
    assert saved["source-sync"]["consecutive_failures"] == 0
    assert saved["source-sync"]["alert_open"] is False


def test_delivery_disabled_is_fail_open_and_does_not_fake_notification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    alert = _load_alert_module()
    monkeypatch.setenv("MAGNET_ALERT_TRANSPORT", "disabled")
    state = tmp_path / "state.json"

    delivered, provider = alert.record_failure(state, "media-publish", 1, 24, "P0", "failure", "broken", 100, False)
    assert delivered is False
    assert provider == "disabled"
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["media-publish"]["status"] == "failed"
    assert saved["media-publish"]["alert_open"] is False


def test_cloudmonitor_uses_basic_auth_and_required_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    alert = _load_alert_module()
    captured: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"code":"200"}'

    def fake_urlopen(request, timeout=0):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("MAGNET_ALERT_CLOUDMONITOR_URL", "https://example.invalid/event/notify?token=secret")
    monkeypatch.setenv("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_ID", "ak-id")
    monkeypatch.setenv("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_SECRET", "ak-secret")
    monkeypatch.setenv("MAGNET_ALERT_CLOUDMONITOR_SECURITY_WORD", "SAFEWORD")
    monkeypatch.setattr(alert.urllib.request, "urlopen", fake_urlopen)

    assert alert._cloudmonitor_send("title", "message") == (True, "cloudmonitor")
    request = captured["request"]
    expected = base64.b64encode(b"ak-id:ak-secret").decode("ascii")
    assert request.get_header("Authorization") == "Basic " + expected
    payload = json.loads(request.data.decode("utf-8"))
    assert set(payload) == {"ruleName", "title", "message"}
    assert payload["title"] == "title"
    assert "message" in payload["message"]
    assert "SAFEWORD" in payload["message"]
    assert captured["timeout"] == 15


def test_cloudmonitor_security_word_mode_requires_no_access_key(monkeypatch: pytest.MonkeyPatch) -> None:
    alert = _load_alert_module()
    captured: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"code":"200"}'

    def fake_urlopen(request, timeout=0):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("MAGNET_ALERT_CLOUDMONITOR_URL", "https://example.invalid/event/notify?token=secret")
    monkeypatch.setenv("MAGNET_ALERT_CLOUDMONITOR_SECURITY_WORD", "SAFEWORD")
    monkeypatch.delenv("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_SECRET", raising=False)
    monkeypatch.setattr(alert.urllib.request, "urlopen", fake_urlopen)

    assert alert._cloudmonitor_send("title", "message") == (True, "cloudmonitor")
    request = captured["request"]
    assert request.get_header("Authorization") is None
    payload = json.loads(request.data.decode("utf-8"))
    assert "SAFEWORD" in payload["message"]
    assert captured["timeout"] == 15


def test_smtp_uses_authorization_code_and_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    alert = _load_alert_module()
    events: dict[str, object] = {}

    class Client:
        def __init__(self, host, port, timeout=0, context=None):
            events["connect"] = (host, port, timeout, context is not None)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def login(self, user, password):
            events["login"] = (user, password)

        def send_message(self, message):
            events["message"] = message

    monkeypatch.setenv("MAGNET_ALERT_SMTP_AUTH_CODE", "authorization-code")
    monkeypatch.setenv("MAGNET_ALERT_SMTP_USER", "sender@example.com")
    monkeypatch.setenv("MAGNET_ALERT_TO", "receiver@example.com")
    monkeypatch.setenv("MAGNET_ALERT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("MAGNET_ALERT_SMTP_PORT", "465")
    monkeypatch.setattr(alert.smtplib, "SMTP_SSL", Client)

    assert alert._smtp_send("subject", "body") == (True, "smtp")
    assert events["connect"][:3] == ("smtp.example.com", 465, 15)
    assert events["login"] == ("sender@example.com", "authorization-code")
    message = events["message"]
    assert message["To"] == "receiver@example.com"
    assert message["From"] == "sender@example.com"


def test_transport_selection_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    alert = _load_alert_module()
    calls: list[str] = []
    monkeypatch.setattr(alert, "_cloudmonitor_send", lambda *_args: (calls.append("cloud") or True, "cloudmonitor"))
    monkeypatch.setattr(alert, "_smtp_send", lambda *_args: (calls.append("smtp") or True, "smtp"))

    monkeypatch.setenv("MAGNET_ALERT_TRANSPORT", "disabled")
    assert alert._deliver("t", "m") == (False, "disabled")
    assert calls == []

    monkeypatch.setenv("MAGNET_ALERT_TRANSPORT", "smtp")
    assert alert._deliver("t", "m") == (True, "smtp")
    assert calls == ["smtp"]

    calls.clear()
    monkeypatch.setenv("MAGNET_ALERT_TRANSPORT", "cloudmonitor")
    assert alert._deliver("t", "m") == (True, "cloudmonitor")
    assert calls == ["cloud"]


def test_strict_test_mode_fails_when_transport_is_disabled(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ALERT_PATH),
            "test",
            "--key",
            "test",
            "--title",
            "test",
            "--message",
            "test",
            "--state-file",
            str(tmp_path / "state.json"),
            "--strict",
        ],
        env={**os.environ, "MAGNET_ALERT_TRANSPORT": "disabled"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "ALERT_TEST sent=false provider=disabled" in result.stdout


def test_media_alert_wires_only_second_failure_and_success_recovery() -> None:
    retry = (MEDIA_LINUX / "retry-media-daily.sh").read_text(encoding="utf-8")
    daily = (MEDIA_LINUX / "magnet-media-daily.service").read_text(encoding="utf-8")
    retry_unit = (MEDIA_LINUX / "magnet-media-retry.service").read_text(encoding="utf-8")
    helper = (MEDIA_LINUX / "media-alert.sh").read_text(encoding="utf-8")

    assert "systemctl start magnet-media-daily.service" in retry
    assert retry.index("systemctl start magnet-media-daily.service") < retry.index("media-alert.sh failure")
    assert "ExecStartPost=-/usr/bin/bash /opt/magnet-media/app/deploy/resource-index/linux/media-alert.sh success" in daily
    assert "EnvironmentFile=-/etc/magnet-alerts/alert.env" in daily
    assert "EnvironmentFile=-/etc/magnet-alerts/alert.env" in retry_unit
    assert '--title "影视自动发布二次失败"' in helper
    assert "/var/lib/magnet-alerts/media-publish.json" in helper
    assert "--key media-source-freshness" in helper
    assert "/var/lib/magnet-alerts/media-source-freshness.json" in helper
    assert '--title "影视 freshness 门禁持续降级"' in helper
    assert '--title "影视 freshness 门禁已恢复"' in helper
    assert "--key media-source-redundancy" in helper
    assert "/var/lib/magnet-alerts/media-source-redundancy.json" in helper
    assert '--title "影视资源冗余降级"' in helper
    assert '--title "影视资源冗余已恢复"' in helper
    assert "required_degraded_sources" in helper
    assert "failed_freshness_groups" in helper
    assert "DEGRADED_SOURCES" in helper
    assert "--repeat-hours 24" in helper


def test_source_sync_alert_wires_two_failures_and_two_low_expiry_observations() -> None:
    service = (SOURCE_LINUX / "magnet-source-sync.service").read_text(encoding="utf-8")
    alert_service = (SOURCE_LINUX / "magnet-source-sync-alert.service").read_text(encoding="utf-8")
    helper = (SOURCE_LINUX / "source-sync-alert.sh").read_text(encoding="utf-8")

    assert "OnFailure=magnet-source-sync-alert.service" in service
    assert "ExecStartPost=-/usr/bin/bash /opt/magnet-source-sync/source-sync-alert.sh success" in service
    assert "EnvironmentFile=-/etc/magnet-alerts/alert.env" in service
    assert "ReadWritePaths=/var/www/magnetgoogo-site /var/lib/magnet-alerts /var/tmp" in service
    assert "source-sync-alert.sh failure" in alert_service
    assert "--key source-sync" in helper and "--threshold 2" in helper
    assert "/var/lib/magnet-alerts/source-sync.json" in helper
    assert "--key source-expiry" in helper
    assert "/var/lib/magnet-alerts/source-expiry.json" in helper
    assert helper.count("--threshold 2") == 2
    assert helper.index("exit 0") < helper.index("--key source-expiry")
    assert "--repeat-hours 24" in helper
    assert "--repeat-hours 12" in helper


def test_alert_host_scripts_use_lf_line_endings() -> None:
    paths = [
        ROOT / "deploy" / "alerts" / "linux" / "magnet-alert.py",
        ROOT / "deploy" / "alerts" / "linux" / "install-alerts.sh",
        MEDIA_LINUX / "media-alert.sh",
        MEDIA_LINUX / "retry-media-daily.sh",
        SOURCE_LINUX / "source-sync-alert.sh",
        SOURCE_LINUX / "install-source-sync.sh",
    ]
    for path in paths:
        assert b"\r\n" not in path.read_bytes(), path


def test_alert_and_source_sync_deployment_files_use_lf_line_endings() -> None:
    paths = list((ROOT / "deploy" / "alerts" / "linux").iterdir()) + list(SOURCE_LINUX.iterdir())
    relevant = [
        path
        for path in paths
        if path.is_file() and (path.suffix in {".sh", ".py", ".service", ".timer", ".env"})
    ]
    assert relevant
    for path in relevant:
        assert b"\r\n" not in path.read_bytes(), path


def test_installers_keep_alert_component_present_without_overwriting_config() -> None:
    alert_installer = (ROOT / "deploy" / "alerts" / "linux" / "install-alerts.sh").read_text(encoding="utf-8")
    media_installer = (MEDIA_LINUX / "install-media-daily.sh").read_text(encoding="utf-8")
    source_installer = (SOURCE_LINUX / "install-source-sync.sh").read_text(encoding="utf-8")

    assert "compile(open(sys.argv[1]" in alert_installer
    assert "if [[ ! -f /etc/magnet-alerts/alert.env ]]" in alert_installer
    assert "chmod 0600 /etc/magnet-alerts/alert.env" in alert_installer
    assert "deploy/alerts/linux/install-alerts.sh" in media_installer
    assert "../../alerts/linux/install-alerts.sh" in source_installer


def test_alert_example_is_disabled_and_contains_no_real_recipient() -> None:
    example = (ROOT / "deploy" / "alerts" / "linux" / "alert.example.env").read_text(encoding="utf-8")
    assert "MAGNET_ALERT_TRANSPORT=disabled" in example
    assert "MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_ID=" in example
    assert "MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_SECRET=" in example
    assert "MAGNET_ALERT_SMTP_AUTH_CODE=" in example
    assert "734496335@qq.com" not in example
