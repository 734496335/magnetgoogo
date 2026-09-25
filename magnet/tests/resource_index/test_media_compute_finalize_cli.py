from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from magnet.resource_index.errors import ResourceIndexError, VALIDATION_ERROR


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "deploy" / "resource-index" / "finalize-media-compute.py"


def _module():
    spec = importlib.util.spec_from_file_location("finalize_media_compute_cli", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_finalize_cli_writes_success_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    config = tmp_path / "config.json"
    package = tmp_path / "handoff.tar"
    status = tmp_path / "status" / "latest.json"
    config.write_text("{}", encoding="utf-8")
    package.write_bytes(b"handoff")
    monkeypatch.setattr(module, "load_media_daily_config", lambda _path: object())
    monkeypatch.setattr(module, "finalize_compute_handoff", lambda *_args, **_kwargs: {"status": "success", "current_revision": 52})
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--config", str(config), "--package", str(package), "--publish", "--status-file", str(status)],
    )

    assert module.main() == 0
    payload = json.loads(status.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["mode"] == "publish"
    assert payload["package"] == package.name
    assert payload["result"]["current_revision"] == 52


def test_finalize_cli_writes_structured_failure_before_reraising(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    config = tmp_path / "config.json"
    package = tmp_path / "handoff.tar"
    status = tmp_path / "status" / "latest.json"
    config.write_text("{}", encoding="utf-8")
    package.write_bytes(b"handoff")
    monkeypatch.setattr(module, "load_media_daily_config", lambda _path: object())

    def fail(*_args, **_kwargs):
        raise ResourceIndexError(VALIDATION_ERROR, "regression gate failed", {"regressions": {"series": {"current": 1}}})

    monkeypatch.setattr(module, "finalize_compute_handoff", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--config", str(config), "--package", str(package), "--status-file", str(status)],
    )

    with pytest.raises(ResourceIndexError):
        module.main()
    payload = json.loads(status.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["mode"] == "candidate"
    assert payload["error"]["error_code"] == VALIDATION_ERROR
    assert payload["error"]["context"]["regressions"]["series"]["current"] == 1
