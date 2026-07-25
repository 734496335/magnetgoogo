"""Live page acquisition for resource_index (real HTTP via LiveHttpClient)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import quote

from magnet.resource_index.acquisition.http_client import LiveHttpClient
from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.domain.enums import DocumentType
from magnet.resource_index.domain.identity import document_id_for
from magnet.resource_index.domain.models import RawDocumentEnvelope
from magnet.resource_index.errors import LIVE_FETCH_DISABLED, LivePolicyError


class LiveFetcher:
    """Policy-gated HTTP fetcher producing RawDocumentEnvelope objects."""

    def __init__(
        self,
        policy: LiveFetchPolicy,
        *,
        client: LiveHttpClient | None = None,
        source_id: str = "javbus",
    ) -> None:
        self.policy = policy
        self.source_id = source_id
        self.client = client or LiveHttpClient(
            request_delay_seconds=policy.request_delay_seconds,
        )
        self._pages_fetched = 0

    def assert_enabled(self) -> None:
        self.policy.assert_allowed()

    def cookies_snapshot(self) -> dict[str, str]:
        return self.client.cookies_snapshot()

    def clear_cookies(self) -> None:
        self.client.clear_cookies()

    def _budget(self) -> None:
        if self._pages_fetched >= self.policy.max_pages:
            raise LivePolicyError(
                LIVE_FETCH_DISABLED,
                f"max_pages budget exhausted ({self.policy.max_pages})",
                {"max_pages": self.policy.max_pages},
            )

    def fetch_document(
        self,
        url: str,
        *,
        document_type: DocumentType,
        method: str = "GET",
        data: str | None = None,
        referer: str | None = None,
        headers: dict[str, str] | None = None,
        count_against_budget: bool = True,
    ) -> RawDocumentEnvelope:
        self.assert_enabled()
        if count_against_budget:
            self._budget()
        if method.upper() == "POST":
            resp = self.client.post(url, data=data, referer=referer, headers=headers)
        else:
            resp = self.client.get(url, referer=referer, headers=headers)
        if count_against_budget:
            self._pages_fetched += 1
        body = resp.text
        body_hash = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
        return RawDocumentEnvelope(
            document_id=document_id_for(self.source_id, str(resp.url), body_hash),
            source_id=self.source_id,
            document_type=document_type,
            source_url=str(resp.url),
            captured_at=datetime.now(timezone.utc),
            status_code=resp.status_code,
            content_type=resp.headers.get("content-type", "text/html"),
            encoding="utf-8",
            sha256=body_hash,
            body=body,
            fixture_name=None,
            sanitized=False,
        )


def search_url(origin: str, query: str) -> str:
    return f"{origin.rstrip('/')}/search/{quote(query, safe='')}"
