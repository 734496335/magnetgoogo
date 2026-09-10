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
    assert "EnvironmentFile=-/etc/magnet-alerts/alert.env" in service
    assert "media-alert.sh success" in service
    assert "/var/lib/magnet-alerts" in service
    assert "cleanup-media-container.sh publish" in service


def test_weekly_audit_runs_through_bash_even_if_archive_loses_executable_mode() -> None:
    service = (LINUX / "magnet-media-audit.service").read_text(encoding="utf-8")
    assert "ExecStart=/usr/bin/bash /opt/magnet-media/app/deploy/resource-index/linux/run-media-daily.sh audit" in service
    assert "cleanup-media-container.sh audit" in service


def test_container_cleanup_removes_only_matching_owner_lock() -> None:
    cleanup = (LINUX / "cleanup-media-container.sh").read_text(encoding="utf-8")
    assert "hostname" in cleanup
    assert 'SHORT_CID="${CID:0:12}"' in cleanup
    assert '"$OWNER" == "$SHORT_CID"' in cleanup
    assert 'rm -f "$LOCK"' in cleanup


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
    assert "media-alert.sh failure" in script
    assert "EnvironmentFile=-/etc/magnet-alerts/alert.env" in retry


def test_weekly_audit_is_separated_from_daily_window() -> None:
    daily = (LINUX / "magnet-media-daily.timer").read_text(encoding="utf-8")
    audit = (LINUX / "magnet-media-audit.timer").read_text(encoding="utf-8")
    assert "03:30:00 Asia/Shanghai" in daily
    assert "14:30:00 Asia/Shanghai" in audit
    assert "02:30:00 Asia/Shanghai" not in audit


def test_oracle_build_only_entrypoint_is_native_arm64_and_side_effect_bounded() -> None:
    script = (LINUX / "build-media-oracle-image.sh").read_text(encoding="utf-8")
    assert 'DEFAULT_APP_RELEASE=$(cd -- "$SCRIPT_DIR/../../.." && pwd)' in script
    assert 'APP_RELEASE=${APP_RELEASE:-$DEFAULT_APP_RELEASE}' in script
    assert 'MAGNET_MEDIA_IMAGE:-magnet-media-daily:oracle-shadow-$release_name' in script
    assert 'uname -m' in script
    assert '!= "aarch64"' in script
    assert "docker build" in script
    assert "docker image inspect" in script
    assert '"$image_arch" != "arm64"' in script
    assert '"$image_os" != "linux"' in script
    assert "MEDIA_ARM64_IMPORTS_PASS" in script
    assert "MEDIA_SSH_CLIENT_PASS" in script
    assert "systemctl" not in script
    assert "nginx" not in script.lower()
    assert "/etc/magnet-media" not in script
    assert "R2_UPLOAD_WORKER_TOKEN" not in script


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


def test_oracle_shadow_installer_uses_data_volume_and_never_touches_nginx_or_generates_keys() -> None:
    script = (LINUX / "install-media-oracle-shadow.sh").read_text(encoding="utf-8")
    assert "mountpoint -q /data" in script
    assert "systemd-escape -p --suffix=mount /var/lib/magnet-media" in script
    assert "What=$STATE_SOURCE" in script
    assert "Where=/var/lib/magnet-media" in script
    assert "ALLOW_R2_TOKEN" in script
    assert "shadow install refuses a production R2 upload token" in script
    assert "media-ed25519-private.pem" in script
    assert "init-media-signing-key" not in script
    assert "nginx" not in script.lower() or "nginx=untouched" in script
    assert "shadow install refuses an existing production media unit" in script
    assert "magnet-media-oracle-shadow.service" in script
    assert "production_units=not_installed" in script
    assert "install -m 0644 \"$APP_LINK/deploy/resource-index/linux/magnet-media-daily.service\"" not in script
    assert "install -m 0644 \"$APP_LINK/deploy/resource-index/linux/magnet-media-daily.timer\"" not in script
    assert "MAGNET_MEDIA_IMAGE=%s" in script
    assert 'MAGNET_MEDIA_IMAGE:-magnet-media-daily:oracle-shadow-$release_name' in script
    assert "image_arch" in script and '"arm64"' in script
    assert "MEDIA_ARM64_IMPORTS_PASS" in script
    assert "MEDIA_SSH_CLIENT_PASS" in script
    assert "docker build" not in script
    assert "run build-media-oracle-image.sh first" in script
    assert "systemd-analyze verify" in script
    assert "refusing to hide existing data" in script
    assert "ALIYUN_IDENTITY_SOURCE" in script
    assert "aliyun-known-hosts" in script


def test_oracle_shadow_acceptance_is_candidate_only_and_proves_public_pointer_immutability() -> None:
    script = (LINUX / "run-media-oracle-shadow-acceptance.sh").read_text(encoding="utf-8")
    assert "Oracle shadow acceptance refuses a production R2 upload token" in script
    assert "magnet-media-daily.timer" in script
    assert "Oracle shadow acceptance refuses installed production unit" in script
    assert "probe-aliyun-media-mirror.py" in script
    assert "probe-media-source-chain.py" in script
    assert '--candidate-limit "$SOURCE_PROBE_LIMIT"' in script
    assert 'run-media-daily.sh" candidate' in script
    assert 'run-media-daily.sh" publish' not in script
    assert "verify-media-oracle-candidate.py" in script
    assert 'cmp -s "$evidence/r2-before.json" "$evidence/r2-after.json"' in script
    assert 'cmp -s "$evidence/aliyun-before.json" "$evidence/aliyun-after.json"' in script
    assert 'cmp -s "$evidence/r2-after.json" "$evidence/aliyun-after.json"' in script
    assert "public pointers remained unchanged" in script
    assert "systemctl enable" not in script
    assert "systemctl start" not in script
    assert "R2_UPLOAD_WORKER_TOKEN" in script
    assert "export R2_UPLOAD_WORKER_TOKEN" not in script
    assert "printf 'R2_UPLOAD_WORKER_TOKEN" not in script


def test_oracle_shadow_service_can_only_run_candidate_mode() -> None:
    service = (LINUX / "magnet-media-oracle-shadow.service").read_text(encoding="utf-8")
    assert "run-media-daily.sh candidate" in service
    assert "run-media-daily.sh publish" not in service
    assert "EnvironmentFile=-/etc/magnet-media/runtime.env" in service
    assert "Requires=docker.service var-lib-magnet\\x2dmedia.mount" in service
    assert "OnFailure=" not in service
    assert "ReadWritePaths=/var/lib/magnet-media /run" in service


def test_oracle_example_config_uses_remote_aliyun_authority_and_data_mount_contract() -> None:
    config = json.loads((LINUX / "media-daily.oracle.example.json").read_text(encoding="utf-8"))
    assert config["state_root"] == "/var/lib/magnet-media"
    assert config["public_root"] == "/var/lib/magnet-media/public"
    assert config["aliyun_remote_root"] == "/var/lib/magnet-media/public"
    assert config["aliyun_ssh_target"] == "magnetmedia@47.103.155.154"
    assert config["aliyun_ssh_identity_file"].startswith("/etc/magnet-media/")
    assert config["aliyun_ssh_known_hosts_file"].startswith("/etc/magnet-media/")
    assert config["freshness_groups"]["series"]["min_fresh"] == 2


def test_aliyun_media_mirror_user_installer_is_least_privilege_and_side_effect_bounded() -> None:
    script = (LINUX / "install-aliyun-media-mirror-user.sh").read_text(encoding="utf-8")
    assert 'USER_NAME=${USER_NAME:-magnetmedia}' in script
    assert 'MEDIA_ROOT=${MEDIA_ROOT:-/var/lib/magnet-media/public}' in script
    assert 'HELPER_TARGET=${HELPER_TARGET:-/usr/local/libexec/magnet-media-remote-static-mirror.py}' in script
    assert 'from="%s",restrict %s' in script
    assert "passwd -l" in script
    assert "sudo|wheel" in script
    assert "setfacl -R -m" not in script
    assert 'setfacl -x "u:$USER_NAME" "$path"' in script
    assert 'setfacl -x "d:u:$USER_NAME" "$path"' in script
    assert "magnetmedia must not retain direct ACL access" in script
    assert 'find "$MEDIA_ROOT" -user "$USER_NAME"' in script
    assert 'chown root:root "$path"' in script
    assert 'install -o root -g root -m 0755 "$HELPER_SOURCE" "$HELPER_TARGET"' in script
    assert "/etc/sudoers.d/magnet-media-mirror" in script
    assert 'NOPASSWD: /usr/bin/python3 %s *' in script
    assert 'visudo -cf "$sudoers_file"' in script
    assert 'runuser -u "$USER_NAME" -- sudo -n python3' in script
    assert "sudo_access=fixed-root-owned-helper-only" in script
    assert "nginx=untouched" in script
    assert "systemd=untouched" in script
    assert "systemctl" not in script
    assert "nginx -t" not in script


def test_ssh_static_mirror_runtime_uses_fixed_remote_helper_with_scoped_sudo_and_no_helper_upload() -> None:
    source = (ROOT / "magnet/resource_index/publish/ssh_static_mirror.py").read_text(encoding="utf-8")
    assert '/usr/local/libexec/magnet-media-remote-static-mirror.py' in source
    assert "self.config.helper_path" not in source
    assert "[full_plan_path, self.config.helper_path]" not in source
    assert "[source, self.config.helper_path]" not in source
    assert 'parts = ["sudo", "-n", "python3", remote_helper, command, *args]' in source


def test_media_docker_image_contains_native_ssh_client_for_remote_mirror() -> None:
    dockerfile = (LINUX / "Dockerfile").read_text(encoding="utf-8")
    assert "openssh-client" in dockerfile
    assert "ca-certificates" in dockerfile


def test_legacy_aliyun_tools_target_current_production_authority_and_preserve_pointer() -> None:
    publish = (ROOT / "deploy/resource-index/publish-media-aliyun-data.ps1").read_text(encoding="utf-8")
    promote = (ROOT / "deploy/resource-index/promote-media-current.ps1").read_text(encoding="utf-8")
    assert '/var/lib/magnet-media/public' in publish
    assert '/var/lib/magnet-media/public' in promote
    assert '/var/www/magnetgoogo-site/media' not in publish
    assert '/var/www/magnetgoogo-site/media' not in promote
    assert "linux\\nginx-media-alias.conf" in publish
    assert "Aliyun current pointer preflight" in publish
    assert "--expected-current-status 200" in publish
    assert "--expected-current-sha256 $CurrentBeforeSha256" in publish
    assert "remote-static-mirror.py" in promote
    assert "preflight-current" in promote
    assert "promote-current" in promote
    assert promote.index("preflight-current") < promote.index("R2 current pointer upload") < promote.index("promote-current")


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
    by_source = {item["source_id"]: item for item in config["sources"]}
    assert by_source["bitba-series"]["count"] == 50
    assert by_source["mjf-series"]["count"] == 50
    assert config["freshness_groups"]["series"]["min_fresh"] == 2


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
