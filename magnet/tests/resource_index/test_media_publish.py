from __future__ import annotations

import hashlib
import io
import json
import os
import threading
from pathlib import Path
from typing import Any

import pytest

import magnet.resource_index.publish.orchestrator as publish_orchestrator
from magnet.resource_index.cli import main as cli_main
from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.publish.base import UploadRequest
from magnet.resource_index.publish.orchestrator import (
    MediaPublishConfig,
    build_media_publish_plan,
    publish_media_release,
)
from magnet.resource_index.publish.r2 import R2PublisherBackend
from magnet.resource_index.release.builder import build_media_release
from magnet.resource_index.release.protocol import sha256_file
from magnet.tests.resource_index.test_media_release import _setup


class FakeClientError(Exception):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.events: list[tuple[str, str]] = []
        self.fail_put_suffixes: set[str] = set()
        self.transient_put_failures: dict[str, int] = {}
        self.corrupt_get_suffixes: set[str] = set()
        self.race_on_put: dict[str, dict[str, Any]] = {}
        self.health_error: Exception | None = None
        self._lock = threading.Lock()

    def head_bucket(self, *, Bucket: str) -> dict[str, Any]:
        self.events.append(("head_bucket", Bucket))
        if self.health_error is not None:
            raise self.health_error
        return {}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        with self._lock:
            item = self.objects.get(Key)
            self.events.append(("head", Key))
            if item is None:
                raise FakeClientError("NoSuchKey", 404)
            return {
                "ContentLength": len(item["body"]),
                "Metadata": dict(item["metadata"]),
                "ETag": item.get("etag", '"fake-etag"'),
            }

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        key = str(kwargs["Key"])
        if any(key.endswith(suffix) for suffix in self.fail_put_suffixes):
            raise FakeClientError("InternalError", 500)
        for suffix, remaining in list(self.transient_put_failures.items()):
            if key.endswith(suffix) and remaining > 0:
                self.transient_put_failures[suffix] = remaining - 1
                raise FakeClientError("InternalError", 500)
        body = kwargs["Body"]
        payload = body.read() if hasattr(body, "read") else bytes(body)
        with self._lock:
            self.events.append(("put", key))
            for suffix, raced in list(self.race_on_put.items()):
                if key.endswith(suffix):
                    self.objects[key] = raced
                    del self.race_on_put[suffix]
                    raise FakeClientError("PreconditionFailed", 412)
            if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
                raise FakeClientError("PreconditionFailed", 412)
            self.objects[key] = {
                "body": payload,
                "metadata": dict(kwargs.get("Metadata") or {}),
                "content_type": kwargs.get("ContentType"),
                "cache_control": kwargs.get("CacheControl"),
                "etag": '"fake-etag"',
            }
        return {"ETag": '"fake-etag"'}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        with self._lock:
            item = self.objects.get(Key)
            self.events.append(("get", Key))
            if item is None:
                raise FakeClientError("NoSuchKey", 404)
            payload = bytes(item["body"])
        if any(Key.endswith(suffix) for suffix in self.corrupt_get_suffixes):
            payload += b"corrupt"
        return {"Body": io.BytesIO(payload)}


def _request(path: Path, *, key: str = "v1/objects/detail/example.json") -> UploadRequest:
    return UploadRequest(
        key=key,
        source_path=path,
        sha256=sha256_file(path),
        size=path.stat().st_size,
        content_type="application/json; charset=utf-8",
        cache_control="public, max-age=31536000, immutable",
        release_id="release-test",
        object_kind="detail",
    )


def _backend(client: FakeS3Client, prefix: str = "m2-test") -> R2PublisherBackend:
    return R2PublisherBackend(
        bucket="magnetgoogo-media-m2-test",
        prefix=prefix,
        client=client,
        retry_base_seconds=0,
        sleeper=lambda _seconds: None,
    )


def _lock_path(receipt_dir: Path, backend: R2PublisherBackend) -> Path:
    lock_hash = hashlib.sha256(backend.destination.encode("utf-8")).hexdigest()[:16]
    return receipt_dir / f".publish-{backend.name}-{lock_hash}.lock"


def _publish_fixture(tmp_path: Path, *, client: FakeS3Client, max_workers: int = 1):
    release = build_media_release(_setup(tmp_path))
    result = publish_media_release(
        _backend(client),
        MediaPublishConfig(
            release_dir=Path(release.release_dir),
            current_path=Path(release.current_path),
            public_key_path=_setup(tmp_path).public_key_path,
            receipt_dir=tmp_path / "receipts",
            max_workers=max_workers,
            deep_verify=True,
        ),
    )
    return release, result


def test_r2_upload_stores_sha_metadata_and_deep_verifies(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    client = FakeS3Client()
    backend = _backend(client)

    outcome = backend.upload(_request(path), deep_verify=True)

    assert outcome.uploaded is True
    assert outcome.reused is False
    remote = client.objects["m2-test/v1/objects/detail/example.json"]
    assert remote["metadata"]["sha256"] == sha256_file(path)
    assert remote["metadata"]["release-id"] == "release-test"
    assert remote["cache_control"] == "public, max-age=31536000, immutable"
    assert ("get", "m2-test/v1/objects/detail/example.json") in client.events


def test_r2_matching_object_is_reused_but_still_deep_verified(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    client = FakeS3Client()
    backend = _backend(client)
    request = _request(path)
    backend.upload(request, deep_verify=True)
    client.events.clear()

    outcome = backend.upload(request, deep_verify=True)

    assert outcome.reused is True
    assert outcome.uploaded is False
    assert not [event for event in client.events if event[0] == "put"]
    assert [event for event in client.events if event[0] == "get"]


def test_r2_immutable_collision_is_blocked(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    client = FakeS3Client()
    backend = _backend(client)
    remote_key = "m2-test/v1/objects/detail/example.json"
    client.objects[remote_key] = {
        "body": b"different",
        "metadata": {"sha256": "0" * 64},
    }

    with pytest.raises(ResourceIndexError, match="different content"):
        backend.upload(_request(path))

    assert client.objects[remote_key]["body"] == b"different"


def test_r2_retries_transient_put_failure_with_a_fresh_file_body(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    client = FakeS3Client()
    client.transient_put_failures["example.json"] = 1
    backend = _backend(client)

    outcome = backend.upload(_request(path), deep_verify=True)

    assert outcome.uploaded is True
    assert client.transient_put_failures["example.json"] == 0
    assert client.objects["m2-test/v1/objects/detail/example.json"]["body"] == path.read_bytes()


def test_r2_conditional_race_reuses_identical_winner(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    client = FakeS3Client()
    backend = _backend(client)
    request = _request(path)
    client.race_on_put["example.json"] = {
        "body": path.read_bytes(),
        "metadata": {"sha256": request.sha256},
        "etag": '"raced"',
    }

    outcome = backend.upload(request, deep_verify=True)

    assert outcome.reused is True
    assert outcome.uploaded is False
    assert outcome.object.sha256 == request.sha256


def test_r2_conditional_race_blocks_different_winner(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    client = FakeS3Client()
    backend = _backend(client)
    client.race_on_put["example.json"] = {
        "body": b"different",
        "metadata": {"sha256": "0" * 64},
        "etag": '"raced"',
    }

    with pytest.raises(ResourceIndexError, match="lost to different content"):
        backend.upload(_request(path), deep_verify=True)


def test_r2_deep_verification_detects_body_corruption_even_when_metadata_matches(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    client = FakeS3Client()
    backend = _backend(client)
    request = _request(path)
    backend.upload(request)
    client.corrupt_get_suffixes.add("example.json")

    with pytest.raises(ResourceIndexError, match="body SHA-256"):
        backend.verify(request, deep=True)


def test_r2_rejects_unsafe_and_production_current_keys(tmp_path: Path) -> None:
    path = tmp_path / "object.json"
    path.write_text("{}", encoding="utf-8")
    backend = _backend(FakeS3Client())

    with pytest.raises(ResourceIndexError, match="unsafe"):
        backend.upload(_request(path, key="../escape.json"))
    with pytest.raises(ResourceIndexError, match="current.json"):
        backend.upload(_request(path, key="v1/current.json"))


def test_publish_orders_objects_then_manifest_then_pointer(tmp_path: Path) -> None:
    client = FakeS3Client()
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)

    result = publish_media_release(
        _backend(client),
        MediaPublishConfig(
            release_dir=Path(release.release_dir),
            current_path=Path(release.current_path),
            public_key_path=config.public_key_path,
            receipt_dir=tmp_path / "receipts",
            max_workers=1,
        ),
    )

    put_keys = [key for operation, key in client.events if operation == "put"]
    manifest_index = next(index for index, key in enumerate(put_keys) if key.endswith("/manifest.json"))
    pointer_index = next(index for index, key in enumerate(put_keys) if "/staging/pointers/" in f"/{key}")
    assert manifest_index == len(put_keys) - 2
    assert pointer_index == len(put_keys) - 1
    assert all("v1/current.json" not in key for key in put_keys)
    assert result.current_promoted is False
    receipt = json.loads(Path(result.receipt_path).read_text(encoding="utf-8"))
    assert receipt["status"] == "success"
    assert receipt["current_promoted"] is False


def test_publish_can_stop_after_manifest_without_uploading_pointer_candidate(tmp_path: Path) -> None:
    client = FakeS3Client()
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)

    result = publish_media_release(
        _backend(client),
        MediaPublishConfig(
            release_dir=Path(release.release_dir),
            current_path=Path(release.current_path),
            public_key_path=config.public_key_path,
            receipt_dir=tmp_path / "receipts",
            max_workers=1,
            upload_pointer_candidate=False,
        ),
    )

    assert result.manifest_uploaded is True
    assert result.pointer_uploaded is False
    assert not any("/staging/pointers/" in f"/{key}" for key in client.objects)


def test_object_failure_never_uploads_manifest_or_pointer_and_writes_receipt(tmp_path: Path) -> None:
    client = FakeS3Client()
    client.fail_put_suffixes.add(".json")
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)

    with pytest.raises(ResourceIndexError, match="PutObject"):
        publish_media_release(
            _backend(client),
            MediaPublishConfig(
                release_dir=Path(release.release_dir),
                current_path=Path(release.current_path),
                public_key_path=config.public_key_path,
                receipt_dir=tmp_path / "receipts",
                max_workers=1,
            ),
        )

    put_keys = [key for operation, key in client.events if operation == "put"]
    assert not any(key.endswith("/manifest.json") for key in put_keys)
    assert not any("/staging/pointers/" in f"/{key}" for key in put_keys)
    receipts = list((tmp_path / "receipts").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["manifest_uploaded"] is False
    assert receipt["pointer_uploaded"] is False


def test_manifest_failure_never_uploads_pointer_candidate(tmp_path: Path) -> None:
    client = FakeS3Client()
    client.fail_put_suffixes.add("manifest.json")
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)

    with pytest.raises(ResourceIndexError, match="PutObject"):
        publish_media_release(
            _backend(client),
            MediaPublishConfig(
                release_dir=Path(release.release_dir),
                current_path=Path(release.current_path),
                public_key_path=config.public_key_path,
                receipt_dir=tmp_path / "receipts",
                max_workers=1,
            ),
        )

    assert not any(key.endswith("manifest.json") for key in client.objects)
    assert not any("/staging/pointers/" in f"/{key}" for key in client.objects)
    receipt = json.loads(next((tmp_path / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["manifest_uploaded"] is False
    assert receipt["pointer_uploaded"] is False


def test_pointer_failure_keeps_manifest_but_never_promotes_current(tmp_path: Path) -> None:
    client = FakeS3Client()
    client.fail_put_suffixes.add("b8c702d5.json")
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)
    pointer_suffix = Path(release.current_path).name
    client.fail_put_suffixes = {pointer_suffix}

    with pytest.raises(ResourceIndexError, match="PutObject"):
        publish_media_release(
            _backend(client),
            MediaPublishConfig(
                release_dir=Path(release.release_dir),
                current_path=Path(release.current_path),
                public_key_path=config.public_key_path,
                receipt_dir=tmp_path / "receipts",
                max_workers=1,
            ),
        )

    assert any(key.endswith("manifest.json") for key in client.objects)
    assert not any("/staging/pointers/" in f"/{key}" for key in client.objects)
    receipt = json.loads(next((tmp_path / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["manifest_uploaded"] is True
    assert receipt["pointer_uploaded"] is False
    assert receipt["current_promoted"] is False


def test_concurrent_failure_receipt_records_all_completed_objects(tmp_path: Path) -> None:
    client = FakeS3Client()
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)
    manifest = json.loads(Path(release.manifest_path).read_text(encoding="utf-8"))
    fail_suffix = Path(manifest["objects"][0]["path"]).name
    client.fail_put_suffixes.add(fail_suffix)

    with pytest.raises(ResourceIndexError):
        publish_media_release(
            _backend(client),
            MediaPublishConfig(
                release_dir=Path(release.release_dir),
                current_path=Path(release.current_path),
                public_key_path=config.public_key_path,
                receipt_dir=tmp_path / "receipts",
                max_workers=4,
            ),
        )

    receipt = json.loads(next((tmp_path / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert len(receipt["objects"]) == len(client.objects)
    assert receipt["manifest_uploaded"] is False
    assert receipt["pointer_uploaded"] is False


def test_partial_failure_can_resume_without_overwriting_existing_objects(tmp_path: Path) -> None:
    client = FakeS3Client()
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)
    publish_config = MediaPublishConfig(
        release_dir=Path(release.release_dir),
        current_path=Path(release.current_path),
        public_key_path=config.public_key_path,
        receipt_dir=tmp_path / "receipts",
        max_workers=1,
    )
    manifest = json.loads(Path(release.manifest_path).read_text(encoding="utf-8"))
    fail_suffix = Path(manifest["objects"][1]["path"]).name
    client.fail_put_suffixes.add(fail_suffix)

    with pytest.raises(ResourceIndexError):
        publish_media_release(_backend(client), publish_config)
    first_object_count = len(client.objects)
    assert first_object_count >= 1
    client.fail_put_suffixes.clear()
    client.events.clear()

    result = publish_media_release(_backend(client), publish_config)

    assert result.status == "success"
    assert result.reused_count >= first_object_count
    assert result.manifest_uploaded is True
    assert result.pointer_uploaded is True
    receipts = sorted((tmp_path / "receipts").glob("*.json"))
    assert len(receipts) == 2
    statuses = {
        json.loads(path.read_text(encoding="utf-8"))["status"]
        for path in receipts
    }
    assert statuses == {"failed", "success"}


def test_stale_publish_lock_is_recovered(tmp_path: Path) -> None:
    client = FakeS3Client()
    backend = _backend(client)
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)
    receipt_dir = tmp_path / "receipts"
    lock_path = _lock_path(receipt_dir, backend)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("pid=99999999\n", encoding="ascii")

    result = publish_media_release(
        backend,
        MediaPublishConfig(
            release_dir=Path(release.release_dir),
            current_path=Path(release.current_path),
            public_key_path=config.public_key_path,
            receipt_dir=receipt_dir,
            max_workers=1,
        ),
    )

    assert result.status == "success"
    assert not lock_path.exists()


def test_windows_system_error_marks_lock_pid_as_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_windows_invalid_parameter(_pid: int, _signal: int) -> None:
        raise SystemError("os.kill returned WinError 87")

    monkeypatch.setattr(publish_orchestrator.os, "kill", raise_windows_invalid_parameter)
    assert publish_orchestrator._process_exists(90108) is False


def test_recent_lock_without_pid_is_not_deleted_during_creation_window(tmp_path: Path) -> None:
    client = FakeS3Client()
    backend = _backend(client)
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)
    receipt_dir = tmp_path / "receipts"
    lock_path = _lock_path(receipt_dir, backend)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="ascii")

    with pytest.raises(ResourceIndexError) as captured:
        publish_media_release(
            backend,
            MediaPublishConfig(
                release_dir=Path(release.release_dir),
                current_path=Path(release.current_path),
                public_key_path=config.public_key_path,
                receipt_dir=receipt_dir,
                max_workers=1,
            ),
        )

    assert captured.value.error_code == "PUBLISH_LOCKED"
    assert lock_path.exists()
    assert not client.objects
    lock_path.unlink()


def test_old_lock_without_pid_is_recovered(tmp_path: Path) -> None:
    client = FakeS3Client()
    backend = _backend(client)
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)
    receipt_dir = tmp_path / "receipts"
    lock_path = _lock_path(receipt_dir, backend)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="ascii")
    old = lock_path.stat().st_mtime - 600
    os.utime(lock_path, (old, old))

    result = publish_media_release(
        backend,
        MediaPublishConfig(
            release_dir=Path(release.release_dir),
            current_path=Path(release.current_path),
            public_key_path=config.public_key_path,
            receipt_dir=receipt_dir,
            max_workers=1,
        ),
    )

    assert result.status == "success"
    assert not lock_path.exists()


def test_active_publish_lock_blocks_second_publisher(tmp_path: Path) -> None:
    client = FakeS3Client()
    backend = _backend(client)
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)
    receipt_dir = tmp_path / "receipts"
    lock_path = _lock_path(receipt_dir, backend)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(f"pid={os.getpid()}\n", encoding="ascii")

    with pytest.raises(ResourceIndexError) as captured:
        publish_media_release(
            backend,
            MediaPublishConfig(
                release_dir=Path(release.release_dir),
                current_path=Path(release.current_path),
                public_key_path=config.public_key_path,
                receipt_dir=receipt_dir,
                max_workers=1,
            ),
        )

    assert captured.value.error_code == "PUBLISH_LOCKED"
    assert not client.objects
    lock_path.unlink()


def test_healthcheck_failure_stops_before_any_object_upload(tmp_path: Path) -> None:
    client = FakeS3Client()
    client.health_error = FakeClientError("AccessDenied", 403)
    release = build_media_release(_setup(tmp_path))
    config = _setup(tmp_path)

    with pytest.raises(ResourceIndexError, match="healthcheck"):
        publish_media_release(
            _backend(client),
            MediaPublishConfig(
                release_dir=Path(release.release_dir),
                current_path=Path(release.current_path),
                public_key_path=config.public_key_path,
                receipt_dir=tmp_path / "receipts",
            ),
        )

    assert not client.objects


def test_cli_requires_explicit_remote_acknowledgement(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_main(
        [
            "publish-media-r2-staging",
            "--release-dir",
            "missing-release",
            "--current",
            "missing-pointer.json",
        ]
    )

    assert code == 1
    assert "LIVE_POLICY_NOT_ACKNOWLEDGED" in capsys.readouterr().err


def test_cli_rejects_non_m2_prefix_before_loading_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_main(
        [
            "publish-media-r2-staging",
            "--release-dir",
            "missing-release",
            "--current",
            "missing-pointer.json",
            "--prefix",
            "production",
            "--yes",
        ]
    )

    assert code == 1
    assert "must begin with m2-test" in capsys.readouterr().err


def test_missing_s3_credentials_fail_without_leaking_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "R2_ENDPOINT_URL",
        "AWS_ENDPOINT_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ResourceIndexError) as captured:
        R2PublisherBackend.from_environment(bucket="magnetgoogo-media-m2-test")

    assert captured.value.error_code == "PUBLISH_CONFIG_ERROR"
    assert "secret" not in json.dumps(captured.value.context).lower()


def test_real_local_release_contract_publishes_all_614_objects_when_available(tmp_path: Path) -> None:
    release_root = Path(
        "data/resource_index/media_releases_m1_final/staging/releases/20260726T000000Z-b8c702d5"
    )
    pointer = Path(
        "data/resource_index/media_releases_m1_final/staging/pointers/"
        "00000000000000000004-20260726T000000Z-b8c702d5.json"
    )
    public_key = Path("data/resource_index/.secrets/media-ed25519-public.pem")
    if not release_root.exists() or not pointer.exists() or not public_key.exists():
        pytest.skip("real local M1 release evidence is not present")
    client = FakeS3Client()

    result = publish_media_release(
        _backend(client, prefix="full-release-contract"),
        MediaPublishConfig(
            release_dir=release_root,
            current_path=pointer,
            public_key_path=public_key,
            receipt_dir=tmp_path / "receipts",
            max_workers=8,
            deep_verify=True,
        ),
    )

    assert result.object_count == 614
    assert result.uploaded_count == 616
    assert result.reused_count == 0
    assert len(client.objects) == 616
    assert result.manifest_uploaded is True
    assert result.pointer_uploaded is True
    assert result.current_promoted is False

    second = publish_media_release(
        _backend(client, prefix="full-release-contract"),
        MediaPublishConfig(
            release_dir=release_root,
            current_path=pointer,
            public_key_path=public_key,
            receipt_dir=tmp_path / "receipts-second",
            max_workers=8,
            deep_verify=True,
        ),
    )
    assert second.uploaded_count == 0
    assert second.reused_count == 616
    receipt_text = Path(second.receipt_path).read_text(encoding="utf-8").lower()
    assert "access_key" not in receipt_text
    assert "secret" not in receipt_text


def test_publish_plan_is_complete_and_has_no_remote_side_effects(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    release = build_media_release(config)

    plan = build_media_publish_plan(
        MediaPublishConfig(
            release_dir=Path(release.release_dir),
            current_path=Path(release.current_path),
            public_key_path=config.public_key_path,
            receipt_dir=tmp_path / "receipts",
        )
    )

    assert plan.object_count == release.object_count
    assert plan.artifact_count == 2
    assert plan.total_file_count == release.object_count + 2
    assert plan.verified_object_count == release.object_count
    assert plan.total_bytes == sum(request.size for request in plan.requests)
    assert plan.object_kinds["manifest"] == 1
    assert plan.object_kinds["pointer-candidate"] == 1
    assert not any(request.key == "v1/current.json" for request in plan.requests)


def test_publish_plan_can_exclude_pointer_candidate(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    release = build_media_release(config)

    plan = build_media_publish_plan(
        MediaPublishConfig(
            release_dir=Path(release.release_dir),
            current_path=Path(release.current_path),
            public_key_path=config.public_key_path,
            receipt_dir=tmp_path / "receipts",
            upload_pointer_candidate=False,
        )
    )

    assert plan.artifact_count == 1
    assert plan.total_file_count == release.object_count + 1
    assert "pointer-candidate" not in plan.object_kinds


def test_cli_dry_run_needs_no_acknowledgement_or_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _setup(tmp_path)
    release = build_media_release(config)
    for name in (
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "CLOUDFLARE_API_TOKEN",
        "R2_PARENT_ACCESS_KEY_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    code = cli_main(
        [
            "publish-media-r2-staging",
            "--release-dir",
            release.release_dir,
            "--current",
            release.current_path,
            "--public-key",
            str(config.public_key_path),
            "--prefix",
            "m2-test/dry-run",
            "--dry-run",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "dry-run"
    assert payload["total_file_count"] == release.object_count + 2
    assert payload["remote_requests"] == 0
    assert payload["current_promoted"] is False
    assert payload["object_kinds"]["pointer-candidate"] == 1
