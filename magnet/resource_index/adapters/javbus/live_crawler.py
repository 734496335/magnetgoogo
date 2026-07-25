"""JavBus live crawl: age session → search/listing → detail → AJAX magnets."""

from __future__ import annotations

import random
from dataclasses import dataclass
from urllib.parse import urljoin

from magnet.resource_index.acquisition.http_client import (
    LiveHttpClient,
    normalized_origin,
    validate_live_url,
)
from magnet.resource_index.acquisition.live_fetcher import LiveFetcher, search_url
from magnet.resource_index.acquisition.policy import LiveFetchPolicy, PhysicalRequestBudget
from magnet.resource_index.adapters.javbus import selectors as sel
from magnet.resource_index.adapters.javbus.adapter import JavBusAdapter
from magnet.resource_index.domain.enums import DocumentType
from magnet.resource_index.domain.models import (
    ContentCandidate,
    ParsedContentBundle,
    RawDocumentEnvelope,
)
from magnet.resource_index.errors import (
    AGE_GATE_PAGE,
    CONFIG_ERROR,
    ParseError,
    ResourceIndexError,
)
from magnet.resource_index.pipeline.reconcile import attach_resources


@dataclass
class CrawlItemResult:
    content_code: str | None
    detail_url: str
    bundle: ParsedContentBundle | None
    error_code: str | None = None
    error_message: str | None = None


class JavBusLiveCrawler:
    """Single-source JavBus crawler with explicit policy and source URL fencing."""

    source_id = sel.SOURCE_ID

    def __init__(
        self,
        *,
        policy: LiveFetchPolicy | None = None,
        origin: str = sel.ORIGIN,
        client: LiveHttpClient | None = None,
    ) -> None:
        self.origin = origin.rstrip("/")
        self._allowed_origins = {normalized_origin(self.origin)}
        self.policy = policy or LiveFetchPolicy.from_flags()
        request_budget = PhysicalRequestBudget(self.policy.max_pages)
        self.client = client or LiveHttpClient(
            request_delay_seconds=self.policy.request_delay_seconds,
            allowed_origins=self._allowed_origins,
            request_budget=request_budget,
        )
        if getattr(self.client, "manages_request_budget", False):
            self.client.allowed_origins = set(self._allowed_origins)
        self.fetcher = LiveFetcher(
            self.policy,
            client=self.client,
            source_id=self.source_id,
            request_budget=request_budget,
        )
        self.adapter = JavBusAdapter()
        self._session_ready = False

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if limit <= 0:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "limit must be positive",
                {"limit": limit},
            )

    def _source_url(self, raw_url: str) -> str:
        url = raw_url if raw_url.startswith(("http://", "https://")) else urljoin(
            self.origin + "/", raw_url
        )
        validate_live_url(url, allowed_origins=self._allowed_origins)
        return url

    def ensure_session(self) -> None:
        """Bootstrap age verification cookie once per in-memory session."""
        if self._session_ready:
            return
        self.policy.assert_allowed()
        home = self.fetcher.fetch_document(
            self.origin + "/",
            document_type=DocumentType.OTHER,
            allow_age_gate=True,
        )
        body_l = home.body.lower()
        needs_verify = any(
            marker.lower() in body_l or marker in home.body
            for marker in sel.AGE_GATE_MARKERS
        ) or "age verification" in body_l
        if "movie-box" in home.body and not needs_verify:
            self._session_ready = True
            return
        if needs_verify or "driver-verify" in home.source_url:
            verify_url = self._source_url(home.source_url)
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
                allow_age_gate=True,
            )
        check = self.fetcher.fetch_document(
            self.origin + "/",
            document_type=DocumentType.LISTING,
        )
        if "movie-box" not in check.body and any(
            marker.lower() in check.body.lower()
            for marker in ("age verification", "driver-verify")
        ):
            raise ParseError(AGE_GATE_PAGE, "age gate not cleared after verify POST", {})
        self._session_ready = True

    def crawl_query(self, query: str, *, limit: int = 6) -> list[CrawlItemResult]:
        self._validate_limit(limit)
        if not query.strip():
            raise ResourceIndexError(CONFIG_ERROR, "query must not be empty", {})
        self.ensure_session()
        url = self._source_url(search_url(self.origin, query.strip()))
        listing_doc = self.fetcher.fetch_document(
            url,
            document_type=DocumentType.LISTING,
            referer=self.origin + "/",
        )
        candidates = self.adapter.parse_listing(listing_doc)
        detail_urls = [candidate.detail_url for candidate in candidates[:limit]]
        return self.crawl_detail_urls(detail_urls)

    def crawl_latest_candidates(
        self,
        *,
        limit: int,
        max_listing_pages: int = 20,
    ) -> list[ContentCandidate]:
        self._validate_limit(limit)
        if max_listing_pages <= 0:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "max_listing_pages must be positive",
                {"max_listing_pages": max_listing_pages},
            )
        self.ensure_session()
        candidates = []
        seen_urls: set[str] = set()
        for page in range(1, max_listing_pages + 1):
            page_url = self.origin + "/" if page == 1 else f"{self.origin}/page/{page}"
            listing_doc = self.fetcher.fetch_document(
                self._source_url(page_url),
                document_type=DocumentType.LISTING,
                referer=self.origin + "/",
            )
            page_candidates = self.adapter.parse_listing(listing_doc)
            if not page_candidates:
                break
            added = 0
            for candidate in page_candidates:
                detail_url = self._source_url(candidate.detail_url)
                if detail_url in seen_urls:
                    continue
                seen_urls.add(detail_url)
                candidates.append(candidate)
                added += 1
                if len(candidates) >= limit:
                    return candidates
            if added == 0:
                break
        return candidates

    def crawl_listing_page(
        self,
        page_url: str | None = None,
        *,
        limit: int = 12,
    ) -> list[CrawlItemResult]:
        self._validate_limit(limit)
        url = self._source_url(page_url or (self.origin + "/"))
        self.ensure_session()
        listing_doc = self.fetcher.fetch_document(
            url,
            document_type=DocumentType.LISTING,
            referer=self.origin + "/",
        )
        candidates = self.adapter.parse_listing(listing_doc)
        detail_urls = [candidate.detail_url for candidate in candidates[:limit]]
        return self.crawl_detail_urls(detail_urls)

    def crawl_detail_urls(self, detail_urls: list[str]) -> list[CrawlItemResult]:
        validated_urls = [self._source_url(raw_url) for raw_url in detail_urls]
        if not validated_urls:
            return []
        self.ensure_session()
        results: list[CrawlItemResult] = []
        for detail_url in validated_urls:
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
            except Exception as exc:  # isolate one item from the rest of the batch
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
        detail_url = self._source_url(detail_url)
        detail_doc = self.fetcher.fetch_document(
            detail_url,
            document_type=DocumentType.DETAIL,
            referer=self.origin + "/",
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

    def _fetch_resource_table(
        self,
        detail_doc: RawDocumentEnvelope,
    ) -> RawDocumentEnvelope | None:
        descriptor = self.adapter.derive_resource_request(detail_doc)
        if descriptor is None:
            return None
        gid = descriptor.query.get("gid")
        uc = descriptor.query.get("uc", "0")
        if not gid:
            return None
        floor = random.randint(1, 1000)
        ajax_url = self._source_url(
            f"{self.origin}/ajax/uncledatoolsbyajax.php"
            f"?gid={gid}&lang=zh&uc={uc}&floor={floor}"
        )
        return self.fetcher.fetch_document(
            ajax_url,
            document_type=DocumentType.RESOURCE_TABLE,
            referer=detail_doc.source_url,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
