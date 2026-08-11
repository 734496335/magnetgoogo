from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LINUX = ROOT / "deploy" / "source-sync" / "linux"


def test_source_sync_requires_authority_and_independent_cdn_byte_match() -> None:
    script = (LINUX / "sync-source-packs.sh").read_text(encoding="utf-8")
    assert "https://magnetgoogo.com" in script
    assert "https://cdn.jsdelivr.net/gh/734496335/mg-data@main" in script
    assert "x-source-authority:" in script
    assert "github-raw" in script
    assert "for file in sources.enc.json sources-green.enc.json" in script
    assert 'cmp -s "$authority" "$cdn"' in script
    assert 'validate_pack "$authority"' in script
    assert 'validate_pack "$cdn"' in script


def test_source_sync_uses_atomic_target_replacement() -> None:
    script = (LINUX / "sync-source-packs.sh").read_text(encoding="utf-8")
    assert 'pending="$TARGET_ROOT/.$file.$$.new"' in script
    assert 'install -m 0644 "$authority" "$pending"' in script
    assert 'mv -f "$pending" "$target"' in script
    assert script.index('cmp -s "$authority" "$cdn"') < script.index('install -m 0644 "$authority" "$pending"')


def test_source_sync_timer_is_persistent_and_hourly() -> None:
    timer = (LINUX / "magnet-source-sync.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* *:17:00" in timer
    assert "RandomizedDelaySec=5m" in timer
    assert "Persistent=true" in timer
    assert "Unit=magnet-source-sync.service" in timer


def test_source_sync_service_has_minimal_write_scope() -> None:
    service = (LINUX / "magnet-source-sync.service").read_text(encoding="utf-8")
    assert "NoNewPrivileges=true" in service
    assert "ProtectHome=true" in service
    assert "ProtectSystem=strict" in service
    assert "ReadWritePaths=/var/www/magnetgoogo-site /var/tmp" in service
    assert "ExecStart=/usr/bin/bash /opt/magnet-source-sync/sync-source-packs.sh" in service


def test_source_sync_installer_enables_timer_before_initial_run() -> None:
    installer = (LINUX / "install-source-sync.sh").read_text(encoding="utf-8")
    enable = installer.index("systemctl enable --now magnet-source-sync.timer")
    start = installer.index("systemctl start magnet-source-sync.service")
    assert enable < start
