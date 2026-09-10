from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LINUX = ROOT / "deploy" / "resource-index" / "linux"


def test_oracle_compute_config_contains_no_production_publish_credentials() -> None:
    config = json.loads((LINUX / "media-daily.oracle-compute.example.json").read_text(encoding="utf-8"))
    assert config["private_key_path"].endswith("not-used-on-oracle-compute.pem")
    assert config["public_key_path"] == "/etc/magnet-media/media-production-ed25519-public.pem"
    assert "aliyun_ssh_target" not in config
    assert config["r2_public_base"] == "https://media.magnetgoogo.com"
    assert config["aliyun_public_base"] == "https://cn.magnetgoogo.com/media"


def test_oracle_compute_service_and_timer_are_compute_only() -> None:
    service = (LINUX / "magnet-media-oracle-compute.service").read_text(encoding="utf-8")
    timer = (LINUX / "magnet-media-oracle-compute.timer").read_text(encoding="utf-8")
    runner = (LINUX / "run-media-daily.sh").read_text(encoding="utf-8")
    assert "run-media-daily.sh compute" in service
    assert "run-media-daily.sh publish" not in service
    assert "RequiresMountsFor=/var/lib/magnet-media" in service
    assert "var-lib-magnet\\x2dmedia.mount" not in service
    assert "OnCalendar=*-*-* 03:00:00 Asia/Shanghai" in timer
    assert "compute) args+=(--no-publish --compute-only)" in runner


def test_oracle_outbox_is_loopback_only() -> None:
    service = (LINUX / "magnet-media-oracle-outbox.service").read_text(encoding="utf-8")
    assert "--bind 127.0.0.1" in service
    assert "RequiresMountsFor=/var/lib/magnet-media" in service
    assert "var-lib-magnet\\x2dmedia.mount" not in service
    assert "18766" in service
    assert "/var/lib/magnet-media/outbox" in service


def test_oracle_compute_installer_has_no_secret_or_production_timer_path() -> None:
    script = (LINUX / "install-media-oracle-compute.sh").read_text(encoding="utf-8")
    assert "media-production-ed25519-public.pem" in script
    assert "media-ed25519-private.pem" not in script
    assert "Oracle compute has no R2 production token" in script
    assert "Oracle compute must not contain an R2 production token" in script
    assert "production_secrets=none" in script
    assert 'chown -R root:root "$STATE_SOURCE"' in script
    assert "magnet-media-daily.timer" in script
    assert "refuses production Aliyun-style unit" in script
    assert "ENABLE_COMPUTE_TIMER" in script


def test_finalizer_wrapper_streams_handoff_then_runs_containerized_finalizer() -> None:
    fetcher = (ROOT / "deploy/resource-index/fetch-media-compute-handoff.py").read_text(encoding="utf-8")
    runner = (LINUX / "run-media-compute-finalizer.sh").read_text(encoding="utf-8")
    assert "_stream_package" in fetcher
    assert "response.read(1024 * 1024)" in fetcher
    assert "package_bytes = _get" not in fetcher
    assert "/usr/bin/python3.11" in runner
    assert "--entrypoint python" in runner
    assert "--publish" in runner
    assert "MAGNET_MEDIA_FINALIZER_MODE" in runner


def test_finalizer_timer_retries_but_same_service_cannot_overlap() -> None:
    timer = (LINUX / "magnet-media-compute-finalizer.timer").read_text(encoding="utf-8")
    service = (LINUX / "magnet-media-compute-finalizer.service").read_text(encoding="utf-8")
    for hour in ("04:30:00", "05:30:00", "06:30:00", "07:30:00"):
        assert hour in timer
    assert "Unit=magnet-media-compute-finalizer.service" in timer
    assert "Type=oneshot" in service
    assert "Requires=docker.service magnet-media-oracle-outbox-tunnel.service" in service


def test_aliyun_finalizer_installer_preserves_old_crawler_timer_until_cutover() -> None:
    script = (LINUX / "install-media-aliyun-finalizer.sh").read_text(encoding="utf-8")
    assert "old Aliyun crawler timer must remain enabled" in script
    assert "systemctl is-enabled --quiet magnet-media-daily.timer" in script
    assert "systemctl disable --now magnet-media-daily.timer" not in script
    assert "FINALIZER_MODE=${FINALIZER_MODE:-candidate}" in script
    assert '[[ "$FINALIZER_MODE" == "publish" ]]' in script
    assert "finalizer timer may only be enabled in publish mode" in script


def test_aliyun_finalizer_build_is_native_amd64_and_build_only() -> None:
    script = (LINUX / "build-media-aliyun-finalizer-image.sh").read_text(encoding="utf-8")
    assert '[[ "$(uname -m)" == "x86_64" ]]' in script
    assert '"linux/amd64"' in script
    assert "MEDIA_FINALIZER_IMPORTS_PASS" in script
    assert "systemctl" not in script
    assert "nginx" not in script.lower()


def test_outbox_tunnel_reuses_existing_pinned_oracle_identity_without_new_secret() -> None:
    unit = (LINUX / "magnet-media-oracle-outbox-tunnel.service").read_text(encoding="utf-8")
    assert "/home/admin/.ssh/travel-oracle-tunnel" in unit
    assert "StrictHostKeyChecking=yes" in unit
    assert "ExitOnForwardFailure=yes" in unit
    assert "127.0.0.1:18766:127.0.0.1:18766" in unit
    assert "-R " not in unit
