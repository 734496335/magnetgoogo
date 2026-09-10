from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "deploy" / "resource-index" / "fetch-media-compute-handoff.py"
SPEC = importlib.util.spec_from_file_location("fetch_media_compute_handoff", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
fetcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetcher)


def _pointer(**overrides: object) -> bytes:
    value: dict[str, object] = {
        "schema_version": "media-compute-handoff-pointer/1",
        "package": "packages/20260910T045933Z-fb9b9e38.tar",
        "package_sha256": "a" * 64,
        "package_size": 123,
        "run_id": "20260910T045933Z-fb9b9e38",
    }
    value.update(overrides)
    return json.dumps(value).encode("utf-8")


def test_load_pointer_accepts_expected_package_contract() -> None:
    pointer = fetcher._load_pointer(_pointer())
    assert pointer["package"] == "packages/20260910T045933Z-fb9b9e38.tar"
    assert pointer["package_size"] == 123


@pytest.mark.parametrize(
    "package",
    [
        "../secret.tar",
        "packages/../secret.tar",
        "packages/a b.tar",
        "packages/a.tar.gz",
        "/packages/a.tar",
    ],
)
def test_load_pointer_rejects_unsafe_package_path(package: str) -> None:
    with pytest.raises(RuntimeError, match="package path is unsafe"):
        fetcher._load_pointer(_pointer(package=package))


def test_load_pointer_rejects_bad_sha_and_size() -> None:
    with pytest.raises(RuntimeError, match="SHA-256 is invalid"):
        fetcher._load_pointer(_pointer(package_sha256="bad"))
    with pytest.raises(RuntimeError, match="package size is invalid"):
        fetcher._load_pointer(_pointer(package_size=0))


def test_ssh_command_is_argv_only_and_pins_host_verification(tmp_path: Path) -> None:
    identity = tmp_path / "id"
    known_hosts = tmp_path / "known_hosts"
    identity.write_text("x", encoding="utf-8")
    known_hosts.write_text("x", encoding="utf-8")
    command = fetcher._ssh_command(
        "ubuntu@161.153.78.129",
        identity,
        known_hosts,
        "/var/lib/magnet-media/outbox/current.json",
    )
    assert command[0] == "/usr/bin/ssh"
    assert "StrictHostKeyChecking=yes" in command
    assert f"UserKnownHostsFile={known_hosts}" in command
    assert command[-1] == "cat -- /var/lib/magnet-media/outbox/current.json"


def test_ssh_command_rejects_remote_path_escape(tmp_path: Path) -> None:
    identity = tmp_path / "id"
    known_hosts = tmp_path / "known_hosts"
    identity.write_text("x", encoding="utf-8")
    known_hosts.write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="remote path is invalid"):
        fetcher._ssh_command("ubuntu@161.153.78.129", identity, known_hosts, "/etc/passwd")


def test_validate_ssh_inputs_requires_absolute_existing_files(tmp_path: Path) -> None:
    identity = tmp_path / "id"
    known_hosts = tmp_path / "known_hosts"
    identity.write_text("x", encoding="utf-8")
    known_hosts.write_text("x", encoding="utf-8")
    fetcher._validate_ssh_inputs("ubuntu@161.153.78.129", identity, known_hosts)
    with pytest.raises(RuntimeError, match="target is invalid"):
        fetcher._validate_ssh_inputs("ubuntu@host;touch-x", identity, known_hosts)
