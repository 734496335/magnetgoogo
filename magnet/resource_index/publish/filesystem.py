"""Local filesystem mirror backend used by the Alibaba Cloud media host."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path, PurePosixPath

from magnet.resource_index.errors import (
    PUBLISH_CONFIG_ERROR,
    PUBLISH_CONFLICT,
    PUBLISH_VERIFICATION_FAILED,
    ResourceIndexError,
)
from magnet.resource_index.publish.base import PublishedObject, PublisherBackend, UploadOutcome, UploadRequest
from magnet.resource_index.release.protocol import sha256_file


def _safe_key(key: str) -> PurePosixPath:
    value = key.strip()
    if not value or value.startswith("/") or "\\" in value:
        raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "filesystem object key is unsafe", {"key": key})
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "filesystem object key is unsafe", {"key": key})
    return path


class FilesystemPublisherBackend(PublisherBackend):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    @property
    def name(self) -> str:
        return "filesystem-mirror"

    @property
    def destination(self) -> str:
        return str(self.root)

    def _path(self, key: str) -> Path:
        relative = _safe_key(key)
        path = self.root.joinpath(*relative.parts).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "filesystem key escapes mirror root", {"key": key}) from exc
        return path

    def healthcheck(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        probe = self.root / f".media-health-{os.getpid()}-{uuid.uuid4().hex}"
        try:
            probe.write_bytes(b"ok")
        finally:
            probe.unlink(missing_ok=True)

    def head(self, key: str) -> PublishedObject | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return PublishedObject(
            key=key,
            size=path.stat().st_size,
            sha256=sha256_file(path),
            etag=None,
            metadata=None,
        )

    def verify(self, request: UploadRequest, *, deep: bool = True) -> PublishedObject:
        published = self.head(request.key)
        if published is None:
            raise ResourceIndexError(
                PUBLISH_VERIFICATION_FAILED,
                "filesystem mirror object is missing",
                {"key": request.key},
            )
        if published.size != request.size or published.sha256 != request.sha256:
            raise ResourceIndexError(
                PUBLISH_VERIFICATION_FAILED,
                "filesystem mirror object does not match expected bytes",
                {
                    "key": request.key,
                    "expected_size": request.size,
                    "actual_size": published.size,
                    "expected_sha256": request.sha256,
                    "actual_sha256": published.sha256,
                },
            )
        return published

    def upload(self, request: UploadRequest, *, deep_verify: bool = True) -> UploadOutcome:
        target = self._path(request.key)
        existing = self.head(request.key)
        if existing is not None:
            if existing.size != request.size or existing.sha256 != request.sha256:
                raise ResourceIndexError(
                    PUBLISH_CONFLICT,
                    "immutable filesystem object conflicts with existing bytes",
                    {"key": request.key},
                )
            return UploadOutcome(existing, uploaded=False, reused=True, deep_verified=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        shutil.copyfile(request.source_path, temporary)
        try:
            if temporary.stat().st_size != request.size or sha256_file(temporary) != request.sha256:
                raise ResourceIndexError(
                    PUBLISH_VERIFICATION_FAILED,
                    "filesystem staging copy failed verification",
                    {"key": request.key},
                )
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        published = self.verify(request, deep=deep_verify)
        return UploadOutcome(published, uploaded=True, reused=False, deep_verified=True)

    def promote_current(self, current_path: str | Path) -> PublishedObject:
        source = Path(current_path)
        if not source.is_file():
            raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "current pointer candidate is missing", {"path": str(source)})
        target = self._path("v1/current.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".current.{uuid.uuid4().hex}.tmp"
        shutil.copyfile(source, temporary)
        try:
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return PublishedObject(
            key="v1/current.json",
            size=target.stat().st_size,
            sha256=sha256_file(target),
            etag=None,
            metadata=None,
        )
