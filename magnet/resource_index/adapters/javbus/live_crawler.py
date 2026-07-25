"""JavBus live crawl: age session → search/listing → detail → AJAX magnets."""

from __future__ import annotations

import random
from dataclasses import dataclass
from urllib.parse import urljoin

from magnet.resource_index.acquisition.http_client import LiveHttpClient
from magnet.resource_index.acquisition.live_fetcher import LiveFetcher, search_url
from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.javbus import selectors as sel
from magnet.resource_index.adapters.javbus.adapter import JavBusAdapter
from magnet.resource_index.domain.enums import DocumentType
from magnet.resource_index.domain.models import ParsedContentBundle, RawDocumentEnvelope
from magnet.resource_index.errors import AGE_GATE_PAGE, ParseError, ResourceIndexError
from magnet.resource_index.pipeline.reconcile import attach_resources


@dataclass
class CrawlItemResult:
    content_code: str | None
    detail_url: str
    bundle: ParsedContentBundle | None
    error_code: str | None = None
    error_message: str | None = None


class JavBusLiveCrawler:
    """Stable single-source live crawler for javbus.com."""

    source_id = sel.SOURCE_ID

    def __init__(
        self,
        *,
        policy: LiveFetchPolicy | None = None,
        origin: str = sel.ORIGIN,
        client: LiveHttpClient | None = None,
    ) -> None:
        self.origin = origin.rstrip("/")
        self.policy = policy or LiveFetchPolicy.from_flags(
            env_enabled=True,
            acknowledged=True,
            max_pages=50,
            request_delay_seconds=1.5,
        )
        self.client = client or LiveHttpClient(
            request_delay_seconds=self.policy.request_delay_seconds,
        )
        self.fetcher = LiveFetcher(
            self.policy,
            client=self.client,
            source_id=self.source_id,
        )
        self.adapter = JavBusAdapter()
        self._session_ready = False

    def ensure_session(self) -> None:
        """Bootstrap age verification cookie (idempotent)."""
        if self._session_ready:
            return
        home = self.fetcher.fetch_document(
            self.origin + "/",
            document_type=DocumentType.OTHER,
            count_against_budget=False,
        )
        body_l = home.body.lower()
        needs_verify = any(
            m.lower() in body_l or m in home.body for m in sel.AGE_GATE_MARKERS
        ) or "age verification" in body_l
        # If already past gate (movie-box present), skip POST
        if "movie-box" in home.body and not needs_verify:
            self._session_ready = True
            return
        if needs_verify or "driver-verify" in home.source_url or "Age Verification" in home.body:
            verify_url = home.source_url
            # Web handler: POST Submit=確認 on verify page
            self.fetcher.fetch_document(
                verify_url,
                document_type=DocumentType.OTHER,
                method="POST",
                data="Submit=%E7%A2%BA%E8%AA%8D",
                referer=verify_url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.origin,
                },
                count_against_budget=False,
            )
        # Confirm listing works
        check = self.fetcher.fetch_document(
            self.origin + "/",
            document_type=DocumentType.LISTING,
            count_against_budget=False,
        )
        if "movie-box" not in check.body and any(
            m.lower() in check.body.lower() for m in ("age verification", "driver-verify")
        ):
            raise ParseError(AGE_GATE_PAGE, "age gate not cleared after verify POST", {})
        self._session_ready = True

    def crawl_query(self, query: str, *, limit: int = 6) -> list[CrawlItemResult]:
        self.ensure_session()
        url = search_url(self.origin, query)
        listing_doc = self.fetcher.fetch_document(
            url,
            document_type=DocumentType.LISTING,
            referer=self.origin + "/",
            count_against_budget=True,
        )
        candidates = self.adapter.parse_listing(listing_doc)
        detail_urls = [c.detail_url for c in candidates[: max(1, limit)]]
        return self.crawl_detail_urls(detail_urls)

    def crawl_listing_page(self, page_url: str | None = None, *, limit: int = 12) -> list[CrawlItemResult]:
        self.ensure_session()
        url = page_url or (self.origin + "/")
        listing_doc = self.fetcher.fetch_document(
            url,
            document_type=DocumentType.LISTING,
            referer=self.origin + "/",
            count_against_budget=True,
        )
        candidates = self.adapter.parse_listing(listing_doc)
        detail_urls = [c.detail_url for c in candidates[: max(1, limit)]]
        return self.crawl_detail_urls(detail_urls)

    def crawl_detail_urls(self, detail_urls: list[str]) -> list[CrawlItemResult]:
        self.ensure_session()
        results: list[CrawlItemResult] = []
        for raw_url in detail_urls:
            detail_url = raw_url if raw_url.startswith("http") else urljoin(self.origin + "/", raw_url)
            try:
                results.append(self._crawl_one_detail(detail_url))
            except ResourceIndexError as exc:
                results.append(
                    CrawlItemResult(
                        content_code=None,
                        detail_url=detail_url,
                        bundle=None,
                        error_code=exc.error_code,
                        error_message=exc.message,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - isolate per item
                results.append(
                    CrawlItemResult(
                        content_code=None,
                        detail_url=detail_url,
                        bundle=None,
                        error_code="UNEXPECTED",
                        error_message=str(exc),
                    )
                )
        return results

    def _crawl_one_detail(self, detail_url: str) -> CrawlItemResult:
        detail_doc = self.fetcher.fetch_document(
            detail_url,
            document_type=DocumentType.DETAIL,
            referer=self.origin + "/",
            count_against_budget=True,
        )
        bundle = self.adapter.parse_detail(detail_doc)
        resources_doc = self._fetch_resource_table(detail_doc)
        if resources_doc is not None:
            releases, warnings = self.adapter.parse_resource_table_with_warnings(
                resources_doc,
                content_id=bundle.content.content_id,
                fallback_title=bundle.content.title,
            )
            bundle = attach_resources(
                bundle,
                releases,
                warnings,
                resource_document_sha256=resources_doc.sha256,
            )
        return CrawlItemResult(
            content_code=bundle.content.content_code,
            detail_url=detail_url,
            bundle=bundle,
        )

    def _fetch_resource_table(self, detail_doc: RawDocumentEnvelope) -> RawDocumentEnvelope | None:
        desc = self.adapter.derive_resource_request(detail_doc)
        if desc is None:
            return None
        gid = desc.query.get("gid")
        uc = desc.query.get("uc", "0")
        if not gid:
            return None
        floor = random.randint(1, 1000)
        ajax_url = (
            f"{self.origin}/ajax/uncledatoolsbyajax.php"
            f"?gid={gid}&lang=zh&uc={uc}&floor={floor}"
        )
        return self.fetcher.fetch_document(
            ajax_url,
            document_type=DocumentType.RESOURCE_TABLE,
            referer=detail_doc.source_url,
            headers={"X-Requested-With": "XMLHttpRequest"},
            count_against_budget=True,
        )
