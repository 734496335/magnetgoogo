"""Authenticated temporary Worker bridge for publishing immutable objects to R2."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from magnet.resource_index.errors import (
    PUBLISH_CONFIG_ERROR,
    PUBLISH_CONFLICT,
    PUBLISH_REMOTE_ERROR,
    PUBLISH_VERIFICATION_FAILED,
    ResourceIndexError,
)
from magnet.resource_index.publish.base import PublishedObject, PublisherBackend, UploadOutcome, UploadRequest
from magnet.resource_index.release.protocol import sha256_file

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
_MAX_OBJECT_BYTES = 1024 * 1024


@dataclass(frozen=True)
class BridgeHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, str, Mapping[str, str], bytes | None], BridgeHttpResponse]


def _fail(error_code: str, message: str, **context: Any) -> None:
    raise ResourceIndexError(error_code, message, context)


def _normalize_prefix(prefix: str) -> str:
    value = prefix.strip().replace("\\", "/").strip("/")
    parts = PurePosixPath(value).parts if value else ()
    if not value or any(part in {"", ".", ".."} for part in parts):
        _fail(PUBLISH_CONFIG_ERROR, "Worker bridge prefix must be a safe non-empty path", prefix=prefix)
    if not value.startswith("m2-test"):
        _fail(PUBLISH_CONFIG_ERROR, "Worker bridge prefix must begin with m2-test", prefix=prefix)
    return "/".join(parts)


def _validate_key(key: str) -> str:
    value = key.strip()
    if not value or value.startswith("/") or "\\" in value or any(ord(char) < 32 for char in value):
        _fail(PUBLISH_CONFIG_ERROR, "Worker bridge object key is unsafe", key=key)
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        _fail(PUBLISH_CONFIG_ERROR, "Worker bridge object key contains an unsafe component", key=key)
    normalized = "/".join(parts)
    if normalized == "v1/current.json":
        _fail(PUBLISH_CONFIG_ERROR, "production current.json is forbidden", key=normalized)
    return normalized


def _header_map(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _default_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> BridgeHttpResponse:
    request_headers = {
        "user-agent": "MagnetGoogo-Media-Publisher/0.2.1",
        "accept": "application/json, application/octet-stream;q=0.9, */*;q=0.8",
        **dict(headers),
    }
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=45) as response:
            return BridgeHttpResponse(
                status=int(response.status),
                headers={str(key): str(value) for key, value in response.headers.items()},
                body=response.read(),
            )
    except urllib.error.HTTPError as exc:
        return BridgeHttpResponse(
            status=int(exc.code),
            headers={str(key): str(value) for key, value in exc.headers.items()},
            body=exc.read(),
        )


class WorkerR2PublisherBackend(PublisherBackend):
    """Publisher that talks to a short-lived authenticated Worker bound to R2."""

    def __init__(
        self,
        *,
        worker_url: str,
        upload_token: str,
        prefix: str,
        transport: Transport | None = None,
        max_attempts: int = 3,
        retry_base_seconds: float = 0.5,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        parsed = urllib.parse.urlparse(worker_url.strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            if transport is None:
                _fail(PUBLISH_CONFIG_ERROR, "Worker bridge URL must be an HTTPS origin")
        if len(upload_token) < 32:
            _fail(PUBLISH_CONFIG_ERROR, "Worker bridge token is missing or too short")
        if max_attempts < 1 or max_attempts > 8:
            _fail(PUBLISH_CONFIG_ERROR, "Worker bridge max_attempts must be between 1 and 8")
        self.worker_url = worker_url.rstrip("/")
        self.prefix = _normalize_prefix(prefix)
        self._token = upload_token
        self._transport = transport or _default_transport
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self._sleep = sleeper

    @property
    def name(self) -> str:
        return "r2-worker-bridge"

    @property
    def destination(self) -> str:
        return f"{self.worker_url}/{self.prefix}"

    def __repr__(self) -> str:
        return f"WorkerR2PublisherBackend(worker_url={self.worker_url!r}, prefix={self.prefix!r}, token=<redacted>)"

    def _remote_key(self, key: str) -> str:
        return f"{self.prefix}/{_validate_key(key)}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        extra_retry_statuses: set[int] | None = None,
    ) -> BridgeHttpResponse:
        request_headers = {"authorization": f"Bearer {self._token}", **dict(headers or {})}
        url = f"{self.worker_url}{path}"
        last_response: BridgeHttpResponse | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._transport(method, url, request_headers, body)
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                if attempt >= self.max_attempts:
                    _fail(PUBLISH_REMOTE_ERROR, "Worker bridge request failed", method=method, error=type(exc).__name__)
                self._sleep(self.retry_base_seconds * (2 ** (attempt - 1)))
                continue
            last_response = response
            retry_statuses = _RETRYABLE_STATUS | set(extra_retry_statuses or ())
            if response.status not in retry_statuses or attempt >= self.max_attempts:
                return response
            self._sleep(self.retry_base_seconds * (2 ** (attempt - 1)))
        if last_response is None:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge retry state produced no response", method=method)
        return last_response

    def _request_across_edge_propagation(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        propagation_statuses: set[int],
    ) -> BridgeHttpResponse:
        response: BridgeHttpResponse | None = None
        for attempt in range(1, 21):
            response = self._request(method, path, body=body, headers=headers)
            if response.status not in propagation_statuses or attempt >= 20:
                return response
            self._sleep(3.0)
        if response is None:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge propagation retry produced no response", method=method)
        return response

    def healthcheck(self) -> None:
        response = self._request_across_edge_propagation(
            "GET",
            "/health",
            propagation_statuses={401, 403, 404},
        )
        if response.status != 200:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge healthcheck failed", status=response.status)
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge healthcheck returned invalid JSON", error=type(exc).__name__)
        if not isinstance(payload, dict) or payload.get("status") != "ok" or payload.get("currentPromotion") is not False:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge healthcheck contract mismatch")

    def head(self, key: str) -> PublishedObject | None:
        remote_key = self._remote_key(key)
        query = urllib.parse.urlencode({"key": remote_key})
        response: BridgeHttpResponse | None = None
        headers: dict[str, str] = {}
        for attempt in range(1, 21):
            response = self._request("HEAD", f"/object?{query}")
            headers = _header_map(response.headers)
            is_worker_response = headers.get("x-media-bridge") == "1"
            if response.status in {401, 403} or (response.status == 404 and not is_worker_response):
                if attempt < 20:
                    self._sleep(3.0)
                    continue
            break
        if response is None:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge HEAD produced no response", key=remote_key)
        if response.status == 404 and headers.get("x-media-bridge") == "1":
            return None
        if response.status != 200:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge HEAD failed", key=remote_key, status=response.status)
        try:
            size = int(headers.get("content-length", "-1"))
        except ValueError:
            size = -1
        if size < 0:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge HEAD returned invalid size", key=remote_key)
        sha256 = headers.get("x-media-sha256") or None
        return PublishedObject(
            key=remote_key,
            size=size,
            sha256=sha256,
            etag=(headers.get("etag") or "").strip('"') or None,
            metadata={
                "release-id": headers.get("x-media-release-id", ""),
                "object-kind": headers.get("x-media-object-kind", ""),
            },
        )

    def verify(self, request: UploadRequest, *, deep: bool = True) -> PublishedObject:
        published = self.head(request.key)
        remote_key = self._remote_key(request.key)
        if published is None:
            _fail(PUBLISH_VERIFICATION_FAILED, "Worker bridge object is missing", key=remote_key)
        if published.size != request.size or published.sha256 != request.sha256:
            _fail(
                PUBLISH_VERIFICATION_FAILED,
                "Worker bridge object metadata verification failed",
                key=remote_key,
                expected_size=request.size,
                actual_size=published.size,
                expected_hash=request.sha256,
                actual_hash=published.sha256,
            )
        if deep:
            query = urllib.parse.urlencode({"key": remote_key})
            response = self._request_across_edge_propagation(
                "GET",
                f"/object?{query}",
                propagation_statuses={401, 403, 404},
            )
            if response.status != 200:
                _fail(PUBLISH_REMOTE_ERROR, "Worker bridge GET failed", key=remote_key, status=response.status)
            actual_hash = hashlib.sha256(response.body).hexdigest()
            if len(response.body) != request.size or actual_hash != request.sha256:
                _fail(
                    PUBLISH_VERIFICATION_FAILED,
                    "Worker bridge object body verification failed",
                    key=remote_key,
                    expected_size=request.size,
                    actual_size=len(response.body),
                    expected_hash=request.sha256,
                    actual_hash=actual_hash,
                )
        return published

    def upload(self, request: UploadRequest, *, deep_verify: bool = True) -> UploadOutcome:
        if not request.immutable:
            _fail(PUBLISH_CONFIG_ERROR, "Worker bridge only accepts immutable objects", key=request.key)
        if not request.source_path.is_file():
            _fail(PUBLISH_CONFIG_ERROR, "Worker bridge local source is missing", path=str(request.source_path))
        actual_size = request.source_path.stat().st_size
        if request.size > _MAX_OBJECT_BYTES or actual_size > _MAX_OBJECT_BYTES:
            _fail(
                PUBLISH_CONFIG_ERROR,
                "Worker bridge object exceeds the 1 MiB safety limit",
                path=str(request.source_path),
                size=actual_size,
            )
        actual_hash = sha256_file(request.source_path)
        if actual_size != request.size or actual_hash != request.sha256:
            _fail(PUBLISH_VERIFICATION_FAILED, "Worker bridge local source changed before upload", path=str(request.source_path))

        existing = self.head(request.key)
        if existing is not None:
            if existing.size != request.size or existing.sha256 != request.sha256:
                _fail(PUBLISH_CONFLICT, "Worker bridge immutable key contains different content", key=existing.key)
            verified = self.verify(request, deep=deep_verify)
            return UploadOutcome(object=verified, uploaded=False, reused=True, deep_verified=deep_verify)

        remote_key = self._remote_key(request.key)
        query = urllib.parse.urlencode({"key": remote_key})
        body = request.source_path.read_bytes()
        response = self._request_across_edge_propagation(
            "PUT",
            f"/object?{query}",
            body=body,
            headers={
                "content-type": request.content_type,
                "cache-control": request.cache_control,
                "x-media-sha256": request.sha256,
                "x-media-size": str(request.size),
                "x-media-release-id": request.release_id,
                "x-media-object-kind": request.object_kind,
            },
            propagation_statuses={401, 403, 404},
        )
        if response.status == 409:
            _fail(PUBLISH_CONFLICT, "Worker bridge conditional immutable upload conflicted", key=remote_key)
        if response.status not in {200, 201}:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge PUT failed", key=remote_key, status=response.status)
        try:
            result = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge PUT returned invalid JSON", key=remote_key, error=type(exc).__name__)
        uploaded = bool(result.get("uploaded")) if isinstance(result, dict) else False
        reused = bool(result.get("reused")) if isinstance(result, dict) else False
        if uploaded == reused:
            _fail(PUBLISH_REMOTE_ERROR, "Worker bridge PUT returned an invalid outcome", key=remote_key)
        verified = self.verify(request, deep=deep_verify)
        return UploadOutcome(object=verified, uploaded=uploaded, reused=reused, deep_verified=deep_verify)
