from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("deploy/resource-index/verify-static-mirror.py")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "payload"
    path = root / "v1" / "objects" / "detail" / "example.json"
    path.parent.mkdir(parents=True)
    payload = b'{"ok":true}'
    path.write_bytes(payload)
    plan = {
        "schema_version": "media-publish-plan/1",
        "release_id": "release-test",
        "pointer_revision": 1,
        "total_file_count": 1,
        "files": [
            {
                "key": "v1/objects/detail/example.json",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
                "object_kind": "detail",
            }
        ],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return root, plan_path


def test_static_mirror_verifier_promotes_and_reuses(tmp_path: Path) -> None:
    root, plan = _fixture(tmp_path)
    target = tmp_path / "target"

    first = _run("--root", str(root), "--plan", str(plan), "--exact", "--promote-to", str(target))
    second = _run("--root", str(root), "--plan", str(plan), "--exact", "--promote-to", str(target))

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert json.loads(first.stdout)["promotion"] == {"copied": 1, "reused": 0}
    assert json.loads(second.stdout)["promotion"] == {"copied": 0, "reused": 1}


def test_static_mirror_verifier_blocks_target_conflict(tmp_path: Path) -> None:
    root, plan = _fixture(tmp_path)
    target = tmp_path / "target"
    conflict = target / "v1" / "objects" / "detail" / "example.json"
    conflict.parent.mkdir(parents=True)
    conflict.write_bytes(b"different")

    result = _run("--root", str(root), "--plan", str(plan), "--promote-to", str(target))

    assert result.returncode == 1
    assert "immutable mirror target conflicts" in result.stdout
    assert conflict.read_bytes() == b"different"


def test_static_mirror_verifier_rejects_current_pointer(tmp_path: Path) -> None:
    root = tmp_path / "payload"
    current = root / "v1" / "current.json"
    current.parent.mkdir(parents=True)
    current.write_bytes(b"{}")
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "schema_version": "media-publish-plan/1",
                "total_file_count": 1,
                "files": [
                    {
                        "key": "v1/current.json",
                        "sha256": hashlib.sha256(b"{}").hexdigest(),
                        "size": 2,
                        "object_kind": "pointer",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run("--root", str(root), "--plan", str(plan))

    assert result.returncode == 1
    assert "current.json is forbidden" in result.stdout


def test_static_mirror_verifier_exact_mode_rejects_extra_file(tmp_path: Path) -> None:
    root, plan = _fixture(tmp_path)
    extra = root / "unexpected.txt"
    extra.write_text("extra", encoding="utf-8")

    result = _run("--root", str(root), "--plan", str(plan), "--exact")

    assert result.returncode == 1
    assert "file set is not exact" in result.stdout
