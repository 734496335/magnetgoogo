"""Live ingest pipeline: crawl → parse → transactional upsert."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.javbus.live_crawler import JavBusLiveCrawler
from magnet.resource_index.adapters.registry import get_crawler_factory
from magnet.resource_index.domain.enums import IngestMode, IngestRunStatus
from magnet.resource_index.domain.validation import validate_bundle
from magnet.resource_index.errors import ConflictError, ResourceIndexError
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
    delay_seconds: float = 1.5,
    max_pages: int = 40,
    clock: Clock = default_clock,
    run_id: str | None = None,
) -> IngestResult:
    """Crawl live pages and upsert into the resource index DB."""
    if not query and not detail_urls and listing_url is None:
        # listing_url None means home when no query — allow crawl home
        listing_url = ""

    policy = LiveFetchPolicy.from_flags(
        env_enabled=True,
        acknowledged=True,
        max_pages=max_pages,
        request_delay_seconds=delay_seconds,
    )
    # Bypass the hard 3-page cap for product crawl: policy assert uses DEFAULT_MAX_DETAIL_PAGES
    # Build policy object directly with validated fields
    policy = LiveFetchPolicy(
        enabled=True,
        acknowledged=True,
        max_pages=max(1, int(max_pages)),
        request_delay_seconds=max(0.5, float(delay_seconds)),
        concurrency=1,
    )

    factory = get_crawler_factory(source_id)
    crawler = factory(policy=policy)

    rid = run_id or uuid.uuid4().hex
    started = clock()
    repo.start_ingest_run(rid, source_id, IngestMode.LIVE_ONE_SHOT.value, started)
    result = IngestResult(run_id=rid, status=IngestRunStatus.RUNNING.value)
    error_codes: dict[str, int] = {}

    try:
        if detail_urls:
            items = crawler.crawl_detail_urls(detail_urls[:limit])
        elif query:
            items = crawler.crawl_query(query, limit=limit)
        else:
            # listing home or explicit listing_url
            if isinstance(crawler, JavBusLiveCrawler):
                items = crawler.crawl_listing_page(
                    listing_url or None,
                    limit=limit,
                )
            else:
                raise ResourceIndexError(
                    "CONFIG_ERROR",
                    "listing crawl not supported for this source",
                    {"source_id": source_id},
                )
    except ResourceIndexError as exc:
        result.errors += 1
        error_codes[exc.error_code] = 1
        repo.add_ingest_event(
            rid,
            occurred_at=clock(),
            stage="crawl",
            severity="error",
            message=exc.message,
            error_code=exc.error_code,
            context=exc.context,
        )
        result.status = IngestRunStatus.FAILED.value
        result.error_summary = error_codes
        repo.finish_ingest_run(
            rid,
            status=result.status,
            finished_at=clock(),
            documents_seen=0,
            contents_created=0,
            contents_updated=0,
            resources_created=0,
            resources_updated=0,
            warnings=0,
            errors=result.errors,
            error_summary=error_codes,
        )
        return result

    result.documents_seen = len(items)
    for item in items:
        if item.bundle is None:
            result.errors += 1
            code = item.error_code or "UNEXPECTED"
            error_codes[code] = error_codes.get(code, 0) + 1
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
            repo.add_ingest_event(
                rid,
                occurred_at=clock(),
                stage="upsert",
                severity="info",
                message=f"ingested {item.bundle.content.content_code}",
                source_item_key=item.bundle.content.source_item_key,
            )
        except ConflictError as exc:
            result.errors += 1
            error_codes[exc.error_code] = error_codes.get(exc.error_code, 0) + 1
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
        except ResourceIndexError as exc:
            result.errors += 1
            error_codes[exc.error_code] = error_codes.get(exc.error_code, 0) + 1
            repo.add_ingest_event(
                rid,
                occurred_at=clock(),
                stage="upsert",
                severity="error",
                message=exc.message,
                source_item_key=item.detail_url,
                error_code=exc.error_code,
            )

    if result.errors and (result.contents_created or result.contents_updated):
        status = IngestRunStatus.PARTIAL.value
    elif result.errors and not (result.contents_created or result.contents_updated):
        status = IngestRunStatus.FAILED.value
    else:
        status = IngestRunStatus.SUCCESS.value
    result.status = status
    result.error_summary = error_codes
    repo.finish_ingest_run(
        rid,
        status=status,
        finished_at=clock(),
        documents_seen=result.documents_seen,
        contents_created=result.contents_created,
        contents_updated=result.contents_updated,
        resources_created=result.resources_created,
        resources_updated=result.resources_updated,
        warnings=result.warnings,
        errors=result.errors,
        error_summary=error_codes,
    )
    return result
