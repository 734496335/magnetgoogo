"""Conservative scheduled orchestration for registered movie sources."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from magnet.resource_index.adapters.movie_registry import get_movie_source
from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.pipeline.latest_crawl import (
    LatestCrawlPaths,
    _canonical_snapshot_bytes,
    read_latest_status,
    select_best_latest_database,
)
from magnet.resource_index.pipeline.movie_latest import MovieLatestRunner
from magnet.resource_index.store.movie_source_state import MovieSourceStateStore
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

Clock = Callable[[], datetime]

_LEGACY_EXPANDED_DB_COUNTS = {
    ("sixv", 100): 50,
    ("dytt8899", 250): 25,
    ("meijumi", 100): 50,
}


def _runtime_db_path(
    *,
    output_dir: str | Path,
    source_id: str,
    target_count: int,
) -> Path:
    root = Path(output_dir).expanduser().resolve()
    exact = root / f"{source_id}_latest_{target_count}.db"
    candidates = [exact]
    legacy_count = _LEGACY_EXPANDED_DB_COUNTS.get((source_id, target_count))
    if legacy_count is not None:
        candidates.append(root / f"{source_id}_latest_{legacy_count}.db")
    selected = select_best_latest_database(
        candidates,
        source_id=source_id,
        target_count=target_count,
    )
    return Path(str(selected["selected_path"]))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SafeMovieSourceResult:
    source_id: str
    status: str
    reason: str
    target_count: int
    invocation_http_requests: int
    reserved_requests: int
    snapshot_changed: bool | None
    job_status: str | None
    covered_count: int | None
    remaining_daily_requests: int
    db_path: str
    feed_path: str
    publish_ready: bool


def _snapshot_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return hashlib.sha256(_canonical_snapshot_bytes(payload)).hexdigest()
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def _reserved_request_upper_bound(spec, *, resume: bool) -> int:
    detail_requests_per_batch = spec.batch_max_requests
    per_item = spec.detail_requests_per_item_upper_bound
    if per_item is not None:
        if per_item <= 0:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "detail request upper bound must be positive",
                {"source_id": spec.source_id, "value": per_item},
            )
        detail_requests_per_batch = min(
            spec.batch_max_requests,
            spec.default_batch_size * per_item,
        )
    reserved_requests = spec.automatic_max_batches * detail_requests_per_batch
    if not resume:
        reserved_requests += spec.snapshot_max_requests
    return reserved_requests


def run_safe_movie_source(
    *,
    source_id: str,
    output_dir: str | Path,
    target_count: int | None = None,
    clock: Clock = _utc_now,
    logger: logging.Logger | None = None,
    recovery_retry: bool = False,
) -> SafeMovieSourceResult:
    spec = get_movie_source(source_id)
    count = int(target_count or spec.default_count)
    paths = LatestCrawlPaths.for_output_dir(
        output_dir,
        source_id=source_id,
        target_count=count,
        db_path=_runtime_db_path(
            output_dir=output_dir,
            source_id=source_id,
            target_count=count,
        ),
    )
    repo = SqliteResourceRepository(paths.db_path)
    try:
        repo.init_schema()
        durable_status = read_latest_status(
            repo=repo,
            paths=paths,
            source_id=source_id,
            target_count=count,
        )
        durable_job_status = str(durable_status.get("status") or "")
        resume = durable_job_status in {"pending", "paused"}
        reserved_requests = _reserved_request_upper_bound(spec, resume=resume)
        state = MovieSourceStateStore(repo)
        reservation = state.reserve(
            source_id=source_id,
            now=clock(),
            minimum_interval_hours=(
                0 if recovery_retry or durable_job_status == "pending" else spec.minimum_check_interval_hours
            ),
            daily_budget=spec.daily_request_budget,
            requested_requests=reserved_requests,
        )
        if not reservation.allowed:
            return SafeMovieSourceResult(
                source_id=source_id,
                status="skipped",
                reason=reservation.reason,
                target_count=count,
                invocation_http_requests=0,
                reserved_requests=0,
                snapshot_changed=None,
                job_status=str(durable_status.get("status")),
                covered_count=int(durable_status.get("covered_count") or 0),
                remaining_daily_requests=reservation.remaining_daily_requests,
                db_path=str(paths.db_path),
                feed_path=str(paths.feed_path),
                publish_ready=False,
            )
        runner = MovieLatestRunner(
            repo=repo,
            paths=paths,
            source_id=source_id,
            target_count=count,
            batch_size=spec.default_batch_size,
            max_attempts=3,
            delay_seconds=spec.minimum_delay_seconds,
            snapshot_max_requests=spec.snapshot_max_requests,
            batch_max_requests=spec.batch_max_requests,
            max_listing_pages=spec.max_listing_pages,
            crawler_builder=spec.crawler_factory,
            snapshot_schema=spec.snapshot_schema,
            minimum_delay_seconds=spec.minimum_delay_seconds,
            clock=clock,
            logger=logger,
        )
        try:
            result = runner.run(
                refresh=not resume,
                max_batches=spec.automatic_max_batches,
            )
        except BaseException as exc:
            actual_requests = reservation.reserved_requests
            if isinstance(exc, ResourceIndexError):
                reported = exc.context.get("http_requests")
                if type(reported) is int and 0 <= reported <= reservation.reserved_requests:
                    actual_requests = reported
            state.complete(
                source_id=source_id,
                now=clock(),
                reserved_requests=reservation.reserved_requests,
                actual_requests=actual_requests,
                snapshot_hash=_snapshot_hash(paths.snapshot_path),
                success=False,
            )
            raise
        operation_ok = result.status in {"success", "pending"} or (
            result.status == "partial" and result.publish_ready
        )
        state.complete(
            source_id=source_id,
            now=clock(),
            reserved_requests=reservation.reserved_requests,
            actual_requests=result.invocation_http_requests,
            snapshot_hash=_snapshot_hash(paths.snapshot_path),
            success=operation_ok,
        )
        current = state.status(source_id=source_id, daily_budget=spec.daily_request_budget)
        return SafeMovieSourceResult(
            source_id=source_id,
            status="ran" if operation_ok else "paused",
            reason="resume" if resume else "scheduled_check",
            target_count=count,
            invocation_http_requests=result.invocation_http_requests,
            reserved_requests=reservation.reserved_requests,
            snapshot_changed=result.snapshot_changed,
            job_status=result.status,
            covered_count=result.covered_count,
            remaining_daily_requests=int(current["remaining_daily_requests"]),
            db_path=str(paths.db_path),
            feed_path=str(paths.feed_path),
            publish_ready=result.publish_ready,
        )
    finally:
        repo.close()


def safe_movie_source_status(
    *,
    source_id: str,
    output_dir: str | Path,
    target_count: int | None = None,
) -> dict[str, object]:
    spec = get_movie_source(source_id)
    count = int(target_count or spec.default_count)
    paths = LatestCrawlPaths.for_output_dir(
        output_dir,
        source_id=source_id,
        target_count=count,
        db_path=_runtime_db_path(
            output_dir=output_dir,
            source_id=source_id,
            target_count=count,
        ),
    )
    repo = SqliteResourceRepository(paths.db_path)
    try:
        repo.init_schema()
        job = read_latest_status(
            repo=repo,
            paths=paths,
            source_id=source_id,
            target_count=count,
        )
        publish_ready = job.get("status") == "success"
        if spec.publish_count is not None and count >= spec.publish_count:
            publish_ready = False
            try:
                feed_payload = json.loads(paths.feed_path.read_text(encoding="utf-8-sig"))
                publish_ready = int(feed_payload.get("summary", {}).get("record_count") or 0) >= spec.publish_count
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                publish_ready = False
        job["publish_ready"] = publish_ready
        return {
            "source": MovieSourceStateStore(repo).status(
                source_id=source_id,
                daily_budget=spec.daily_request_budget,
            ),
            "job": job,
            "policy": {
                "minimum_delay_seconds": spec.minimum_delay_seconds,
                "minimum_check_interval_hours": spec.minimum_check_interval_hours,
                "daily_request_budget": spec.daily_request_budget,
                "automatic_max_batches": spec.automatic_max_batches,
            },
        }
    finally:
        repo.close()
