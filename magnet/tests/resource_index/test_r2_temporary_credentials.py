from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from magnet.resource_index.cli import main as cli_main
from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.publish.temporary_credentials import (
    TemporaryR2Credentials,
    mint_temporary_r2_credentials,
    mint_temporary_r2_credentials_from_environment,
)


class FakeResponse:
    def __init__(self, document: object) -> None:
        self.payload = json.dumps(document).encode("utf-8")

    def read(self) -> bytes:
        return self.payload


def test_mints_prefix_scoped_short_lived_credentials_without_exposing_values() -> None:
    captured: dict[str, Any] = {}

    def opener(request: Any, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "success": True,
                "result": {
                    "accessKeyId": "temporary-access-id",
                    "secretAccessKey": "temporary-secret-value",
                    "sessionToken": "temporary-session-token",
                },
            }
        )

    credentials = mint_temporary_r2_credentials(
        account_id="9490b95301e1a3e27b3ca2bf1c848f6d",
        api_token="parent-api-token",
        parent_access_key_id="parent-access-id",
        bucket="magnetgoogo-media-m2-test",
        prefix="m2-test/full-run",
        ttl_seconds=600,
        open_url=opener,
    )

    assert credentials.access_key_id == "temporary-access-id"
    assert credentials.secret_access_key == "temporary-secret-value"
    assert credentials.session_token == "temporary-session-token"
    assert credentials.prefix == "m2-test/full-run/"
    assert captured["body"] == {
        "bucket": "magnetgoogo-media-m2-test",
        "parentAccessKeyId": "parent-access-id",
        "permission": "object-read-write",
        "ttlSeconds": 600,
        "prefixes": ["m2-test/full-run/"],
    }
    assert captured["headers"]["Authorization"] == "Bearer parent-api-token"
    representation = repr(credentials)
    assert "temporary-access-id" not in representation
    assert "temporary-secret-value" not in representation
    assert "temporary-session-token" not in representation
    assert "<redacted>" in representation


def test_rejects_non_test_prefix_and_excessive_ttl() -> None:
    base = {
        "account_id": "9490b95301e1a3e27b3ca2bf1c848f6d",
        "api_token": "parent-api-token",
        "parent_access_key_id": "parent-access-id",
        "bucket": "magnetgoogo-media-m2-test",
    }
    with pytest.raises(ResourceIndexError, match="m2-test prefix"):
        mint_temporary_r2_credentials(**base, prefix="production/v1", open_url=lambda *_: None)
    with pytest.raises(ResourceIndexError, match="between 60 and 3600"):
        mint_temporary_r2_credentials(
            **base,
            prefix="m2-test/full-run",
            ttl_seconds=7200,
            open_url=lambda *_: None,
        )


def test_api_failures_never_echo_parent_or_child_secrets() -> None:
    def rejected(_request: Any, _timeout: float) -> Any:
        raise urllib.error.HTTPError(
            url="https://api.cloudflare.com",
            code=403,
            msg="forbidden parent-api-token child-secret",
            hdrs=None,
            fp=io.BytesIO(b'{"errors":[{"message":"child-secret"}]}'),
        )

    with pytest.raises(ResourceIndexError) as error:
        mint_temporary_r2_credentials(
            account_id="9490b95301e1a3e27b3ca2bf1c848f6d",
            api_token="parent-api-token",
            parent_access_key_id="parent-access-id",
            bucket="magnetgoogo-media-m2-test",
            prefix="m2-test/full-run",
            open_url=rejected,
        )
    rendered = f"{error.value.message} {error.value.context}"
    assert "parent-api-token" not in rendered
    assert "child-secret" not in rendered
    assert error.value.context == {"status": 403}


def test_unsuccessful_response_records_only_error_codes() -> None:
    def opener(_request: Any, _timeout: float) -> FakeResponse:
        return FakeResponse(
            {
                "success": False,
                "errors": [{"code": 10000, "message": "secret-value"}],
                "result": {"secretAccessKey": "must-not-leak"},
            }
        )

    with pytest.raises(ResourceIndexError) as error:
        mint_temporary_r2_credentials(
            account_id="9490b95301e1a3e27b3ca2bf1c848f6d",
            api_token="parent-api-token",
            parent_access_key_id="parent-access-id",
            bucket="magnetgoogo-media-m2-test",
            prefix="m2-test/full-run",
            open_url=opener,
        )
    assert error.value.context == {"error_codes": [10000]}
    assert "secret-value" not in str(error.value.context)
    assert "must-not-leak" not in str(error.value.context)


def test_environment_loader_requires_parent_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("R2_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "R2_PARENT_ACCESS_KEY_ID"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ResourceIndexError, match="invalid Cloudflare account ID"):
        mint_temporary_r2_credentials_from_environment(
            bucket="magnetgoogo-media-m2-test",
            prefix="m2-test/full-run",
        )


def test_temporary_credentials_dataclass_repr_is_always_redacted() -> None:
    value = TemporaryR2Credentials(
        access_key_id="id",
        secret_access_key="secret",
        session_token="session",
        ttl_seconds=900,
        bucket="magnetgoogo-media-m2-test",
        prefix="m2-test/full-run/",
    )
    assert repr(value).count("<redacted>") == 3


def test_cli_uses_minted_credentials_only_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    import magnet.resource_index.publish.orchestrator as orchestrator_module
    import magnet.resource_index.publish.r2 as r2_module
    import magnet.resource_index.publish.temporary_credentials as temporary_module

    captured: dict[str, Any] = {}
    temporary = TemporaryR2Credentials(
        access_key_id="child-id",
        secret_access_key="child-secret",
        session_token="child-session",
        ttl_seconds=300,
        bucket="magnetgoogo-media-m2-test",
        prefix="m2-test/cli/",
    )

    monkeypatch.setattr(
        temporary_module,
        "mint_temporary_r2_credentials_from_environment",
        lambda **kwargs: captured.setdefault("mint", kwargs) and temporary,
    )

    class FakeBackend:
        def __init__(self, **kwargs: Any) -> None:
            captured["backend"] = kwargs

    monkeypatch.setattr(r2_module, "R2PublisherBackend", FakeBackend)
    monkeypatch.setattr(
        orchestrator_module,
        "publish_media_release",
        lambda backend, config: type(
            "Result",
            (),
            {
                "__dict__": {
                    "status": "success",
                    "backend": "r2",
                    "destination": "r2://test",
                    "release_id": "release",
                    "pointer_revision": 1,
                    "object_count": 0,
                    "uploaded_count": 0,
                    "reused_count": 0,
                    "manifest_uploaded": False,
                    "pointer_uploaded": False,
                    "current_promoted": False,
                    "receipt_path": "receipt.json",
                }
            },
        )(),
    )
    monkeypatch.setenv("R2_ACCOUNT_ID", "9490b95301e1a3e27b3ca2bf1c848f6d")

    code = cli_main(
        [
            "publish-media-r2-staging",
            "--release-dir",
            "unused-release",
            "--current",
            "unused-current",
            "--prefix",
            "m2-test/cli",
            "--temporary-credentials",
            "--credential-ttl-seconds",
            "300",
            "--yes",
        ]
    )
    assert code == 0
    assert captured["mint"]["ttl_seconds"] == 300
    assert captured["backend"]["access_key_id"] == "child-id"
    assert captured["backend"]["secret_access_key"] == "child-secret"
    assert captured["backend"]["session_token"] == "child-session"
