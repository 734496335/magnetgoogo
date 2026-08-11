from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


ROOT = Path(__file__).resolve().parents[3]
LINUX = ROOT / "deploy" / "source-sync" / "linux"


def _write_pack(path: Path, key: bytes, *, issued_at: datetime, expires_at: datetime, rules: int, green: int) -> None:
    payload_rules = [
        {"id": f"r{i}", "health": {"status": "green" if i < green else "yellow"}}
        for i in range(rules)
    ]
    envelope = {
        "schema_version": 1,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "min_app_version": "0.1.10",
        "payload": {"rulesets": [{"rules": payload_rules}]},
    }
    compressed = gzip.compress(json.dumps(envelope, separators=(",", ":")).encode("utf-8"), compresslevel=9)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(compressed) + padder.finalize()
    iv = os.urandom(16)
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    ciphertext_text = base64.b64encode(ciphertext).decode("ascii")
    signature = hmac.new(key, ciphertext_text.encode("utf-8"), hashlib.sha256).hexdigest()
    path.write_text(
        json.dumps({"iv": iv.hex(), "ct": ciphertext_text, "sig": signature, "gz": True}),
        encoding="utf-8",
    )


def _run_verifier(tmp_path: Path, *, expires_delta_hours: float = 72, pair_skew_minutes: int = 0) -> subprocess.CompletedProcess[str]:
    key = bytes.fromhex("11" * 32)
    now = datetime.now(timezone.utc)
    issued = now + timedelta(hours=expires_delta_hours - 72)
    full = tmp_path / "sources.enc.json"
    green = tmp_path / "sources-green.enc.json"
    _write_pack(full, key, issued_at=issued, expires_at=now + timedelta(hours=expires_delta_hours), rules=357, green=148)
    _write_pack(
        green,
        key,
        issued_at=issued + timedelta(minutes=pair_skew_minutes),
        expires_at=now + timedelta(hours=expires_delta_hours, minutes=pair_skew_minutes),
        rules=150,
        green=148,
    )
    return subprocess.run(
        [
            sys.executable,
            str(LINUX / "verify-source-packs.py"),
            "--full",
            str(full),
            "--green",
            str(green),
            "--min-remaining-hours",
            "12",
        ],
        env={**os.environ, "SOURCE_ENCRYPTION_KEY_HEX": key.hex()},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_source_sync_requires_authority_and_github_api_byte_match() -> None:
    script = (LINUX / "sync-source-packs.sh").read_text(encoding="utf-8")
    assert "https://magnetgoogo.com" in script
    assert "https://api.github.com/repos/734496335/mg-data/contents" in script
    assert "x-source-authority:" in script
    assert "github-raw" in script
    assert 'FILE="sources.enc.json"' in script
    assert "sources-green.enc.json" not in script
    assert 'cmp -s "$authority" "$github_api"' in script
    assert "GitHub API contents decode failed" in script
    assert 'encoded="".join(d["content"].split())' in script
    assert "base64.b64decode(encoded,validate=True)" in script


def test_source_sync_treats_jsdelivr_as_optional_observation_not_publish_gate() -> None:
    script = (LINUX / "sync-source-packs.sh").read_text(encoding="utf-8")
    assert "https://cdn.jsdelivr.net/gh/734496335/mg-data@main" in script
    assert "optional jsDelivr evidence converged" in script
    assert "warning: jsDelivr is lagging" in script
    verifier_index = script.index('"$PYTHON_BIN" "$VERIFIER"')
    cdn_index = script.index('cdn="$TMP_ROOT/$FILE.cdn"')
    assert verifier_index < cdn_index


def test_source_sync_verifies_crypto_and_freshness_before_install() -> None:
    script = (LINUX / "sync-source-packs.sh").read_text(encoding="utf-8")
    verifier = '"$PYTHON_BIN" "$VERIFIER"'
    install = 'install -m 0644 "$authority" "$pending"'
    assert verifier in script
    assert script.index(verifier) < script.index(install)
    assert "MAGNET_SOURCE_MIN_REMAINING_HOURS" in script
    assert "--green" not in script


def test_source_sync_stages_only_full_pack_and_validates_before_replace() -> None:
    script = (LINUX / "sync-source-packs.sh").read_text(encoding="utf-8")
    assert 'pending="$TARGET_ROOT/.$FILE.$$.new"' in script
    assert 'install -m 0644 "$authority" "$pending"' in script
    assert '"$VERIFIER" --full "$pending"' in script
    assert 'mv -f "$pending" "$target"' in script
    assert "sources-green.enc.json" not in script


def test_source_sync_timer_is_persistent_and_hourly() -> None:
    timer = (LINUX / "magnet-source-sync.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* *:17:00" in timer
    assert "RandomizedDelaySec=5m" in timer
    assert "Persistent=true" in timer
    assert "Unit=magnet-source-sync.service" in timer


def test_source_sync_service_has_minimal_write_scope_and_root_only_key_file() -> None:
    service = (LINUX / "magnet-source-sync.service").read_text(encoding="utf-8")
    assert "NoNewPrivileges=true" in service
    assert "ProtectHome=true" in service
    assert "ProtectSystem=strict" in service
    assert "ReadWritePaths=/var/www/magnetgoogo-site /var/tmp" in service
    assert "EnvironmentFile=/etc/magnet-source-sync/source-sync.env" in service
    assert "ExecStart=/usr/bin/bash /opt/magnet-source-sync/sync-source-packs.sh" in service


def test_source_sync_installer_requires_key_and_installs_verifier_before_enabling_timer() -> None:
    installer = (LINUX / "install-source-sync.sh").read_text(encoding="utf-8")
    assert "missing /etc/magnet-source-sync/source-sync.env" in installer
    assert 'chmod 0600 /etc/magnet-source-sync/source-sync.env' in installer
    verifier = installer.index('install -m 0755 "$SOURCE_DIR/verify-source-packs.py"')
    enable = installer.index("systemctl enable --now magnet-source-sync.timer")
    start = installer.index("systemctl start magnet-source-sync.service")
    assert verifier < enable < start


def test_source_pack_verifier_accepts_fresh_signed_pair(tmp_path: Path) -> None:
    result = _run_verifier(tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "pass"
    assert report["full"]["rules"] == 357
    assert report["full"]["green"] == 148
    assert report["green"]["rules"] == 150


def test_source_pack_verifier_rejects_near_expiry_pair(tmp_path: Path) -> None:
    result = _run_verifier(tmp_path, expires_delta_hours=6)
    assert result.returncode != 0
    assert "validity hours remain" in result.stderr


def test_source_pack_verifier_rejects_full_green_generation_skew(tmp_path: Path) -> None:
    result = _run_verifier(tmp_path, pair_skew_minutes=1)
    assert result.returncode != 0
    assert "disagree on issued_at" in result.stderr
