"""Live page acquisition for resource_index."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

from magnet.resource_index.acquisition.http_client import LiveHttpClient
from magnet.resource_index.acquisition.policy import LiveFetchPolicy, PhysicalRequestBudget
from magnet.resource_index.domain.enums import DocumentType
from magnet.resource_index.domain.identity import document_id_for
from magnet.resource_index.domain.models import RawDocumentEnvelope


class LiveFetcher:
    """Policy-gated fetcher producing RawDocumentEnvelope objects."""

    def __init__(
        self,
        policy: LiveFetchPolicy,
        *,
        client: LiveHttpClient | None = None,
        source_id: str = "javbus",
        request_budget: PhysicalRequestBudget | None = None,
        allowed_origins: set[str] | None = None,
    ) -> None:
        self.policy = policy
        self.source_id = source_id
        self.request_budget = request_budget or PhysicalRequestBudget(policy.max_pages)
        self.client = client or LiveHttpClient(
            request_delay_seconds=policy.request_delay_seconds,
            request_budget=self.request_budget,
            allowed_origins=allowed_origins,
        )
        if getattr(self.client, "manages_request_budget", False):
            self.client.set_request_budget(self.request_budget)

    @property
    def _pages_fetched(self) -> int:
        return self.request_budget.used

    def assert_enabled(self) -> None:
        self.policy.assert_allowed()

    def cookies_snapshot(self) -> dict[str, str]:
        return self.client.cookies_snapshot()

    def clear_cookies(self) -> None:
        self.client.clear_cookies()

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
        allow_age_gate: bool = False,
    ) -> RawDocumentEnvelope:
        self.assert_enabled()
        if count_against_budget and not getattr(
            self.client, "manages_request_budget", False
        ):
            self.request_budget.consume(url_host=urlparse(url).netloc)
        if method.upper() == "POST":
            resp = self.client.post(
                url,
                data=data,
                referer=referer,
                headers=headers,
                allow_age_gate=allow_age_gate,
            )
        else:
            resp = self.client.get(
                url,
                referer=referer,
                headers=headers,
                allow_age_gate=allow_age_gate,
            )
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
