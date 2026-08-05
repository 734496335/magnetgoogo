from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[3]
LINUX = ROOT / "deploy" / "resource-index" / "linux"


def test_linux_deployment_files_use_lf_line_endings() -> None:
    suffixes = {".sh", ".service", ".timer", ".conf", ".json", ".pem"}
    paths = [
        path
        for path in LINUX.iterdir()
        if path.name == "Dockerfile" or path.suffix in suffixes
    ]
    assert paths
    for path in paths:
        assert b"\r\n" not in path.read_bytes(), path


def test_daily_runner_defaults_to_bounded_candidate_mode() -> None:
    script = (LINUX / "run-media-daily.sh").read_text(encoding="utf-8")
    assert 'MODE="${1:-${MAGNET_MEDIA_MODE:-candidate}}"' in script
    assert 'MAGNET_MEDIA_MEMORY:-768m' in script
    assert 'MAGNET_MEDIA_MEMORY_SWAP:-1280m' in script
    assert 'MAGNET_MEDIA_CPUS:-1.0' in script
    assert '--pids-limit "$PIDS_LIMIT"' in script
    assert 'CONTAINER_NAME="magnet-media-${MODE}"' in script
    assert '--name "$CONTAINER_NAME"' in script
    assert '--cidfile "$CID_FILE"' in script
    assert "docker container inspect" in script
    assert "docker rm -f" in script
    assert "--cap-drop ALL" in script
    assert 'audit) args+=(--skip-crawl --skip-ratings --no-publish)' in script
    assert "--memory 1500m" not in script
    assert "--cpus 1.75" not in script


def test_daily_service_runs_production_publish_mode_through_bash() -> None:
    service = (LINUX / "magnet-media-daily.service").read_text(encoding="utf-8")
    assert "ExecStart=/usr/bin/bash /opt/magnet-media/app/deploy/resource-index/linux/run-media-daily.sh publish" in service
    assert "run-media-daily.sh candidate" not in service
    assert "daily media production publish" in service
    assert "OnFailure=magnet-media-retry.service" in service
    assert "cleanup-media-container.sh publish" in service


def test_weekly_audit_runs_through_bash_even_if_archive_loses_executable_mode() -> None:
    service = (LINUX / "magnet-media-audit.service").read_text(encoding="utf-8")
    assert "ExecStart=/usr/bin/bash /opt/magnet-media/app/deploy/resource-index/linux/run-media-daily.sh audit" in service
    assert "cleanup-media-container.sh audit" in service


def test_failed_daily_publish_has_one_delayed_retry() -> None:
    retry = (LINUX / "magnet-media-retry.service").read_text(encoding="utf-8")
    script = (LINUX / "retry-media-daily.sh").read_text(encoding="utf-8")
    assert "retry-media-daily.sh" in retry
    assert "OnFailure=" not in retry
    assert "TimeoutStartSec=4h45m" in retry
    assert 'MAGNET_MEDIA_RETRY_DELAY:-30m' in script
    assert "latest-publish.json" in script
    assert "SUCCESS_EPOCH >= FAILED_EPOCH" in script
    assert "systemctl start magnet-media-daily.service" in script


def test_weekly_audit_is_separated_from_daily_window() -> None:
    daily = (LINUX / "magnet-media-daily.timer").read_text(encoding="utf-8")
    audit = (LINUX / "magnet-media-audit.timer").read_text(encoding="utf-8")
    assert "03:30:00 Asia/Shanghai" in daily
    assert "14:30:00 Asia/Shanghai" in audit
    assert "02:30:00 Asia/Shanghai" not in audit


def test_installer_seeds_media_before_nginx_cutover_and_keeps_timers_opt_in() -> None:
    script = (LINUX / "install-media-daily.sh").read_text(encoding="utf-8")
    prepare = script.index("prepare-nginx-media-root.py")
    include = script.index("install-nginx-media-include.py")
    assert prepare < include
    assert 'ENABLE_TIMERS=${ENABLE_TIMERS:-0}' in script
    assert 'if [[ "$ENABLE_TIMERS" == "1" ]]' in script
    assert "rollback_nginx" in script
    assert "init-media-signing-key" in script
    assert "media-production-ed25519-public.pem" in script
    assert "MAGNET_MEDIA_PYTHON_IMAGE" in script
    assert "MAGNET_MEDIA_PIP_INDEX_URL" in script
    assert '--build-arg "PYTHON_IMAGE=$PYTHON_IMAGE"' in script
    assert '--build-arg "PIP_INDEX_URL=$PIP_INDEX_URL"' in script
    assert "install-media-candidate-seed.py" in script
    assert "MEDIA_SEED_ROOT" in script
    assert "cleanup-media-container.sh" in script
    assert "retry-media-daily.sh" in script
    assert "magnet-media-retry.service" in script
    assert script.count("--entrypoint python") >= 3
    assert 'python3 "$APP_ROOT/deploy/resource-index' not in script
    assert 'mode=automatic-production-publish' in script
    assert '-v "$MEDIA_SEED_ROOT:/seed:ro"' in script
    assert '-v "$LIVE_MEDIA_ROOT:/live-media:ro"' in script
    assert "-v /etc/nginx:/etc/nginx" in script


def test_auto_publish_worker_uses_the_domestic_reachable_custom_domain() -> None:
    config = json.loads(
        (ROOT / "deploy/resource-index/r2-auto-worker/wrangler.jsonc").read_text(encoding="utf-8")
    )
    assert config["vars"]["PUBLISH_MODE"] == "production-auto"
    assert config["routes"] == [
        {
            "pattern": "media-auto-publisher.magnetgoogo.com",
            "custom_domain": True,
        }
    ]


def test_example_config_has_retention_and_disk_guards() -> None:
    config = json.loads((LINUX / "media-daily.example.json").read_text(encoding="utf-8"))
    assert config["min_app_version"] == "0.2.3"
    assert config["previous_public_key_path"] == "/etc/magnet-media/media-production-ed25519-public.pem"
    assert config["retention_runs"] == 7
    assert config["retention_status_history"] == 30
    assert config["retention_releases"] == 3
    assert config["disk_max_used_percent"] == 80
    assert config["disk_min_free_bytes"] == 2 * 1024 * 1024 * 1024
    assert config["max_workers"] == 4
    assert config["rating_lookup_limit_per_feed"] == 40
    assert config["source_fallback_max_age_hours"] == 168


def test_production_public_key_matches_the_formal_v023_client() -> None:
    pem = (LINUX / "media-production-ed25519-public.pem").read_bytes()
    public_key = serialization.load_pem_public_key(pem)
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    protocol = (ROOT / "magnetgoogo-app" / "src" / "core" / "mediaReleaseProtocol.ts").read_text(encoding="utf-8")
    match = re.search(r"MEDIA_PUBLIC_KEY_BASE64 = '([^']+)'", protocol)
    assert match
    assert base64.b64encode(raw).decode("ascii") == match.group(1)


def test_nginx_alias_reads_only_the_validated_state_root() -> None:
    snippet = (LINUX / "nginx-media-alias.conf").read_text(encoding="utf-8")
    assert "/var/lib/magnet-media/public/v1/current.json" in snippet
    assert "/var/www/magnetgoogo-site/media" not in snippet
    assert "location ^~ /media/staging/" in snippet
    assert "deny all;" in snippet
