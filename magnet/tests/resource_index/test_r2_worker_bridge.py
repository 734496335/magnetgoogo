from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Mapping

import pytest

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.publish.base import UploadRequest
from magnet.resource_index.publish.worker_bridge import BridgeHttpResponse, WorkerR2PublisherBackend
from magnet.resource_index.release.protocol import sha256_file


class FakeBridge:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, object]] = {}
        self.corrupt_get = False
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> BridgeHttpResponse:
        self.calls.append((method, url))
        assert headers["authorization"] == "Bearer " + "t" * 48
        parsed = urllib.parse.urlparse(url)
        if parsed.path == "/health":
            return BridgeHttpResponse(200, {}, b'{"status":"ok","currentPromotion":false}')
        key = urllib.parse.parse_qs(parsed.query)["key"][0]
        item = self.objects.get(key)
        if method == "HEAD":
            if item is None:
                return BridgeHttpResponse(404, {"x-media-bridge": "1"}, b"")
            return BridgeHttpResponse(200, self._headers(item), b"")
        if method == "GET":
            if item is None:
                return BridgeHttpResponse(404, {}, b"")
            payload = bytes(item["body"])
            if self.corrupt_get:
                payload += b"x"
            return BridgeHttpResponse(200, self._headers(item), payload)
        if method == "PUT":
            if item is not None:
                same = item["sha256"] == headers["x-media-sha256"] and len(bytes(item["body"])) == int(headers["x-media-size"])
                if not same:
                    return BridgeHttpResponse(409, {}, b'{"error":"conflict"}')
                return BridgeHttpResponse(200, {}, b'{"uploaded":false,"reused":true}')
            assert body is not None
            self.objects[key] = {
                "body": body,
                "sha256": headers["x-media-sha256"],
                "release_id": headers["x-media-release-id"],
                "object_kind": headers["x-media-object-kind"],
            }
            return BridgeHttpResponse(201, {}, b'{"uploaded":true,"reused":false}')
        raise AssertionError(method)

    @staticmethod
    def _headers(item: Mapping[str, object]) -> dict[str, str]:
        return {
            "x-media-bridge": "1",
            "content-length": str(len(bytes(item["body"]))),
            "x-media-sha256": str(item["sha256"]),
            "x-media-release-id": str(item["release_id"]),
            "x-media-object-kind": str(item["object_kind"]),
            "etag": '"fake"',
        }


def _backend(bridge: FakeBridge) -> WorkerR2PublisherBackend:
    return WorkerR2PublisherBackend(
        worker_url="https://example.workers.dev",
        upload_token="t" * 48,
        prefix="m2-test/release-r4",
        transport=bridge,
        retry_base_seconds=0,
        sleeper=lambda _seconds: None,
    )


def _request(path: Path, key: str = "v1/objects/detail/example.json") -> UploadRequest:
    return UploadRequest(
        key=key,
        source_path=path,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        content_type="application/json; charset=utf-8",
        cache_control="public, max-age=31536000, immutable",
        release_id="release-r4",
        object_kind="detail",
    )


def test_worker_bridge_uploads_deep_verifies_and_reuses(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    bridge = FakeBridge()
    backend = _backend(bridge)
    backend.healthcheck()

    first = backend.upload(_request(path), deep_verify=True)
    second = backend.upload(_request(path), deep_verify=True)

    assert first.uploaded is True and first.reused is False
    assert second.uploaded is False and second.reused is True
    assert len(bridge.objects) == 1
    object_gets = [call for call in bridge.calls if call[0] == "GET" and "/object?" in call[1]]
    assert len(object_gets) == 2


def test_worker_bridge_blocks_existing_different_content(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    bridge = FakeBridge()
    key = "m2-test/release-r4/v1/objects/detail/example.json"
    bridge.objects[key] = {"body": b"bad", "sha256": hashlib.sha256(b"bad").hexdigest(), "release_id": "x", "object_kind": "detail"}

    with pytest.raises(ResourceIndexError, match="different content"):
        _backend(bridge).upload(_request(path))


def test_worker_bridge_detects_corrupt_download(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    bridge = FakeBridge()
    backend = _backend(bridge)
    backend.upload(_request(path), deep_verify=False)
    bridge.corrupt_get = True

    with pytest.raises(ResourceIndexError, match="body verification"):
        backend.verify(_request(path), deep=True)


def test_worker_bridge_forbids_current_and_redacts_token(tmp_path: Path) -> None:
    path = tmp_path / "current.json"
    path.write_text("{}", encoding="utf-8")
    bridge = FakeBridge()
    backend = _backend(bridge)

    assert "t" * 48 not in repr(backend)
    assert "<redacted>" in repr(backend)
    with pytest.raises(ResourceIndexError, match="current.json"):
        backend.upload(_request(path, key="v1/current.json"))


def test_worker_bridge_distinguishes_platform_404_from_worker_missing() -> None:
    bridge = FakeBridge()
    attempts = 0

    def propagating_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> BridgeHttpResponse:
        nonlocal attempts
        if method == "HEAD" and attempts < 2:
            attempts += 1
            return BridgeHttpResponse(404, {"server": "cloudflare"}, b"platform route missing")
        return bridge(method, url, headers, body)

    backend = WorkerR2PublisherBackend(
        worker_url="https://example.workers.dev",
        upload_token="t" * 48,
        prefix="m2-test/release-r4",
        transport=propagating_transport,
        retry_base_seconds=0,
        sleeper=lambda _seconds: None,
    )

    assert backend.head("v1/objects/detail/missing.json") is None
    assert attempts == 2


def test_worker_bridge_retries_edge_unauthorized_before_head(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    bridge = FakeBridge()
    request = _request(path)
    backend = _backend(bridge)
    backend.upload(request, deep_verify=False)
    attempts = 0

    def lagging_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> BridgeHttpResponse:
        nonlocal attempts
        if method == "HEAD" and attempts < 2:
            attempts += 1
            return BridgeHttpResponse(401, {}, b'{"error":"unauthorized"}')
        return bridge(method, url, headers, body)

    lagging_backend = WorkerR2PublisherBackend(
        worker_url="https://example.workers.dev",
        upload_token="t" * 48,
        prefix="m2-test/release-r4",
        transport=lagging_transport,
        retry_base_seconds=0,
        sleeper=lambda _seconds: None,
    )

    published = lagging_backend.head(request.key)
    assert published is not None
    assert published.sha256 == request.sha256
    assert attempts == 2


def test_worker_bridge_rejects_object_larger_than_one_mib(tmp_path: Path) -> None:
    path = tmp_path / "large.bin"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    request = UploadRequest(
        key="v1/covers/large.bin",
        source_path=path,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        content_type="application/octet-stream",
        cache_control="public, max-age=31536000, immutable",
        release_id="release-r4",
        object_kind="cover",
    )

    with pytest.raises(ResourceIndexError, match="safety limit"):
        _backend(FakeBridge()).upload(request)


def test_worker_bridge_allows_release_manifest_up_to_two_mib(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    request = UploadRequest(
        key="v1/releases/release-r6/manifest.json",
        source_path=path,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        content_type="application/json; charset=utf-8",
        cache_control="public, max-age=31536000, immutable",
        release_id="release-r6",
        object_kind="manifest",
    )
    bridge = FakeBridge()
    backend = WorkerR2PublisherBackend(
        worker_url="https://example.workers.dev",
        upload_token="t" * 48,
        prefix="",
        allow_production_root=True,
        transport=bridge,
        retry_base_seconds=0,
        sleeper=lambda _seconds: None,
    )

    outcome = backend.upload(request, deep_verify=True)

    assert outcome.uploaded is True
    assert set(bridge.objects) == {"v1/releases/release-r6/manifest.json"}


def test_worker_bridge_rejects_disguised_large_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    request = UploadRequest(
        key="v1/objects/detail/manifest.json",
        source_path=path,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        content_type="application/json; charset=utf-8",
        cache_control="public, max-age=31536000, immutable",
        release_id="release-r6",
        object_kind="manifest",
    )

    with pytest.raises(ResourceIndexError, match="safety limit"):
        _backend(FakeBridge()).upload(request)


def test_worker_bridge_rejects_manifest_larger_than_two_mib(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    request = UploadRequest(
        key="v1/releases/release-r6/manifest.json",
        source_path=path,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        content_type="application/json; charset=utf-8",
        cache_control="public, max-age=31536000, immutable",
        release_id="release-r6",
        object_kind="manifest",
    )

    with pytest.raises(ResourceIndexError, match="safety limit"):
        _backend(FakeBridge()).upload(request)


def test_worker_bridge_rejects_non_test_prefix() -> None:
    with pytest.raises(ResourceIndexError, match="m2-test"):
        WorkerR2PublisherBackend(
            worker_url="https://example.workers.dev",
            upload_token="t" * 48,
            prefix="production",
            transport=FakeBridge(),
        )


def test_worker_bridge_production_root_uses_exact_release_keys(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    bridge = FakeBridge()
    backend = WorkerR2PublisherBackend(
        worker_url="https://example.workers.dev",
        upload_token="t" * 48,
        prefix="",
        allow_production_root=True,
        transport=bridge,
        retry_base_seconds=0,
        sleeper=lambda _seconds: None,
    )

    backend.upload(_request(path), deep_verify=True)

    assert set(bridge.objects) == {"v1/objects/detail/example.json"}
    assert "allow_production_root=True" in repr(backend)


def test_worker_bridge_production_root_rejects_nonempty_prefix() -> None:
    with pytest.raises(ResourceIndexError, match="bucket root"):
        WorkerR2PublisherBackend(
            worker_url="https://example.workers.dev",
            upload_token="t" * 48,
            prefix="production",
            allow_production_root=True,
            transport=FakeBridge(),
        )


def test_worker_bridge_default_mode_rejects_empty_prefix() -> None:
    with pytest.raises(ResourceIndexError, match="non-empty"):
        WorkerR2PublisherBackend(
            worker_url="https://example.workers.dev",
            upload_token="t" * 48,
            prefix="",
            transport=FakeBridge(),
        )


def test_worker_bridge_production_root_still_forbids_current(tmp_path: Path) -> None:
    path = tmp_path / "current.json"
    path.write_text("{}", encoding="utf-8")
    backend = WorkerR2PublisherBackend(
        worker_url="https://example.workers.dev",
        upload_token="t" * 48,
        prefix="",
        allow_production_root=True,
        transport=FakeBridge(),
    )

    with pytest.raises(ResourceIndexError, match="current.json"):
        backend.upload(_request(path, key="v1/current.json"))
