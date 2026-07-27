"""Cloudflare R2 publisher using the S3-compatible API."""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from magnet.resource_index.errors import (
    PUBLISH_CONFIG_ERROR,
    PUBLISH_CONFLICT,
    PUBLISH_REMOTE_ERROR,
    PUBLISH_VERIFICATION_FAILED,
    ResourceIndexError,
)
from magnet.resource_index.publish.base import (
    PublishedObject,
    PublisherBackend,
    UploadOutcome,
    UploadRequest,
)
from magnet.resource_index.release.protocol import sha256_file

_SAFE_BUCKET = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")


def _fail(error_code: str, message: str, **context: Any) -> None:
    raise ResourceIndexError(error_code, message, context)


def _normalize_prefix(prefix: str) -> str:
    value = prefix.strip().replace("\\", "/").strip("/")
    if not value:
        return ""
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        _fail(PUBLISH_CONFIG_ERROR, "R2 prefix contains an unsafe path component", prefix=prefix)
    return "/".join(parts)


def _validate_key(key: str) -> str:
    value = key.strip()
    if not value or value.startswith("/") or "\\" in value or any(ord(ch) < 32 for ch in value):
        _fail(PUBLISH_CONFIG_ERROR, "R2 object key must be a safe relative POSIX path", key=key)
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        _fail(PUBLISH_CONFIG_ERROR, "R2 object key contains an unsafe path component", key=key)
    normalized = "/".join(parts)
    if normalized == "v1/current.json":
        _fail(
            PUBLISH_CONFIG_ERROR,
            "M2 cannot upload or promote the production current.json pointer",
            key=normalized,
        )
    return normalized


def _error_status(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return None
    metadata = response.get("ResponseMetadata")
    if isinstance(metadata, Mapping):
        status = metadata.get("HTTPStatusCode")
        if isinstance(status, int):
            return status
    return None


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return None
    error = response.get("Error")
    if isinstance(error, Mapping):
        code = error.get("Code")
        if code is not None:
            return str(code)
    return None


def _is_not_found(exc: Exception) -> bool:
    return _error_status(exc) == 404 or _error_code(exc) in {"404", "NoSuchKey", "NotFound"}


def _is_retryable(exc: Exception) -> bool:
    return _error_status(exc) in {408, 429, 500, 502, 503, 504} or _error_code(exc) in {
        "InternalError",
        "RequestTimeout",
        "ServiceUnavailable",
        "SlowDown",
        "Throttling",
        "TooManyRequests",
    }


def _metadata(response: Mapping[str, Any]) -> dict[str, str]:
    raw = response.get("Metadata") or {}
    if not isinstance(raw, Mapping):
        return {}
    return {str(key).lower(): str(value) for key, value in raw.items()}


def _stream_sha256(body: Any) -> str:
    digest = hashlib.sha256()
    try:
        if isinstance(body, (bytes, bytearray, memoryview)):
            digest.update(bytes(body))
            return digest.hexdigest()
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()


class R2PublisherBackend(PublisherBackend):
    """Immutable-object publisher for one Cloudflare R2 bucket and prefix."""

    def __init__(
        self,
        *,
        bucket: str,
        account_id: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        session_token: str | None = None,
        endpoint_url: str | None = None,
        prefix: str = "",
        client: Any | None = None,
        max_attempts: int = 3,
        retry_base_seconds: float = 0.5,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not _SAFE_BUCKET.fullmatch(bucket):
            _fail(PUBLISH_CONFIG_ERROR, "invalid R2 bucket name", bucket=bucket)
        if max_attempts < 1 or max_attempts > 8:
            _fail(PUBLISH_CONFIG_ERROR, "R2 max_attempts must be between 1 and 8", value=max_attempts)
        if retry_base_seconds < 0 or retry_base_seconds > 30:
            _fail(
                PUBLISH_CONFIG_ERROR,
                "R2 retry_base_seconds must be between 0 and 30",
                value=retry_base_seconds,
            )
        self.bucket = bucket
        self.prefix = _normalize_prefix(prefix)
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self._sleep = sleeper
        self.account_id = account_id
        self.endpoint_url = endpoint_url or (
            f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
        )
        if client is None:
            if not self.endpoint_url or not access_key_id or not secret_access_key:
                _fail(
                    PUBLISH_CONFIG_ERROR,
                    "R2 S3 credentials are incomplete",
                    missing="R2 endpoint or S3 access credentials",
                )
            try:
                import boto3
            except ImportError as exc:
                raise ResourceIndexError(
                    PUBLISH_CONFIG_ERROR,
                    "boto3 is required for the R2 publisher",
                    {"install": "deploy/resource-index/requirements.txt"},
                ) from exc
            client = boto3.client(
                service_name="s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                aws_session_token=session_token,
                region_name="auto",
            )
        self._client = client

    def _call(self, operation: str, callback: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return callback()
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_attempts or not _is_retryable(exc):
                    raise
                self._sleep(self.retry_base_seconds * (2 ** (attempt - 1)))
        raise RuntimeError(f"unreachable retry state for {operation}") from last_error

    @classmethod
    def from_environment(
        cls,
        *,
        bucket: str,
        prefix: str = "",
        client: Any | None = None,
    ) -> "R2PublisherBackend":
        return cls(
            bucket=bucket,
            prefix=prefix,
            account_id=os.environ.get("R2_ACCOUNT_ID"),
            access_key_id=os.environ.get("R2_ACCESS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY")
            or os.environ.get("AWS_SECRET_ACCESS_KEY"),
            session_token=os.environ.get("R2_SESSION_TOKEN") or os.environ.get("AWS_SESSION_TOKEN"),
            endpoint_url=os.environ.get("R2_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL"),
            client=client,
        )

    @property
    def name(self) -> str:
        return "r2"

    @property
    def destination(self) -> str:
        suffix = f"/{self.prefix}" if self.prefix else ""
        return f"r2://{self.bucket}{suffix}"

    def _remote_key(self, key: str) -> str:
        normalized = _validate_key(key)
        return f"{self.prefix}/{normalized}" if self.prefix else normalized

    def healthcheck(self) -> None:
        try:
            self._call("HeadBucket", lambda: self._client.head_bucket(Bucket=self.bucket))
        except Exception as exc:
            _fail(
                PUBLISH_REMOTE_ERROR,
                "R2 bucket healthcheck failed",
                bucket=self.bucket,
                status=_error_status(exc),
                remote_code=_error_code(exc),
            )

    def head(self, key: str) -> PublishedObject | None:
        remote_key = self._remote_key(key)
        try:
            response = self._call(
                "HeadObject",
                lambda: self._client.head_object(Bucket=self.bucket, Key=remote_key),
            )
        except Exception as exc:
            if _is_not_found(exc):
                return None
            _fail(
                PUBLISH_REMOTE_ERROR,
                "R2 HeadObject failed",
                bucket=self.bucket,
                key=remote_key,
                status=_error_status(exc),
                remote_code=_error_code(exc),
            )
        metadata = _metadata(response)
        size = response.get("ContentLength")
        if type(size) is not int or size < 0:
            _fail(PUBLISH_REMOTE_ERROR, "R2 HeadObject returned an invalid size", key=remote_key)
        etag = response.get("ETag")
        return PublishedObject(
            key=remote_key,
            size=size,
            sha256=metadata.get("sha256"),
            etag=str(etag).strip('"') if etag is not None else None,
            metadata=metadata,
        )

    def verify(self, request: UploadRequest, *, deep: bool = True) -> PublishedObject:
        published = self.head(request.key)
        remote_key = self._remote_key(request.key)
        if published is None:
            _fail(PUBLISH_VERIFICATION_FAILED, "R2 object is missing", key=remote_key)
        if published.size != request.size:
            _fail(
                PUBLISH_VERIFICATION_FAILED,
                "R2 object size verification failed",
                key=remote_key,
                expected=request.size,
                actual=published.size,
            )
        if published.sha256 != request.sha256:
            _fail(
                PUBLISH_VERIFICATION_FAILED,
                "R2 object SHA-256 metadata verification failed",
                key=remote_key,
                expected=request.sha256,
                actual=published.sha256,
            )
        if deep:
            try:
                response = self._call(
                    "GetObject",
                    lambda: self._client.get_object(Bucket=self.bucket, Key=remote_key),
                )
                body = response.get("Body") if isinstance(response, Mapping) else None
                if body is None:
                    _fail(PUBLISH_REMOTE_ERROR, "R2 GetObject returned no body", key=remote_key)
                actual_hash = _stream_sha256(body)
            except ResourceIndexError:
                raise
            except Exception as exc:
                _fail(
                    PUBLISH_REMOTE_ERROR,
                    "R2 GetObject failed during deep verification",
                    key=remote_key,
                    status=_error_status(exc),
                    remote_code=_error_code(exc),
                )
            if actual_hash != request.sha256:
                _fail(
                    PUBLISH_VERIFICATION_FAILED,
                    "R2 object body SHA-256 verification failed",
                    key=remote_key,
                    expected=request.sha256,
                    actual=actual_hash,
                )
        return published

    def upload(self, request: UploadRequest, *, deep_verify: bool = True) -> UploadOutcome:
        if not request.immutable:
            _fail(PUBLISH_CONFIG_ERROR, "M2 only accepts immutable upload requests", key=request.key)
        if request.key == "v1/current.json":
            _validate_key(request.key)
        if not request.source_path.is_file():
            _fail(PUBLISH_CONFIG_ERROR, "local publish source is missing", path=str(request.source_path))
        actual_size = request.source_path.stat().st_size
        actual_hash = sha256_file(request.source_path)
        if actual_size != request.size or actual_hash != request.sha256:
            _fail(
                PUBLISH_VERIFICATION_FAILED,
                "local publish source changed after release verification",
                path=str(request.source_path),
                expected_size=request.size,
                actual_size=actual_size,
                expected_hash=request.sha256,
                actual_hash=actual_hash,
            )

        existing = self.head(request.key)
        if existing is not None:
            if existing.size != request.size or existing.sha256 != request.sha256:
                _fail(
                    PUBLISH_CONFLICT,
                    "immutable R2 key already exists with different content",
                    key=existing.key,
                    expected_size=request.size,
                    actual_size=existing.size,
                    expected_hash=request.sha256,
                    actual_hash=existing.sha256,
                )
            verified = self.verify(request, deep=deep_verify)
            return UploadOutcome(
                object=verified,
                uploaded=False,
                reused=True,
                deep_verified=deep_verify,
            )

        remote_key = self._remote_key(request.key)
        metadata = {
            "sha256": request.sha256,
            "release-id": request.release_id,
            "object-kind": request.object_kind,
        }
        def put_once() -> Any:
            with request.source_path.open("rb") as handle:
                # Do not use ChecksumSHA256: R2 exposes SHA-256 as a composite
                # multipart checksum, not a full-object PutObject checksum.
                return self._client.put_object(
                    Bucket=self.bucket,
                    Key=remote_key,
                    Body=handle,
                    ContentLength=request.size,
                    ContentType=request.content_type,
                    CacheControl=request.cache_control,
                    Metadata=metadata,
                    IfNoneMatch="*",
                )

        try:
            self._call("PutObject", put_once)
        except Exception as exc:
            if _error_status(exc) == 412 or _error_code(exc) == "PreconditionFailed":
                raced = self.head(request.key)
                if raced is not None and raced.size == request.size and raced.sha256 == request.sha256:
                    verified = self.verify(request, deep=deep_verify)
                    return UploadOutcome(
                        object=verified,
                        uploaded=False,
                        reused=True,
                        deep_verified=deep_verify,
                    )
                _fail(
                    PUBLISH_CONFLICT,
                    "conditional immutable R2 upload lost to different content",
                    key=remote_key,
                    expected_size=request.size,
                    actual_size=raced.size if raced else None,
                    expected_hash=request.sha256,
                    actual_hash=raced.sha256 if raced else None,
                )
            _fail(
                PUBLISH_REMOTE_ERROR,
                "R2 PutObject failed",
                bucket=self.bucket,
                key=remote_key,
                status=_error_status(exc),
                remote_code=_error_code(exc),
            )
        verified = self.verify(request, deep=deep_verify)
        return UploadOutcome(
            object=verified,
            uploaded=True,
            reused=False,
            deep_verified=deep_verify,
        )
