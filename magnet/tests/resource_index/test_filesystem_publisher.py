from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from magnet.resource_index.errors import PUBLISH_CONFLICT, ResourceIndexError
from magnet.resource_index.publish.base import UploadRequest
from magnet.resource_index.publish.filesystem import FilesystemPublisherBackend


def _request(tmp_path: Path, *, payload: bytes = b"payload") -> UploadRequest:
    source = tmp_path / "source.json"
    source.write_bytes(payload)
    return UploadRequest(
        key="v1/objects/detail/example.json",
        source_path=source,
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
        content_type="application/json; charset=utf-8",
        cache_control="public, max-age=31536000, immutable",
        release_id="release-test",
        object_kind="detail",
    )


def test_filesystem_publisher_uploads_and_reuses_immutable_object(tmp_path: Path) -> None:
    backend = FilesystemPublisherBackend(tmp_path / "mirror")
    backend.healthcheck()
    request = _request(tmp_path)

    first = backend.upload(request)
    second = backend.upload(request)

    assert first.uploaded is True
    assert second.reused is True
    assert backend.verify(request).sha256 == request.sha256


def test_filesystem_publisher_rejects_immutable_conflict(tmp_path: Path) -> None:
    backend = FilesystemPublisherBackend(tmp_path / "mirror")
    request = _request(tmp_path)
    backend.upload(request)
    (tmp_path / "mirror" / request.key).write_bytes(b"different")

    with pytest.raises(ResourceIndexError) as exc:
        backend.upload(request)
    assert exc.value.error_code == PUBLISH_CONFLICT


def test_filesystem_publisher_promotes_current_atomically(tmp_path: Path) -> None:
    backend = FilesystemPublisherBackend(tmp_path / "mirror")
    current = tmp_path / "current.json"
    current.write_bytes(b'{"pointer_revision":7}')

    published = backend.promote_current(current)

    assert published.sha256 == hashlib.sha256(current.read_bytes()).hexdigest()
    assert (tmp_path / "mirror" / "v1" / "current.json").read_bytes() == current.read_bytes()


def test_filesystem_publisher_rejects_current_revision_rebind(tmp_path: Path) -> None:
    backend = FilesystemPublisherBackend(tmp_path / "mirror")
    first = tmp_path / "first.json"
    first.write_bytes(b'{"pointer_revision":7,"release_id":"release-a"}')
    conflicting = tmp_path / "conflicting.json"
    conflicting.write_bytes(b'{"pointer_revision":7,"release_id":"release-b"}')
    backend.promote_current(first)

    with pytest.raises(ResourceIndexError) as exc:
        backend.promote_current(conflicting)

    assert exc.value.error_code == PUBLISH_CONFLICT
    assert "cannot be rebound" in exc.value.message
    assert (tmp_path / "mirror" / "v1" / "current.json").read_bytes() == first.read_bytes()


def test_filesystem_publisher_rejects_current_revision_rollback(tmp_path: Path) -> None:
    backend = FilesystemPublisherBackend(tmp_path / "mirror")
    current = tmp_path / "current.json"
    current.write_bytes(b'{"pointer_revision":8,"release_id":"release-8"}')
    rollback = tmp_path / "rollback.json"
    rollback.write_bytes(b'{"pointer_revision":7,"release_id":"release-7"}')
    backend.promote_current(current)

    with pytest.raises(ResourceIndexError) as exc:
        backend.promote_current(rollback)

    assert exc.value.error_code == PUBLISH_CONFLICT
    assert "rollback is forbidden" in exc.value.message
    assert (tmp_path / "mirror" / "v1" / "current.json").read_bytes() == current.read_bytes()


def test_filesystem_publisher_reuses_identical_current_revision(tmp_path: Path) -> None:
    backend = FilesystemPublisherBackend(tmp_path / "mirror")
    current = tmp_path / "current.json"
    current.write_bytes(b'{"pointer_revision":7,"release_id":"release-a"}')
    backend.promote_current(current)
    before = (tmp_path / "mirror" / "v1" / "current.json").stat().st_mtime_ns

    published = backend.promote_current(current)

    after = (tmp_path / "mirror" / "v1" / "current.json").stat().st_mtime_ns
    assert published.sha256 == hashlib.sha256(current.read_bytes()).hexdigest()
    assert after == before
