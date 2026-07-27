"""Short-lived, prefix-scoped Cloudflare R2 S3 credentials.

The parent API token and parent access key are read from environment variables.
Returned child credentials remain in memory and must never be serialized.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from magnet.resource_index.errors import (
    PUBLISH_CONFIG_ERROR,
    PUBLISH_REMOTE_ERROR,
    ResourceIndexError,
)

_ACCOUNT_ID = re.compile(r"^[0-9a-f]{32}$")
_BUCKET = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")


def _fail(error_code: str, message: str, **context: Any) -> None:
    raise ResourceIndexError(error_code, message, context)


def _safe_prefix(prefix: str) -> str:
    value = prefix.strip().replace("\\", "/").strip("/")
    if not value.startswith("m2-test"):
        _fail(
            PUBLISH_CONFIG_ERROR,
            "temporary R2 credentials must be restricted to an m2-test prefix",
            prefix=prefix,
        )
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        _fail(PUBLISH_CONFIG_ERROR, "temporary R2 credential prefix is unsafe", prefix=prefix)
    return value + "/"


@dataclass(frozen=True, repr=False)
class TemporaryR2Credentials:
    access_key_id: str
    secret_access_key: str
    session_token: str
    ttl_seconds: int
    bucket: str
    prefix: str

    def __repr__(self) -> str:
        return (
            "TemporaryR2Credentials(access_key_id=<redacted>, "
            "secret_access_key=<redacted>, session_token=<redacted>, "
            f"ttl_seconds={self.ttl_seconds}, bucket={self.bucket!r}, prefix={self.prefix!r})"
        )


OpenUrl = Callable[[urllib.request.Request, float], Any]


def _default_open(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


def mint_temporary_r2_credentials(
    *,
    account_id: str,
    api_token: str,
    parent_access_key_id: str,
    bucket: str,
    prefix: str,
    ttl_seconds: int = 900,
    timeout_seconds: float = 20.0,
    open_url: OpenUrl = _default_open,
) -> TemporaryR2Credentials:
    """Mint one object-read-write credential restricted to a test prefix."""

    normalized_account = account_id.strip().lower()
    if not _ACCOUNT_ID.fullmatch(normalized_account):
        _fail(PUBLISH_CONFIG_ERROR, "invalid Cloudflare account ID")
    if not _BUCKET.fullmatch(bucket):
        _fail(PUBLISH_CONFIG_ERROR, "invalid R2 bucket name", bucket=bucket)
    normalized_prefix = _safe_prefix(prefix)
    if not api_token.strip() or not parent_access_key_id.strip():
        _fail(PUBLISH_CONFIG_ERROR, "parent R2 credential inputs are incomplete")
    if ttl_seconds < 60 or ttl_seconds > 3600:
        _fail(
            PUBLISH_CONFIG_ERROR,
            "temporary R2 credential TTL must be between 60 and 3600 seconds",
            ttl_seconds=ttl_seconds,
        )
    if timeout_seconds <= 0 or timeout_seconds > 60:
        _fail(PUBLISH_CONFIG_ERROR, "temporary credential API timeout is invalid")

    payload = json.dumps(
        {
            "bucket": bucket,
            "parentAccessKeyId": parent_access_key_id,
            "permission": "object-read-write",
            "ttlSeconds": ttl_seconds,
            "prefixes": [normalized_prefix],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{normalized_account}/r2/temp-access-credentials",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        response = open_url(request, timeout_seconds)
        raw = response.read()
    except urllib.error.HTTPError as exc:
        _fail(
            PUBLISH_REMOTE_ERROR,
            "Cloudflare temporary credential API rejected the request",
            status=exc.code,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _fail(
            PUBLISH_REMOTE_ERROR,
            "Cloudflare temporary credential API request failed",
            error_type=type(exc).__name__,
        )

    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(PUBLISH_REMOTE_ERROR, "Cloudflare temporary credential API returned invalid JSON")
    if not isinstance(document, Mapping) or document.get("success") is not True:
        error_codes: list[int | str] = []
        errors = document.get("errors") if isinstance(document, Mapping) else None
        if isinstance(errors, list):
            for error in errors:
                if isinstance(error, Mapping) and error.get("code") is not None:
                    error_codes.append(error["code"])
        _fail(
            PUBLISH_REMOTE_ERROR,
            "Cloudflare temporary credential API returned an unsuccessful response",
            error_codes=error_codes[:5],
        )
    result = document.get("result")
    if not isinstance(result, Mapping):
        _fail(PUBLISH_REMOTE_ERROR, "Cloudflare temporary credential API omitted its result")
    access_key_id = result.get("accessKeyId")
    secret_access_key = result.get("secretAccessKey")
    session_token = result.get("sessionToken")
    if not all(isinstance(value, str) and value for value in (access_key_id, secret_access_key, session_token)):
        _fail(PUBLISH_REMOTE_ERROR, "Cloudflare temporary credential response is incomplete")

    return TemporaryR2Credentials(
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        session_token=session_token,
        ttl_seconds=ttl_seconds,
        bucket=bucket,
        prefix=normalized_prefix,
    )


def mint_temporary_r2_credentials_from_environment(
    *,
    bucket: str,
    prefix: str,
    ttl_seconds: int = 900,
    open_url: OpenUrl = _default_open,
) -> TemporaryR2Credentials:
    return mint_temporary_r2_credentials(
        account_id=os.environ.get("R2_ACCOUNT_ID", ""),
        api_token=os.environ.get("CLOUDFLARE_API_TOKEN", ""),
        parent_access_key_id=os.environ.get("R2_PARENT_ACCESS_KEY_ID", ""),
        bucket=bucket,
        prefix=prefix,
        ttl_seconds=ttl_seconds,
        open_url=open_url,
    )
