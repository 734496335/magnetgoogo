"""Runtime lock, retention and disk guards for unattended media jobs."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import date, timedelta
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError


@dataclass(frozen=True)
class RetentionConfig:
    runs: int = 7
    status_history: int = 30
    releases: int = 3
    receipts: int = 30


def _boot_id() -> str:
    path = Path("/proc/sys/kernel/random/boot_id")
    try:
        value = path.read_text(encoding="ascii").strip()
    except OSError:
        return "unknown"
    return value or "unknown"


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _parse_lock(payload: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError:
        return values
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key and value:
            values[key] = value
    return values


def _stale_lock_reason(values: dict[str, str], current_boot_id: str) -> str | None:
    try:
        pid = int(values.get("pid") or "")
    except ValueError:
        return None
    recorded_boot_id = values.get("boot_id") or "unknown"
    if current_boot_id != "unknown" and recorded_boot_id != "unknown" and recorded_boot_id != current_boot_id:
        return "boot_changed"
    if not _process_alive(pid):
        return "dead_pid"
    return None


def _remove_unchanged_lock(path: Path, payload: bytes, inode: int) -> bool:
    try:
        current_stat = path.stat()
        current_payload = path.read_bytes()
    except FileNotFoundError:
        return True
    if current_stat.st_ino != inode or current_payload != payload:
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    return True


@contextmanager
def run_lock(path: Path, *, started_at: str) -> Iterator[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    boot_id = _boot_id()
    token = uuid.uuid4().hex
    recovered_reason: str | None = None
    descriptor: int | None = None
    acquired = False
    for _attempt in range(3):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            payload = (
                f"schema=media-daily-lock/1\n"
                f"pid={os.getpid()}\n"
                f"boot_id={boot_id}\n"
                f"token={token}\n"
                f"started_at={started_at}\n"
            ).encode("ascii")
            os.write(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            acquired = True
            break
        except FileExistsError as exc:
            try:
                stat = path.stat()
                existing = path.read_bytes()
            except FileNotFoundError:
                continue
            reason = _stale_lock_reason(_parse_lock(existing), boot_id)
            if reason is None:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "media daily run is already active",
                    {"lock_path": str(path)},
                ) from exc
            if not _remove_unchanged_lock(path, existing, stat.st_ino):
                continue
            recovered_reason = reason
    if not acquired:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media daily lock could not be acquired safely",
            {"lock_path": str(path)},
        )
    try:
        yield {
            "lock_path": str(path),
            "stale_lock_recovered": recovered_reason is not None,
            "stale_lock_reason": recovered_reason,
        }
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if acquired:
            try:
                values = _parse_lock(path.read_bytes())
            except FileNotFoundError:
                values = {}
            if values.get("token") == token:
                path.unlink(missing_ok=True)


def _remove_path(path: Path) -> int:
    if path.is_dir() and not path.is_symlink():
        size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        shutil.rmtree(path)
        return size
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return 0
    path.unlink(missing_ok=True)
    return size


def _newest(paths: list[Path], count: int) -> set[Path]:
    if count < 1:
        return set()
    ordered = sorted(paths, key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    return set(ordered[:count])


def prune_media_state(root: Path, config: RetentionConfig, *, protected_run_id: str | None = None) -> dict[str, Any]:
    deleted: list[str] = []
    deleted_bytes = 0

    runs_dir = root / "runs"
    run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()] if runs_dir.exists() else []
    keep_runs = _newest(run_dirs, config.runs)
    if protected_run_id:
        keep_runs.update(path for path in run_dirs if path.name == protected_run_id)
    for path in run_dirs:
        if path not in keep_runs:
            deleted_bytes += _remove_path(path)
            deleted.append(str(path))

    status_dir = root / "status"
    history = [
        path
        for path in status_dir.glob("*.json")
        if path.name not in {"latest.json", "state.json"}
    ] if status_dir.exists() else []
    keep_status = _newest(history, config.status_history)
    for path in history:
        if path not in keep_status:
            deleted_bytes += _remove_path(path)
            deleted.append(str(path))

    staging = root / "releases" / "staging"
    pointer_dir = staging / "pointers"
    pointers = list(pointer_dir.glob("*.json")) if pointer_dir.exists() else []
    keep_pointers = _newest(pointers, config.releases)
    retained_release_ids: set[str] = set()
    for path in keep_pointers:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        release_id = value.get("release_id")
        if isinstance(release_id, str) and release_id:
            retained_release_ids.add(release_id)
    for path in pointers:
        if path not in keep_pointers:
            deleted_bytes += _remove_path(path)
            deleted.append(str(path))

    release_dir = staging / "releases"
    releases = [path for path in release_dir.iterdir() if path.is_dir() and not path.name.startswith(".build-")] if release_dir.exists() else []
    keep_releases = _newest(releases, config.releases)
    keep_releases.update(path for path in releases if path.name in retained_release_ids)
    for path in releases:
        if path not in keep_releases:
            deleted_bytes += _remove_path(path)
            deleted.append(str(path))

    receipt_dir = root / "receipts"
    receipts = list(receipt_dir.glob("*.json")) if receipt_dir.exists() else []
    keep_receipts = _newest(receipts, config.receipts)
    for path in receipts:
        if path not in keep_receipts:
            deleted_bytes += _remove_path(path)
            deleted.append(str(path))

    return {
        "status": "pass",
        "deleted_count": len(deleted),
        "deleted_bytes": deleted_bytes,
        "deleted": deleted,
        "kept": {
            "runs": len(keep_runs),
            "status_history": len(keep_status),
            "pointers": len(keep_pointers),
            "releases": len(keep_releases),
            "receipts": len(keep_receipts),
        },
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def update_candidate_soak(
    path: Path,
    *,
    run_id: str,
    run_date: date,
    success: bool,
    summary: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous_corrupt = False
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
            previous_corrupt = True
    else:
        state = {}
    if not isinstance(state, dict) or state.get("schema_version") not in {None, "media-candidate-soak/1"}:
        state = {}
        previous_corrupt = True

    if success:
        raw_dates = state.get("successful_dates") or []
        successful_dates = {
            date.fromisoformat(value)
            for value in raw_dates
            if isinstance(value, str)
        }
        successful_dates.add(run_date)
        ordered = sorted(successful_dates)[-14:]
        consecutive = 0
        cursor = run_date
        values = set(ordered)
        while cursor in values:
            consecutive += 1
            cursor -= timedelta(days=1)
        state = {
            "schema_version": "media-candidate-soak/1",
            "successful_dates": [value.isoformat() for value in ordered],
            "consecutive_days": consecutive,
            "ready_for_promotion": consecutive >= 7,
            "last_status": "success",
            "last_run_id": run_id,
            "last_run_date": run_date.isoformat(),
            "last_summary": summary or {},
            "last_error": None,
            "previous_state_corrupt": previous_corrupt,
        }
    else:
        state = {
            "schema_version": "media-candidate-soak/1",
            "successful_dates": [],
            "consecutive_days": 0,
            "ready_for_promotion": False,
            "last_status": "failed",
            "last_run_id": run_id,
            "last_run_date": run_date.isoformat(),
            "last_summary": summary or {},
            "last_error": error or {},
            "previous_state_corrupt": previous_corrupt,
        }
    _atomic_json(path, state)
    return state


def assert_disk_capacity(root: Path, *, max_used_percent: float, min_free_bytes: int) -> dict[str, Any]:
    usage = shutil.disk_usage(root)
    used_percent = ((usage.total - usage.free) / usage.total) * 100 if usage.total else 100.0
    report = {
        "total_bytes": usage.total,
        "free_bytes": usage.free,
        "used_percent": round(used_percent, 2),
        "max_used_percent": max_used_percent,
        "min_free_bytes": min_free_bytes,
    }
    if used_percent >= max_used_percent or usage.free < min_free_bytes:
        raise ResourceIndexError(CONFIG_ERROR, "media daily disk guard rejected the run", report)
    return {"status": "pass", **report}
