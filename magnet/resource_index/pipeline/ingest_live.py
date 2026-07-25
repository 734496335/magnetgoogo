"""Live ingest pipeline: crawl → parse → transactional upsert."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Callable

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.registry import get_crawler_factory
from magnet.resource_index.domain.enums import IngestMode, IngestRunStatus
from magnet.resource_index.domain.validation import validate_bundle
from magnet.resource_index.errors import (
    CONFIG_ERROR,
    INGEST_CANCELLED,
    LIVE_EMPTY_RESULT,
    ConflictError,
    ResourceIndexError,
)
from magnet.resource_index.pipeline.ingest import IngestResult, default_clock
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

Clock = Callable[[], datetime]


def ingest_live(
    *,
    repo: SqliteResourceRepository,
    source_id: str,
    query: str | None = None,
    detail_urls: list[str] | None = None,
    listing_url: str | None = None,
    limit: int = 6,
    delay_seconds: float = 10.0,
    max_pages: int = 40,
    policy: LiveFetchPolicy | None = None,
    clock: Clock = default_clock,
    run_id: str | None = None,
    stale_run_after_seconds: int = 3600,
) -> IngestResult:
    if limit <= 0:
        raise ResourceIndexError(CONFIG_ERROR, "limit must be positive", {"limit": limit})
    if stale_run_after_seconds <= 0:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "stale_run_after_seconds must be positive",
            {"stale_run_after_seconds": stale_run_after_seconds},
        )

    active_policy = policy or LiveFetchPolicy.from_flags(
        acknowledged=False,
        max_pages=max_pages,
        request_delay_seconds=delay_seconds,
    )
    active_policy.assert_allowed()

    recovery_now = clock()
    repo.recover_stale_ingest_runs(
        stale_before=recovery_now - timedelta(seconds=stale_run_after_seconds),
        recovered_at=recovery_now,
    )

    factory = get_crawler_factory(source_id)
    crawler = factory(policy=active_policy)
    rid = run_id or uuid.uuid4().hex
    repo.start_ingest_run(rid, source_id, IngestMode.LIVE_ONE_SHOT.value, clock())
    result = IngestResult(run_id=rid, status=IngestRunStatus.RUNNING.value)
    summary: dict[str, int] = {}

    def add_code(code: str) -> None:
        summary[code] = summary.get(code, 0) + 1

    try:
        if detail_urls:
            items = crawler.crawl_detail_urls(detail_urls[:limit])
        elif query:
            items = crawler.crawl_query(query, limit=limit)
        else:
            crawl_listing = getattr(crawler, "crawl_listing_page", None)
            if not callable(crawl_listing):
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "listing crawl not supported for this source",
                    {"source_id": source_id},
                )
            items = crawl_listing(listing_url or None, limit=limit)

        result.documents_seen = len(items)
        if not items:
            result.errors += 1
            add_code(LIVE_EMPTY_RESULT)
            repo.add_ingest_event(
                rid,
                occurred_at=clock(),
                stage="crawl",
                severity="error",
                message="live crawl returned no items",
                error_code=LIVE_EMPTY_RESULT,
                context={"source_id": source_id},
            )

        for item in items:
            if item.bundle is None:
                result.errors += 1
                code = item.error_code or "UNEXPECTED"
                add_code(code)
                repo.add_ingest_event(
                    rid,
                    occurred_at=clock(),
                    stage="crawl_item",
                    severity="error",
                    message=item.error_message or "crawl failed",
                    source_item_key=item.detail_url,
                    error_code=code,
                )
                continue

            try:
                validate_bundle(item.bundle)
                stats = repo.upsert_bundle(item.bundle, now=clock())
                if stats.content_created:
                    result.contents_created += 1
                if stats.content_updated:
                    result.contents_updated += 1
                result.resources_created += stats.resources_created
                result.resources_updated += stats.resources_updated
                result.warnings += stats.warnings
                for warning in item.bundle.warnings:
                    add_code(warning.error_code)
                    repo.add_ingest_event(
                        rid,
                        occurred_at=clock(),
                        stage="parse",
                        severity="warning",
                        message=warning.message,
                        source_item_key=item.bundle.content.source_item_key,
                        error_code=warning.error_code,
                        context=warning.context,
                    )
                repo.add_ingest_event(
                    rid,
                    occurred_at=clock(),
                    stage="upsert",
                    severity="info",
                    message=f"ingested {item.bundle.content.content_code}",
                    source_item_key=item.bundle.content.source_item_key,
                )
            except (ConflictError, ResourceIndexError) as exc:
                result.errors += 1
                add_code(exc.error_code)
                repo.add_ingest_event(
                    rid,
                    occurred_at=clock(),
                    stage="upsert",
                    severity="error",
                    message=exc.message,
                    source_item_key=item.detail_url,
                    error_code=exc.error_code,
                    context=exc.context,
                )

        if result.errors and (result.contents_created or result.contents_updated):
            result.status = IngestRunStatus.PARTIAL.value
        elif result.errors:
            result.status = IngestRunStatus.FAILED.value
        else:
            result.status = IngestRunStatus.SUCCESS.value
    except KeyboardInterrupt:
        result.errors += 1
        add_code(INGEST_CANCELLED)
        repo.add_ingest_event(
            rid,
            occurred_at=clock(),
            stage="crawl",
            severity="warning",
            message="live crawl cancelled by user",
            error_code=INGEST_CANCELLED,
        )
        result.status = IngestRunStatus.CANCELLED.value
    except Exception as exc:
        result.errors += 1
        if isinstance(exc, ResourceIndexError):
            code = exc.error_code
            message = exc.message
            context = exc.context
        else:
            code = "UNEXPECTED"
            message = str(exc)
            context = {"exception_type": type(exc).__name__}
        add_code(code)
        repo.add_ingest_event(
            rid,
            occurred_at=clock(),
            stage="crawl",
            severity="error",
            message=message,
            error_code=code,
            context=context,
        )
        if result.contents_created or result.contents_updated:
            result.status = IngestRunStatus.PARTIAL.value
        else:
            result.status = IngestRunStatus.FAILED.value

    request_budget = getattr(getattr(crawler, "fetcher", None), "request_budget", None)
    result.http_requests = int(getattr(request_budget, "used", 0) or 0)
    result.error_summary = summary
    repo.finish_ingest_run(
        rid,
        status=result.status,
        finished_at=clock(),
        documents_seen=result.documents_seen,
        contents_created=result.contents_created,
        contents_updated=result.contents_updated,
        resources_created=result.resources_created,
        resources_updated=result.resources_updated,
        warnings=result.warnings,
        errors=result.errors,
        error_summary=summary,
        http_requests=result.http_requests,
    )
    return result
