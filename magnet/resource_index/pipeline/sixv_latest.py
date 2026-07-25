"""Resumable latest-movie runner for the 6V source."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.sixv.live_crawler import SixVLiveCrawler
from magnet.resource_index.adapters.sixv.models import SixVListingCandidate
from magnet.resource_index.errors import (
    ACCESS_CHALLENGE,
    CONFIG_ERROR,
    INGEST_CANCELLED,
    LIVE_RATE_LIMITED,
    ResourceIndexError,
)
from magnet.resource_index.pipeline.latest_crawl import (
    LatestCrawlPaths,
    PortableRunLock,
    _atomic_write_json,
    _canonical_snapshot_bytes,
)
from magnet.resource_index.store.latest_crawl_jobs import LatestCrawlJobStore
from magnet.resource_index.store.movie_repository import MovieRepository
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

Clock = Callable[[], datetime]
CrawlerBuilder = Callable[[LiveFetchPolicy], SixVLiveCrawler]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SixVLatestResult:
    job_id: str
    status: str
    target_count: int
    covered_count: int
    failed_count: int
    movie_count: int
    recommended_count: int
    resource_count: int
    snapshot_http_requests: int
    detail_http_requests: int
    db_path: str
    snapshot_path: str
    feed_path: str


class SixVLatestRunner:
    source_id = "sixv"

    def __init__(
        self,
        *,
        repo: SqliteResourceRepository,
        paths: LatestCrawlPaths,
        target_count: int = 50,
        batch_size: int = 5,
        max_attempts: int = 3,
        delay_seconds: float = 10.0,
        snapshot_max_requests: int = 8,
        batch_max_requests: int = 8,
        max_listing_pages: int = 4,
        crawler_builder: CrawlerBuilder | None = None,
        clock: Clock = _utc_now,
        logger: logging.Logger | None = None,
    ) -> None:
        if repo.db_path.resolve() != paths.db_path.resolve():
            raise ResourceIndexError(
                CONFIG_ERROR,
                "runner database path does not match the locked database path",
                {
                    "repository_db": str(repo.db_path.resolve()),
                    "paths_db": str(paths.db_path.resolve()),
                },
            )
        if target_count <= 0 or batch_size <= 0 or max_attempts <= 0:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "target_count, batch_size and max_attempts must be positive",
                {},
            )
        if batch_max_requests < batch_size:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "batch request budget must cover one request per detail",
                {
                    "batch_size": batch_size,
                    "batch_max_requests": batch_max_requests,
                },
            )
        self.repo = repo
        self.paths = paths
        self.target_count = target_count
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.delay_seconds = delay_seconds
        self.snapshot_max_requests = snapshot_max_requests
        self.batch_max_requests = batch_max_requests
        self.max_listing_pages = max_listing_pages
        self.crawler_builder = crawler_builder or (lambda policy: SixVLiveCrawler(policy=policy))
        self.clock = clock
        self.logger = logger
        self.job_store = LatestCrawlJobStore(repo)
        self.movie_repo = MovieRepository(repo)
        self.current_job_id: str | None = None

    def _log(self, message: str, **context: Any) -> None:
        if self.logger is None:
            return
        suffix = " ".join(f"{key}={value}" for key, value in sorted(context.items()))
        self.logger.info("%s%s", message, f" {suffix}" if suffix else "")

    def _policy(self, max_pages: int) -> LiveFetchPolicy:
        policy = LiveFetchPolicy(
            enabled=True,
            acknowledged=True,
            max_pages=max_pages,
            request_delay_seconds=self.delay_seconds,
            concurrency=1,
        )
        policy.assert_allowed()
        return policy

    def _snapshot_payload(
        self,
        candidates: list[SixVListingCandidate],
        *,
        captured_at: datetime,
        http_requests: int,
    ) -> dict[str, Any]:
        return {
            "schema_version": "sixv-latest-movies/1",
            "source_id": self.source_id,
            "target_count": self.target_count,
            "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
            "http_requests": http_requests,
            "items": [
                {
                    "rank": item.rank,
                    "detail_url": item.detail_url,
                    "source_item_key": item.source_item_key,
                    "content_code": item.content_code,
                    "listing_title": item.listing_title,
                    "update_date": item.update_date.isoformat() if item.update_date else None,
                    "recommended": item.recommended,
                    "highlight_labels": list(item.highlight_labels),
                    "quality_tags": list(item.quality_tags),
                }
                for item in candidates
            ],
        }

    def _capture_snapshot(self) -> tuple[dict[str, Any], int]:
        crawler = self.crawler_builder(self._policy(self.snapshot_max_requests))
        candidates = crawler.crawl_latest_candidates(
            limit=self.target_count,
            max_listing_pages=self.max_listing_pages,
        )
        snapshot = self._snapshot_payload(
            candidates,
            captured_at=self.clock(),
            http_requests=crawler.http_requests,
        )
        _atomic_write_json(self.paths.snapshot_path, snapshot)
        return snapshot, crawler.http_requests

    def _load_snapshot(self) -> dict[str, Any]:
        try:
            snapshot = json.loads(self.paths.snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "unable to read the 6V latest snapshot",
                {"path": str(self.paths.snapshot_path)},
            ) from exc
        if (
            snapshot.get("schema_version") != "sixv-latest-movies/1"
            or snapshot.get("source_id") != self.source_id
            or int(snapshot.get("target_count") or 0) != self.target_count
            or len(snapshot.get("items") or []) != self.target_count
        ):
            raise ResourceIndexError(
                CONFIG_ERROR,
                "6V latest snapshot contract mismatch",
                {"path": str(self.paths.snapshot_path)},
            )
        ranks = [int(item.get("rank") or 0) for item in snapshot["items"]]
        urls = [str(item.get("detail_url") or "") for item in snapshot["items"]]
        if ranks != list(range(1, self.target_count + 1)) or len(set(urls)) != len(urls):
            raise ResourceIndexError(
                CONFIG_ERROR,
                "6V latest snapshot ranks or URLs are invalid",
                {"path": str(self.paths.snapshot_path)},
            )
        return snapshot

    def _candidate(self, item: dict[str, Any]) -> SixVListingCandidate:
        from datetime import date

        update_date = None
        if item.get("update_date"):
            update_date = date.fromisoformat(item["update_date"])
        return SixVListingCandidate(
            rank=int(item["rank"]),
            detail_url=item["detail_url"],
            source_item_key=item["source_item_key"],
            content_code=item["content_code"],
            listing_title=item["listing_title"],
            update_date=update_date,
            recommended=bool(item.get("recommended")),
            highlight_labels=tuple(item.get("highlight_labels") or ()),
            quality_tags=tuple(item.get("quality_tags") or ()),
        )

    def _sync_success(self, job_id: str) -> int:
        cursor = self.repo.conn.execute(
            """
            UPDATE latest_crawl_items
            SET status = 'success', last_error_code = NULL, updated_at = ?
            WHERE job_id = ?
              AND status <> 'success'
              AND EXISTS (
                  SELECT 1 FROM movie_items m
                  JOIN latest_crawl_jobs j ON j.job_id = latest_crawl_items.job_id
                  WHERE m.source_id = j.source_id
                    AND m.detail_url = latest_crawl_items.detail_url
              )
            """,
            (self.clock().isoformat().replace("+00:00", "Z"), job_id),
        )
        return int(cursor.rowcount or 0)

    def _mark_incomplete_pending(self, job_id: str) -> int:
        now_s = self.clock().isoformat().replace("+00:00", "Z")
        cursor = self.repo.conn.execute(
            """
            UPDATE latest_crawl_items
            SET status = 'pending', attempts = 0, last_run_id = NULL,
                last_error_code = NULL, updated_at = ?
            WHERE job_id = ?
              AND EXISTS (
                  SELECT 1
                  FROM movie_items m
                  JOIN latest_crawl_jobs j ON j.job_id = latest_crawl_items.job_id
                  WHERE m.source_id = j.source_id
                    AND m.detail_url = latest_crawl_items.detail_url
                    AND (
                        m.genres_json = '[]'
                        OR m.synopsis IS NULL
                        OR TRIM(m.synopsis) = ''
                    )
              )
            """,
            (now_s, job_id),
        )
        changed = int(cursor.rowcount or 0)
        if changed:
            self.repo.conn.execute(
                """
                UPDATE latest_crawl_jobs
                SET status = 'pending', completed_at = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                (now_s, job_id),
            )
        return changed

    def _reset_unattempted(
        self,
        job_id: str,
        *,
        ranks: list[int],
    ) -> None:
        if not ranks:
            return
        placeholders = ",".join("?" for _ in ranks)
        self.repo.conn.execute(
            f"""
            UPDATE latest_crawl_items
            SET status = 'pending',
                attempts = CASE WHEN attempts > 0 THEN attempts - 1 ELSE 0 END,
                last_run_id = NULL,
                last_error_code = NULL,
                updated_at = ?
            WHERE job_id = ? AND rank IN ({placeholders}) AND status = 'running'
            """,
            (
                self.clock().isoformat().replace("+00:00", "Z"),
                job_id,
                *ranks,
            ),
        )

    def _reconcile(
        self,
        job_id: str,
        *,
        ranks: list[int],
        run_id: str,
        errors: dict[int, str],
        http_requests: int,
    ) -> tuple[int, int]:
        now_s = self.clock().isoformat().replace("+00:00", "Z")
        succeeded = 0
        failed = 0
        self.repo.conn.execute("BEGIN IMMEDIATE")
        try:
            for rank in ranks:
                row = self.repo.conn.execute(
                    "SELECT detail_url FROM latest_crawl_items WHERE job_id = ? AND rank = ?",
                    (job_id, rank),
                ).fetchone()
                exists = row is not None and self.movie_repo.exists(
                    source_id=self.source_id,
                    detail_url=row["detail_url"],
                )
                if exists:
                    status = "success"
                    error_code = None
                    succeeded += 1
                else:
                    status = "failed"
                    error_code = errors.get(rank, "UNEXPECTED")
                    failed += 1
                self.repo.conn.execute(
                    """
                    UPDATE latest_crawl_items
                    SET status = ?, last_run_id = ?, last_error_code = ?, updated_at = ?
                    WHERE job_id = ? AND rank = ?
                    """,
                    (status, run_id, error_code, now_s, job_id, rank),
                )
            self.repo.conn.execute(
                """
                UPDATE latest_crawl_jobs
                SET detail_http_requests = detail_http_requests + ?, updated_at = ?
                WHERE job_id = ?
                """,
                (http_requests, now_s, job_id),
            )
            self.repo.conn.execute("COMMIT")
        except Exception:
            self.repo.conn.execute("ROLLBACK")
            raise
        return succeeded, failed

    def _export_feed(self, job_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        missing_urls: list[str] = []
        for snapshot_item in snapshot["items"]:
            feed_item = self.movie_repo.feed_item(
                source_id=self.source_id,
                detail_url=snapshot_item["detail_url"],
                rank=int(snapshot_item["rank"]),
            )
            if feed_item is None:
                missing_urls.append(snapshot_item["detail_url"])
                continue
            items.append(feed_item)
        counts = self.movie_repo.counts(source_id=self.source_id)
        job = self.job_store.get_job(job_id)
        assert job is not None
        payload = {
            "schema_version": "movie-feed/1",
            "source_id": self.source_id,
            "generated_at": self.clock().isoformat().replace("+00:00", "Z"),
            "snapshot_captured_at": snapshot.get("captured_at"),
            "items": items,
            "summary": {
                "record_count": len(items),
                "target_count": self.target_count,
                "recommended_count": sum(1 for item in items if item["recommended"]),
                "resource_count": sum(len(item["resources"]) for item in items),
                "missing_urls": missing_urls,
                "snapshot_http_requests": int(job["snapshot_http_requests"] or 0),
                "detail_http_requests": int(job["detail_http_requests"] or 0),
                "database_movie_count": counts["movies"],
            },
        }
        _atomic_write_json(self.paths.feed_path, payload)
        return payload

    def _result(self, job_id: str, status: str, feed: dict[str, Any]) -> SixVLatestResult:
        summary = self.job_store.summary(job_id)
        job = self.job_store.get_job(job_id)
        assert job is not None
        return SixVLatestResult(
            job_id=job_id,
            status=status,
            target_count=self.target_count,
            covered_count=summary["covered_count"],
            failed_count=summary["failed_count"],
            movie_count=int(feed["summary"]["record_count"]),
            recommended_count=int(feed["summary"]["recommended_count"]),
            resource_count=int(feed["summary"]["resource_count"]),
            snapshot_http_requests=int(job["snapshot_http_requests"] or 0),
            detail_http_requests=int(job["detail_http_requests"] or 0),
            db_path=str(self.paths.db_path),
            snapshot_path=str(self.paths.snapshot_path),
            feed_path=str(self.paths.feed_path),
        )

    def run(
        self,
        *,
        refresh: bool = False,
        max_batches: int | None = None,
        reparse_incomplete: bool = False,
    ) -> SixVLatestResult:
        if max_batches is not None and max_batches < 0:
            raise ResourceIndexError(CONFIG_ERROR, "max_batches must not be negative", {})
        self.repo.init_schema()
        self.paths.output_dir.mkdir(parents=True, exist_ok=True)
        with PortableRunLock(self.paths.lock_path):
            if refresh or not self.paths.snapshot_path.exists():
                snapshot, snapshot_requests = self._capture_snapshot()
            else:
                snapshot = self._load_snapshot()
                snapshot_requests = int(snapshot.get("http_requests") or 0)
            snapshot_hash = hashlib.sha256(_canonical_snapshot_bytes(snapshot)).hexdigest()
            job_id = f"latest-{self.source_id}-{self.target_count}-{snapshot_hash[:16]}"
            self.current_job_id = job_id
            self.job_store.create_or_get_job(
                job_id=job_id,
                source_id=self.source_id,
                target_count=self.target_count,
                batch_size=self.batch_size,
                max_attempts=self.max_attempts,
                snapshot_hash=snapshot_hash,
                snapshot=snapshot,
                snapshot_path=str(self.paths.snapshot_path),
                feed_path=str(self.paths.feed_path),
                snapshot_http_requests=snapshot_requests,
                now=self.clock(),
            )
            self.job_store.recover_running(job_id, now=self.clock())
            self._sync_success(job_id)
            if reparse_incomplete:
                self._mark_incomplete_pending(job_id)
            job = self.job_store.get_job(job_id)
            assert job is not None
            summary = self.job_store.summary(job_id)
            if summary["covered_count"] == self.target_count:
                self.job_store.set_job_status(job_id, status="success", now=self.clock())
                feed = self._export_feed(job_id, snapshot)
                return self._result(job_id, "success", feed)

            by_rank = {int(item["rank"]): item for item in snapshot["items"]}
            attempted: set[int] = set()
            batches = 0
            stopped_by_policy = False
            while max_batches is None or batches < max_batches:
                batch = self.job_store.next_batch(
                    job_id,
                    batch_size=self.batch_size,
                    max_attempts=self.max_attempts,
                    exclude_ranks=attempted,
                )
                if not batch:
                    break
                ranks = [int(item["rank"]) for item in batch]
                attempted.update(ranks)
                run_id = f"{job_id}-b{min(ranks):04d}-a{max(int(item['attempts']) for item in batch) + 1:02d}-{uuid.uuid4().hex[:8]}"
                self.job_store.mark_batch_running(
                    job_id,
                    ranks=ranks,
                    run_id=run_id,
                    now=self.clock(),
                )
                self.repo.start_ingest_run(
                    run_id,
                    self.source_id,
                    "live_one_shot",
                    self.clock(),
                )
                crawler = self.crawler_builder(self._policy(self.batch_max_requests))
                errors: dict[int, str] = {}
                processed_ranks: list[int] = []
                created = 0
                updated = 0
                resources_created = 0
                resources_updated = 0
                cancelled = False
                hard_stop = False
                self._log("6V movie batch started", job_id=job_id, run_id=run_id, ranks=ranks)
                try:
                    for rank in ranks:
                        candidate = self._candidate(by_rank[rank])
                        processed_ranks.append(rank)
                        try:
                            movie = crawler.crawl_movie_detail(candidate)
                            stats = self.movie_repo.upsert(movie, now=self.clock())
                            created += int(stats.movie_created)
                            updated += int(stats.movie_updated)
                            resources_created += stats.resources_created
                            resources_updated += stats.resources_updated
                        except KeyboardInterrupt:
                            cancelled = True
                            errors[rank] = INGEST_CANCELLED
                            break
                        except ResourceIndexError as exc:
                            errors[rank] = exc.error_code
                            if exc.error_code in {LIVE_RATE_LIMITED, ACCESS_CHALLENGE}:
                                hard_stop = True
                                break
                        except Exception as exc:
                            errors[rank] = type(exc).__name__
                except KeyboardInterrupt:
                    cancelled = True
                unattempted_ranks = [rank for rank in ranks if rank not in processed_ranks]
                self._reset_unattempted(job_id, ranks=unattempted_ranks)
                status = "cancelled" if cancelled else ("partial" if errors and (created or updated) else "failed" if errors else "success")
                self.repo.finish_ingest_run(
                    run_id,
                    status=status,
                    finished_at=self.clock(),
                    documents_seen=len(processed_ranks),
                    contents_created=created,
                    contents_updated=updated,
                    resources_created=resources_created,
                    resources_updated=resources_updated,
                    warnings=0,
                    errors=len(errors),
                    error_summary={code: list(errors.values()).count(code) for code in set(errors.values())},
                    http_requests=crawler.http_requests,
                )
                self._reconcile(
                    job_id,
                    ranks=processed_ranks,
                    run_id=run_id,
                    errors=errors,
                    http_requests=crawler.http_requests,
                )
                self._export_feed(job_id, snapshot)
                batches += 1
                self._log(
                    "6V movie batch finished",
                    job_id=job_id,
                    run_id=run_id,
                    http_requests=crawler.http_requests,
                    errors=len(errors),
                )
                if cancelled:
                    self.job_store.set_job_status(job_id, status="paused", now=self.clock())
                    raise KeyboardInterrupt
                if hard_stop:
                    stopped_by_policy = True
                    break

            summary = self.job_store.summary(job_id)
            if stopped_by_policy:
                status = "paused"
            elif summary["covered_count"] == self.target_count:
                status = "success"
            elif summary["exhausted_count"] > 0 and summary["pending_count"] == 0:
                status = "partial"
            else:
                status = "pending"
            self.job_store.set_job_status(job_id, status=status, now=self.clock())
            feed = self._export_feed(job_id, snapshot)
            return self._result(job_id, status, feed)
