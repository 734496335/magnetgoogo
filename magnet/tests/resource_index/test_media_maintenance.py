from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline import media_maintenance
from magnet.resource_index.pipeline.media_maintenance import (
    RetentionConfig,
    assert_disk_capacity,
    prune_media_state,
    run_lock,
    update_candidate_soak,
)


def _lock(path: Path, *, pid: int, boot_id: str, token: str = "old") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"schema=media-daily-lock/1\npid={pid}\nboot_id={boot_id}\ntoken={token}\nstarted_at=old\n",
        encoding="ascii",
    )


def test_run_lock_keeps_live_owner_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "daily.lock"
    monkeypatch.setattr(media_maintenance, "_boot_id", lambda: "boot-a")
    _lock(lock, pid=os.getpid(), boot_id="boot-a")
    before = lock.read_bytes()

    with pytest.raises(ResourceIndexError, match="already active"):
        with run_lock(lock, started_at="2026-07-31T00:00:00Z"):
            pass

    assert lock.read_bytes() == before


def test_run_lock_recovers_dead_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "daily.lock"
    monkeypatch.setattr(media_maintenance, "_boot_id", lambda: "boot-a")
    monkeypatch.setattr(media_maintenance, "_process_alive", lambda _pid: False)
    _lock(lock, pid=987654, boot_id="boot-a")

    with run_lock(lock, started_at="2026-07-31T00:00:00Z") as state:
        assert state["stale_lock_recovered"] is True
        assert state["stale_lock_reason"] == "dead_pid"
        assert lock.exists()

    assert not lock.exists()


def test_run_lock_recovers_expired_heartbeat_even_when_pid_looks_alive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = tmp_path / "daily.lock"
    monkeypatch.setattr(media_maintenance, "_boot_id", lambda: "boot-a")
    monkeypatch.setattr(media_maintenance, "_process_alive", lambda _pid: True)
    _lock(lock, pid=1, boot_id="boot-a")
    expired = time.time() - media_maintenance._LOCK_STALE_SECONDS - 10
    os.utime(lock, (expired, expired))

    with run_lock(lock, started_at="2026-08-05T00:00:00Z") as state:
        assert state["stale_lock_recovered"] is True
        assert state["stale_lock_reason"] == "heartbeat_expired"


def test_run_lock_heartbeat_refreshes_lock_mtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = tmp_path / "daily.lock"
    monkeypatch.setattr(media_maintenance, "_LOCK_HEARTBEAT_SECONDS", 0.01)

    with run_lock(lock, started_at="2026-08-05T00:00:00Z"):
        before = lock.stat().st_mtime_ns
        time.sleep(0.05)
        after = lock.stat().st_mtime_ns
        assert after > before
        values = media_maintenance._parse_lock(lock.read_bytes())
        assert values["hostname"]


def test_run_lock_recovers_previous_boot_even_when_pid_is_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = tmp_path / "daily.lock"
    monkeypatch.setattr(media_maintenance, "_boot_id", lambda: "boot-new")
    monkeypatch.setattr(media_maintenance, "_process_alive", lambda _pid: True)
    _lock(lock, pid=os.getpid(), boot_id="boot-old")

    with run_lock(lock, started_at="2026-07-31T00:00:00Z") as state:
        assert state["stale_lock_reason"] == "boot_changed"


def _touch(path: Path, index: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(index), encoding="utf-8")
    stamp = 1_700_000_000 + index
    os.utime(path, (stamp, stamp))


def test_prune_media_state_retains_bounded_history_and_pointer_releases(tmp_path: Path) -> None:
    root = tmp_path / "state"
    for index in range(10):
        run = root / "runs" / f"run-{index:02d}"
        _touch(run / "payload.bin", index)
        os.utime(run, (1_700_000_000 + index, 1_700_000_000 + index))
    for index in range(8):
        _touch(root / "status" / f"status-{index:02d}.json", index)
    _touch(root / "status" / "latest.json", 99)
    _touch(root / "status" / "latest-publish.json", 98)
    _touch(root / "status" / "latest-audit.json", 97)
    _touch(root / "status" / "candidate-soak.json", 96)
    _touch(root / "status" / "state.json", 99)
    for index in range(5):
        release_id = f"release-{index}"
        release = root / "releases" / "staging" / "releases" / release_id
        _touch(release / "v1" / "payload", index)
        os.utime(release, (1_700_000_000 + index, 1_700_000_000 + index))
        pointer = root / "releases" / "staging" / "pointers" / f"pointer-{index}.json"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(json.dumps({"release_id": release_id}), encoding="utf-8")
        os.utime(pointer, (1_700_000_000 + index, 1_700_000_000 + index))
    for index in range(8):
        _touch(root / "receipts" / f"receipt-{index}.json", index)

    report = prune_media_state(
        root,
        RetentionConfig(runs=3, status_history=4, releases=2, receipts=3),
        protected_run_id="run-00",
    )

    assert report["status"] == "pass"
    assert sorted(path.name for path in (root / "runs").iterdir()) == ["run-00", "run-07", "run-08", "run-09"]
    control_names = {
        "latest.json",
        "latest-publish.json",
        "latest-audit.json",
        "candidate-soak.json",
        "state.json",
    }
    assert control_names.issubset({path.name for path in (root / "status").glob("*.json")})
    assert len([path for path in (root / "status").glob("*.json") if path.name not in control_names]) == 4
    assert sorted(path.name for path in (root / "releases" / "staging" / "pointers").glob("*.json")) == [
        "pointer-3.json",
        "pointer-4.json",
    ]
    assert sorted(path.name for path in (root / "releases" / "staging" / "releases").iterdir()) == [
        "release-3",
        "release-4",
    ]
    assert len(list((root / "receipts").glob("*.json"))) == 3


def test_prune_media_state_always_retains_durable_current_pointer_and_release(tmp_path: Path) -> None:
    root = tmp_path / "state"
    pointer_dir = root / "releases" / "staging" / "pointers"
    release_dir = root / "releases" / "staging" / "releases"
    for revision in (10, 11, 12):
        release_id = f"release-{revision}"
        release = release_dir / release_id
        _touch(release / "v1" / "payload", revision)
        os.utime(release, (1_700_000_000 + revision, 1_700_000_000 + revision))
        pointer = pointer_dir / f"pointer-{revision}.json"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(
            json.dumps({"pointer_revision": revision, "release_id": release_id}),
            encoding="utf-8",
        )
        os.utime(pointer, (1_700_000_000 + revision, 1_700_000_000 + revision))
    current_pointer = pointer_dir / "pointer-10.json"
    current_release = release_dir / "release-10"
    os.utime(current_pointer, (1_600_000_000, 1_600_000_000))
    os.utime(current_release, (1_600_000_000, 1_600_000_000))
    _write_state = root / "status" / "state.json"
    _write_state.parent.mkdir(parents=True, exist_ok=True)
    _write_state.write_text(
        json.dumps({"current_revision": 10, "release_id": "release-10"}),
        encoding="utf-8",
    )

    prune_media_state(root, RetentionConfig(runs=1, status_history=1, releases=1, receipts=1))

    assert current_pointer.exists()
    assert current_release.exists()
    assert (pointer_dir / "pointer-12.json").exists()


def test_candidate_soak_requires_seven_distinct_consecutive_days(tmp_path: Path) -> None:
    path = tmp_path / "candidate-soak.json"
    start = date(2026, 8, 1)
    for offset in range(7):
        state = update_candidate_soak(
            path,
            run_id=f"run-{offset}",
            run_date=start + timedelta(days=offset),
            success=True,
            summary={"resource_count": 3500},
        )
    assert state["consecutive_days"] == 7
    assert state["ready_for_promotion"] is True

    duplicate = update_candidate_soak(
        path,
        run_id="run-duplicate",
        run_date=start + timedelta(days=6),
        success=True,
    )
    assert duplicate["consecutive_days"] == 7


def test_candidate_soak_failure_resets_streak(tmp_path: Path) -> None:
    path = tmp_path / "candidate-soak.json"
    update_candidate_soak(path, run_id="run-1", run_date=date(2026, 8, 1), success=True)
    failed = update_candidate_soak(
        path,
        run_id="run-2",
        run_date=date(2026, 8, 2),
        success=False,
        error={"error_code": "CONFIG_ERROR"},
    )
    assert failed["consecutive_days"] == 0
    assert failed["successful_dates"] == []
    assert failed["ready_for_promotion"] is False
    assert failed["last_error"]["error_code"] == "CONFIG_ERROR"


def test_candidate_soak_corrupt_state_resets_conservatively(tmp_path: Path) -> None:
    path = tmp_path / "candidate-soak.json"
    path.write_text("not-json", encoding="utf-8")
    state = update_candidate_soak(
        path,
        run_id="run-1",
        run_date=date(2026, 8, 1),
        success=True,
    )
    assert state["consecutive_days"] == 1
    assert state["previous_state_corrupt"] is True


def test_disk_guard_rejects_high_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        media_maintenance.shutil,
        "disk_usage",
        lambda _path: media_maintenance.shutil._ntuple_diskusage(1000, 850, 150),
    )
    with pytest.raises(ResourceIndexError, match="disk guard") as captured:
        assert_disk_capacity(tmp_path, max_used_percent=80, min_free_bytes=100)
    assert captured.value.context["used_percent"] == 85.0


def test_disk_guard_passes_with_headroom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        media_maintenance.shutil,
        "disk_usage",
        lambda _path: media_maintenance.shutil._ntuple_diskusage(1000, 400, 600),
    )
    report = assert_disk_capacity(tmp_path, max_used_percent=80, min_free_bytes=500)
    assert report["status"] == "pass"
    assert report["used_percent"] == 40.0
