"""Atomic M2 publication of a verified release to one remote backend."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping

from magnet.resource_index.errors import (
    PUBLISH_CONFIG_ERROR,
    PUBLISH_LOCKED,
    PUBLISH_REMOTE_ERROR,
    ResourceIndexError,
)
from magnet.resource_index.publish.base import PublisherBackend, UploadOutcome, UploadRequest
from magnet.resource_index.release.builder import verify_media_release
from magnet.resource_index.release.protocol import canonical_json_bytes, sha256_file

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
POINTER_CANDIDATE_CACHE_CONTROL = "no-store"


@dataclass(frozen=True)
class MediaPublishConfig:
    release_dir: Path
    current_path: Path
    public_key_path: Path
    receipt_dir: Path
    max_workers: int = 8
    deep_verify: bool = True
    upload_pointer_candidate: bool = True


@dataclass(frozen=True)
class MediaPublishResult:
    status: str
    backend: str
    destination: str
    release_id: str
    pointer_revision: int
    object_count: int
    uploaded_count: int
    reused_count: int
    manifest_uploaded: bool
    pointer_uploaded: bool
    current_promoted: bool
    receipt_path: str


def _fail(error_code: str, message: str, **context: Any) -> None:
    raise ResourceIndexError(error_code, message, context)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(PUBLISH_CONFIG_ERROR, "failed to read publish JSON", path=str(path), error=str(exc))
    if not isinstance(value, dict):
        _fail(PUBLISH_CONFIG_ERROR, "publish JSON must be an object", path=str(path))
    return value


def _safe_local_path(root: Path, remote_path: str) -> Path:
    if not remote_path.startswith("/v1/") or "\\" in remote_path:
        _fail(PUBLISH_CONFIG_ERROR, "manifest path is not a safe /v1/ path", path=remote_path)
    parts = PurePosixPath(remote_path).parts
    if any(part in {"", ".", ".."} for part in parts):
        _fail(PUBLISH_CONFIG_ERROR, "manifest path contains an unsafe component", path=remote_path)
    candidate = (root / remote_path.lstrip("/")).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        _fail(PUBLISH_CONFIG_ERROR, "manifest path escapes the release directory", path=remote_path)
    if not candidate.is_file():
        _fail(PUBLISH_CONFIG_ERROR, "manifest path is missing locally", path=str(candidate))
    return candidate


def _content_type(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return "application/json; charset=utf-8"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _object_kind(key: str) -> str:
    if key.startswith("v1/objects/catalog/"):
        return "catalog"
    if key.startswith("v1/objects/detail/"):
        return "detail"
    if key.startswith("v1/objects/resources/"):
        return "resources"
    if key.startswith("v1/covers/"):
        return "cover"
    if "/releases/" in key and key.endswith("/manifest.json"):
        return "manifest"
    if key.startswith("staging/pointers/"):
        return "pointer-candidate"
    return "artifact"


def _request_from_ref(
    *,
    release_dir: Path,
    release_id: str,
    ref: Mapping[str, Any],
) -> UploadRequest:
    path_value = ref.get("path")
    hash_value = ref.get("hash")
    size_value = ref.get("size")
    if not isinstance(path_value, str) or not isinstance(hash_value, str) or type(size_value) is not int:
        _fail(PUBLISH_CONFIG_ERROR, "manifest object reference is incomplete", reference=dict(ref))
    source_path = _safe_local_path(release_dir, path_value)
    key = path_value.lstrip("/")
    return UploadRequest(
        key=key,
        source_path=source_path,
        sha256=hash_value,
        size=size_value,
        content_type=_content_type(source_path),
        cache_control=IMMUTABLE_CACHE_CONTROL,
        release_id=release_id,
        object_kind=_object_kind(key),
        immutable=True,
    )


def _artifact_request(
    *,
    key: str,
    source_path: Path,
    release_id: str,
    cache_control: str,
) -> UploadRequest:
    if not source_path.is_file():
        _fail(PUBLISH_CONFIG_ERROR, "publish artifact is missing", path=str(source_path))
    return UploadRequest(
        key=key,
        source_path=source_path,
        sha256=sha256_file(source_path),
        size=source_path.stat().st_size,
        content_type=_content_type(source_path),
        cache_control=cache_control,
        release_id=release_id,
        object_kind=_object_kind(key),
        immutable=True,
    )


def _receipt_name(
    backend: PublisherBackend,
    release_id: str,
    pointer_revision: int,
    attempt_id: str,
) -> str:
    destination_hash = hashlib.sha256(backend.destination.encode("utf-8")).hexdigest()[:10]
    return f"{backend.name}-{destination_hash}-{release_id}-r{pointer_revision}-{attempt_id}.json"


def _write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    temporary.write_bytes(canonical_json_bytes(receipt))
    try:
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _process_exists(pid: int) -> bool:
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


def _read_lock_pid(lock_path: Path) -> int | None:
    try:
        text = lock_path.read_text(encoding="ascii", errors="ignore")
    except OSError:
        return None
    match = re.search(r"(?:^|\n)pid=(\d+)(?:\n|$)", text)
    return int(match.group(1)) if match else None


def _lock_is_stale(lock_path: Path, *, malformed_grace_seconds: float = 300.0) -> bool:
    existing_pid = _read_lock_pid(lock_path)
    if existing_pid is not None:
        return not _process_exists(existing_pid)
    try:
        age_seconds = max(0.0, time.time() - lock_path.stat().st_mtime)
    except OSError:
        return False
    return age_seconds >= malformed_grace_seconds


@contextmanager
def _exclusive_publish_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    for _attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as exc:
            existing_pid = _read_lock_pid(lock_path)
            if not _lock_is_stale(lock_path):
                raise ResourceIndexError(
                    PUBLISH_LOCKED,
                    "another media publisher is already using this destination",
                    {"lock_path": str(lock_path), "pid": existing_pid},
                ) from exc
            try:
                lock_path.unlink()
            except FileNotFoundError:
                continue
            except OSError as unlink_error:
                raise ResourceIndexError(
                    PUBLISH_LOCKED,
                    "stale media publish lock could not be removed",
                    {"lock_path": str(lock_path)},
                ) from unlink_error
    if descriptor is None:
        _fail(PUBLISH_LOCKED, "media publish lock could not be acquired", lock_path=str(lock_path))
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _outcome_record(request: UploadRequest, outcome: UploadOutcome) -> dict[str, Any]:
    return {
        "key": request.key,
        "size": request.size,
        "sha256": request.sha256,
        "object_kind": request.object_kind,
        "uploaded": outcome.uploaded,
        "reused": outcome.reused,
        "deep_verified": outcome.deep_verified,
        "etag": outcome.object.etag,
    }


def publish_media_release(
    backend: PublisherBackend,
    config: MediaPublishConfig,
) -> MediaPublishResult:
    if config.max_workers < 1 or config.max_workers > 32:
        _fail(PUBLISH_CONFIG_ERROR, "max_workers must be between 1 and 32", value=config.max_workers)
    release_dir = config.release_dir.resolve()
    current_path = config.current_path.resolve()
    public_key_path = config.public_key_path.resolve()
    receipt_dir = config.receipt_dir.resolve()
    if current_path.name == "current.json" and current_path.parent.name == "v1":
        _fail(
            PUBLISH_CONFIG_ERROR,
            "M2 requires a staging pointer candidate, not a production v1/current.json",
            current_path=str(current_path),
        )

    local_report = verify_media_release(release_dir, public_key_path, current_path)
    current = _load_json(current_path)
    release_id = str(local_report["release_id"])
    pointer_revision = int(local_report["pointer_revision"])
    manifest_path_value = current.get("manifest_path")
    if not isinstance(manifest_path_value, str):
        _fail(PUBLISH_CONFIG_ERROR, "pointer candidate lacks manifest_path")
    manifest_path = _safe_local_path(release_dir, manifest_path_value)
    manifest = _load_json(manifest_path)
    refs = manifest.get("objects")
    if not isinstance(refs, list):
        _fail(PUBLISH_CONFIG_ERROR, "manifest objects must be a list")
    object_requests = [
        _request_from_ref(release_dir=release_dir, release_id=release_id, ref=ref)
        for ref in refs
        if isinstance(ref, Mapping)
    ]
    if len(object_requests) != len(refs):
        _fail(PUBLISH_CONFIG_ERROR, "manifest objects contains a non-object reference")
    manifest_request = _artifact_request(
        key=manifest_path_value.lstrip("/"),
        source_path=manifest_path,
        release_id=release_id,
        cache_control=IMMUTABLE_CACHE_CONTROL,
    )
    pointer_request = _artifact_request(
        key=f"staging/pointers/{current_path.name}",
        source_path=current_path,
        release_id=release_id,
        cache_control=POINTER_CANDIDATE_CACHE_CONTROL,
    )

    attempt_id = uuid.uuid4().hex[:12]
    receipt_path = receipt_dir / _receipt_name(
        backend,
        release_id,
        pointer_revision,
        attempt_id,
    )
    lock_hash = hashlib.sha256(backend.destination.encode("utf-8")).hexdigest()[:16]
    lock_path = receipt_dir / f".publish-{backend.name}-{lock_hash}.lock"
    started_at = _utc_now()
    records: list[dict[str, Any]] = []
    manifest_uploaded = False
    pointer_uploaded = False

    def write_failure(exc: Exception, stage: str, request: UploadRequest | None = None) -> None:
        if isinstance(exc, ResourceIndexError):
            error = {
                "error_code": exc.error_code,
                "message": exc.message,
                "context": exc.context,
            }
        else:
            error = {
                "error_code": PUBLISH_REMOTE_ERROR,
                "message": str(exc),
                "context": {},
            }
        _write_receipt(
            receipt_path,
            {
                "schema_version": "media-publish-receipt/1",
                "status": "failed",
                "started_at": started_at,
                "finished_at": _utc_now(),
                "backend": backend.name,
                "destination": backend.destination,
                "release_id": release_id,
                "pointer_revision": pointer_revision,
                "stage": stage,
                "failed_key": request.key if request else None,
                "error": error,
                "objects": sorted(records, key=lambda row: row["key"]),
                "manifest_uploaded": manifest_uploaded,
                "pointer_uploaded": pointer_uploaded,
                "current_promoted": False,
            },
        )

    with _exclusive_publish_lock(lock_path):
        try:
            backend.healthcheck()
        except Exception as exc:
            write_failure(exc, "healthcheck")
            raise

        failed_request: UploadRequest | None = None
        try:
            if config.max_workers == 1:
                for request in object_requests:
                    failed_request = request
                    outcome = backend.upload(request, deep_verify=config.deep_verify)
                    records.append(_outcome_record(request, outcome))
            else:
                futures: dict[Future[UploadOutcome], UploadRequest] = {}
                first_failure: tuple[UploadRequest, Exception] | None = None
                with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
                    for request in object_requests:
                        futures[executor.submit(backend.upload, request, deep_verify=config.deep_verify)] = request
                    for future in as_completed(futures):
                        request = futures[future]
                        try:
                            outcome = future.result()
                        except Exception as exc:
                            if first_failure is None:
                                first_failure = (request, exc)
                            continue
                        records.append(_outcome_record(request, outcome))
                if first_failure is not None:
                    failed_request, failure = first_failure
                    raise failure

            failed_request = manifest_request
            manifest_outcome = backend.upload(manifest_request, deep_verify=config.deep_verify)
            manifest_uploaded = manifest_outcome.uploaded or manifest_outcome.reused
            records.append(_outcome_record(manifest_request, manifest_outcome))

            if config.upload_pointer_candidate:
                failed_request = pointer_request
                pointer_outcome = backend.upload(pointer_request, deep_verify=config.deep_verify)
                pointer_uploaded = pointer_outcome.uploaded or pointer_outcome.reused
                records.append(_outcome_record(pointer_request, pointer_outcome))
        except Exception as exc:
            write_failure(exc, "upload", failed_request)
            raise

        uploaded_count = sum(1 for row in records if row["uploaded"])
        reused_count = sum(1 for row in records if row["reused"])
        receipt = {
            "schema_version": "media-publish-receipt/1",
            "status": "success",
            "started_at": started_at,
            "finished_at": _utc_now(),
            "backend": backend.name,
            "destination": backend.destination,
            "release_id": release_id,
            "pointer_revision": pointer_revision,
            "manifest_sha256": local_report["manifest_sha256"],
            "local_verified_objects": local_report["verified_objects"],
            "deep_verify": config.deep_verify,
            "max_workers": config.max_workers,
            "objects": sorted(records, key=lambda row: row["key"]),
            "object_count": len(object_requests),
            "uploaded_count": uploaded_count,
            "reused_count": reused_count,
            "manifest_uploaded": manifest_uploaded,
            "pointer_uploaded": pointer_uploaded,
            "current_promoted": False,
        }
        _write_receipt(receipt_path, receipt)
        return MediaPublishResult(
            status="success",
            backend=backend.name,
            destination=backend.destination,
            release_id=release_id,
            pointer_revision=pointer_revision,
            object_count=len(object_requests),
            uploaded_count=uploaded_count,
            reused_count=reused_count,
            manifest_uploaded=manifest_uploaded,
            pointer_uploaded=pointer_uploaded,
            current_promoted=False,
            receipt_path=str(receipt_path),
        )
