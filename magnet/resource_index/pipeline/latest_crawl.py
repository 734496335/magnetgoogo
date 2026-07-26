"""Portable, resumable latest-list crawl orchestration."""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import shutil
import socket
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.movie_registry import get_movie_source
from magnet.resource_index.adapters.registry import get_crawler_factory
from magnet.resource_index.config import SCHEMA_VERSION
from magnet.resource_index.errors import (
    CONFIG_ERROR,
    LATEST_CRAWL_INCOMPLETE,
    LATEST_SNAPSHOT_INVALID,
    ResourceIndexError,
)
from magnet.resource_index.pipeline.ingest import IngestResult
from magnet.resource_index.pipeline.ingest_live import ingest_live
from magnet.resource_index.store.latest_crawl_jobs import LatestCrawlJobStore
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

Clock = Callable[[], datetime]
CrawlerBuilder = Callable[[str, LiveFetchPolicy], Any]
IngestFunction = Callable[..., IngestResult]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_name(value: str) -> str:
    result = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)
    return result.strip("-") or "source"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _canonical_snapshot_bytes(snapshot: dict[str, Any]) -> bytes:
    stable = {
        "schema_version": snapshot["schema_version"],
        "source_id": snapshot["source_id"],
        "target_count": snapshot["target_count"],
        "items": snapshot["items"],
    }
    return json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, SystemError):
        return False
    return True


@dataclass(frozen=True)
class LatestCrawlPaths:
    output_dir: Path
    db_path: Path
    snapshot_path: Path
    feed_path: Path
    lock_path: Path
    log_path: Path

    @classmethod
    def for_output_dir(
        cls,
        output_dir: str | Path,
        *,
        source_id: str,
        target_count: int,
        db_path: str | Path | None = None,
    ) -> "LatestCrawlPaths":
        root = Path(output_dir).expanduser().resolve()
        stem = f"{_safe_name(source_id)}_latest_{int(target_count)}"
        resolved_db = (
            Path(db_path).expanduser().resolve()
            if db_path
            else root / f"{stem}.db"
        )
        return cls(
            output_dir=root,
            db_path=resolved_db,
            snapshot_path=root / f"{stem}_urls.json",
            feed_path=root / f"{stem}_feed.json",
            lock_path=resolved_db.with_name(f"{resolved_db.stem}.lock"),
            log_path=root / f"{stem}.log",
        )


class PortableRunLock:
    def __init__(
        self,
        path: str | Path,
        *,
        pid_is_alive: Callable[[int], bool] = _pid_is_alive,
    ) -> None:
        self.path = Path(path)
        self.pid_is_alive = pid_is_alive
        self.token = uuid.uuid4().hex
        self.acquired = False
        self.recovered_stale = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "created_at": _utc_now().isoformat().replace("+00:00", "Z"),
            "token": self.token,
        }
        encoded = (json.dumps(metadata, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for _ in range(2):
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                try:
                    current = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    current = {}
                same_host = current.get("hostname") == socket.gethostname()
                owner_pid = int(current.get("pid") or 0)
                if not same_host or self.pid_is_alive(owner_pid):
                    raise RuntimeError(
                        f"latest crawl is already running: lock={self.path} "
                        f"host={current.get('hostname')} pid={owner_pid}"
                    )
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                self.recovered_stale = True
                continue
            try:
                os.write(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self.acquired = True
            return
        raise RuntimeError(f"unable to acquire latest crawl lock: {self.path}")

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        if current.get("token") == self.token:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.acquired = False

    def __enter__(self) -> "PortableRunLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.release()


@dataclass(frozen=True)
class LatestCrawlResult:
    job_id: str
    status: str
    target_count: int
    covered_count: int
    failed_count: int
    canonical_count: int
    resource_count: int
    snapshot_http_requests: int
    detail_http_requests: int
    db_path: str
    snapshot_path: str
    feed_path: str


class LatestCrawlRunner:
    def __init__(
        self,
        *,
        repo: SqliteResourceRepository,
        source_id: str,
        paths: LatestCrawlPaths,
        target_count: int = 100,
        batch_size: int = 5,
        max_attempts: int = 3,
        delay_seconds: float = 10.0,
        snapshot_max_requests: int = 20,
        batch_max_requests: int = 16,
        max_listing_pages: int = 20,
        crawler_builder: CrawlerBuilder | None = None,
        ingest_fn: IngestFunction | None = None,
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
                {
                    "target_count": target_count,
                    "batch_size": batch_size,
                    "max_attempts": max_attempts,
                },
            )
        minimum_batch_budget = 3 + batch_size * 2
        if batch_max_requests < minimum_batch_budget:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "batch_max_requests is too small for the configured batch_size",
                {
                    "batch_size": batch_size,
                    "batch_max_requests": batch_max_requests,
                    "minimum_batch_requests": minimum_batch_budget,
                },
            )
        self.repo = repo
        self.source_id = source_id
        self.paths = paths
        self.target_count = target_count
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.delay_seconds = delay_seconds
        self.snapshot_max_requests = snapshot_max_requests
        self.batch_max_requests = batch_max_requests
        self.max_listing_pages = max_listing_pages
        self.crawler_builder = crawler_builder or self._default_crawler_builder
        self.ingest_fn = ingest_fn or ingest_live
        self.clock = clock
        self.logger = logger or logging.getLogger(__name__)
        self.job_store = LatestCrawlJobStore(repo)
        self.current_job_id: str | None = None

    @staticmethod
    def _default_crawler_builder(source_id: str, policy: LiveFetchPolicy) -> Any:
        return get_crawler_factory(source_id)(policy=policy)

    def _log(self, message: str, **context: Any) -> None:
        suffix = " ".join(f"{key}={value}" for key, value in sorted(context.items()))
        self.logger.info("%s%s", message, f" {suffix}" if suffix else "")

    def _validate_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if snapshot.get("schema_version") != "1.0":
            raise ResourceIndexError(
                LATEST_SNAPSHOT_INVALID,
                "unsupported latest snapshot schema",
                {"schema_version": snapshot.get("schema_version")},
            )
        if snapshot.get("source_id") != self.source_id:
            raise ResourceIndexError(
                LATEST_SNAPSHOT_INVALID,
                "snapshot source does not match requested source",
                {
                    "snapshot_source": snapshot.get("source_id"),
                    "source_id": self.source_id,
                },
            )
        if int(snapshot.get("target_count") or 0) != self.target_count:
            raise ResourceIndexError(
                LATEST_SNAPSHOT_INVALID,
                "snapshot target_count does not match requested count",
                {
                    "snapshot_target": snapshot.get("target_count"),
                    "target_count": self.target_count,
                },
            )
        items = snapshot.get("items")
        if not isinstance(items, list) or len(items) != self.target_count:
            raise ResourceIndexError(
                LATEST_SNAPSHOT_INVALID,
                "snapshot item count is incomplete",
                {"expected": self.target_count, "actual": len(items or [])},
            )
        ranks = [item.get("rank") for item in items]
        urls = [item.get("detail_url") for item in items]
        if ranks != list(range(1, self.target_count + 1)):
            raise ResourceIndexError(
                LATEST_SNAPSHOT_INVALID,
                "snapshot ranks must be contiguous from 1",
                {},
            )
        if any(not isinstance(url, str) or not url for url in urls) or len(set(urls)) != len(urls):
            raise ResourceIndexError(
                LATEST_SNAPSHOT_INVALID,
                "snapshot detail URLs must be non-empty and unique",
                {},
            )
        return snapshot

    def _fetch_snapshot(self) -> dict[str, Any]:
        policy = LiveFetchPolicy(
            enabled=True,
            acknowledged=True,
            max_pages=self.snapshot_max_requests,
            request_delay_seconds=self.delay_seconds,
            concurrency=1,
        )
        policy.assert_allowed()
        crawler = self.crawler_builder(self.source_id, policy)
        crawl_latest = getattr(crawler, "crawl_latest_candidates", None)
        if not callable(crawl_latest):
            raise ResourceIndexError(
                CONFIG_ERROR,
                "source does not support latest-list snapshots",
                {"source_id": self.source_id},
            )
        raw_candidates = crawl_latest(
            limit=self.target_count,
            max_listing_pages=self.max_listing_pages,
        )
        items: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for candidate in raw_candidates:
            detail_url = str(candidate.detail_url)
            if detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)
            items.append(
                {
                    "rank": len(items) + 1,
                    "detail_url": detail_url,
                    "content_code": candidate.content_code,
                    "listing_title": candidate.raw_title,
                }
            )
            if len(items) >= self.target_count:
                break
        request_budget = getattr(getattr(crawler, "fetcher", None), "request_budget", None)
        snapshot = {
            "schema_version": "1.0",
            "source_id": self.source_id,
            "target_count": self.target_count,
            "captured_at": self.clock().isoformat().replace("+00:00", "Z"),
            "http_requests": int(getattr(request_budget, "used", 0) or 0),
            "items": items,
        }
        return self._validate_snapshot(snapshot)

    def _load_or_create_snapshot(self, *, refresh: bool) -> dict[str, Any]:
        if self.paths.snapshot_path.exists() and not refresh:
            try:
                payload = json.loads(self.paths.snapshot_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ResourceIndexError(
                    LATEST_SNAPSHOT_INVALID,
                    "unable to read latest snapshot",
                    {"path": str(self.paths.snapshot_path)},
                ) from exc
            return self._validate_snapshot(payload)
        snapshot = self._fetch_snapshot()
        _atomic_write_json(self.paths.snapshot_path, snapshot)
        return snapshot

    def _job_id(self, snapshot_hash: str) -> str:
        return f"latest-{_safe_name(self.source_id)}-{self.target_count}-{snapshot_hash[:16]}"

    def _run_id(self, job_id: str, batch: list[dict[str, Any]]) -> str:
        first_rank = min(int(item["rank"]) for item in batch)
        attempt = max(int(item["attempts"]) for item in batch) + 1
        return f"{job_id}-b{first_rank:04d}-a{attempt:02d}-{uuid.uuid4().hex[:8]}"

    def _fallback_error_code(self, result: IngestResult | None, exc: BaseException | None) -> str | None:
        if result is not None and result.error_summary:
            return sorted(result.error_summary)[0]
        if exc is not None:
            return type(exc).__name__.upper()
        return None

    def _write_feed(self, job_id: str) -> dict[str, Any]:
        job = self.job_store.get_job(job_id)
        assert job is not None
        records: list[dict[str, Any]] = []
        missing_urls: list[str] = []
        content_ids: set[str] = set()
        for item in self.job_store.items(job_id):
            observation = self.repo.conn.execute(
                """
                SELECT * FROM content_observations
                WHERE source_id = ? AND detail_url = ?
                ORDER BY last_seen_at DESC
                LIMIT 1
                """,
                (self.source_id, item["detail_url"]),
            ).fetchone()
            if observation is None:
                missing_urls.append(item["detail_url"])
                continue
            content = self.repo.conn.execute(
                "SELECT * FROM content_items WHERE content_id = ?",
                (observation["content_id"],),
            ).fetchone()
            if content is None:
                missing_urls.append(item["detail_url"])
                continue
            content_ids.add(content["content_id"])
            people = [
                dict(row)
                for row in self.repo.conn.execute(
                    """
                    SELECT p.display_name, cp.role, cp.sort_order
                    FROM content_people cp
                    JOIN people p ON p.person_id = cp.person_id
                    WHERE cp.content_id = ?
                    ORDER BY cp.sort_order, p.display_name
                    """,
                    (content["content_id"],),
                ).fetchall()
            ]
            tags = [
                row["display_name"]
                for row in self.repo.conn.execute(
                    """
                    SELECT t.display_name
                    FROM content_tags ct
                    JOIN tags t ON t.tag_id = ct.tag_id
                    WHERE ct.content_id = ?
                    ORDER BY t.display_name
                    """,
                    (content["content_id"],),
                ).fetchall()
            ]
            resource_count = int(
                self.repo.conn.execute(
                    "SELECT COUNT(*) FROM resource_releases WHERE content_id = ?",
                    (content["content_id"],),
                ).fetchone()[0]
            )
            records.append(
                {
                    "rank": int(item["rank"]),
                    "content_id": content["content_id"],
                    "content_code": content["content_code"],
                    "title": content["title"],
                    "listing_title": item["listing_title"],
                    "release_date": content["release_date"],
                    "duration_minutes": content["duration_minutes"],
                    "maker_name": content["maker_name"],
                    "publisher_name": content["publisher_name"],
                    "series_name": content["series_name"],
                    "cover_source_url": content["cover_source_url"],
                    "detail_url": item["detail_url"],
                    "people": people,
                    "tags": tags,
                    "resource_count": resource_count,
                    "source_first_seen_at": observation["first_seen_at"],
                    "source_last_seen_at": observation["last_seen_at"],
                }
            )
        resource_count = 0
        if content_ids:
            placeholders = ",".join("?" for _ in content_ids)
            resource_count = int(
                self.repo.conn.execute(
                    f"SELECT COUNT(*) FROM resource_releases WHERE content_id IN ({placeholders})",
                    tuple(sorted(content_ids)),
                ).fetchone()[0]
            )
        summary = self.job_store.summary(job_id)
        payload = {
            "summary": {
                "generated_at": self.clock().isoformat().replace("+00:00", "Z"),
                "source_id": self.source_id,
                "job_id": job_id,
                "status": job["status"],
                "target_count": self.target_count,
                "record_count": len(records),
                "canonical_content_count": len(content_ids),
                "resource_count": resource_count,
                "records_without_resources": sum(
                    1 for record in records if record["resource_count"] == 0
                ),
                "missing_urls": missing_urls,
                "failed_count": summary["failed_count"],
                "snapshot_http_requests": int(job["snapshot_http_requests"]),
                "detail_http_requests": int(job["detail_http_requests"]),
            },
            "items": records,
        }
        _atomic_write_json(self.paths.feed_path, payload)
        return payload

    def _result(self, job_id: str, status: str, feed: dict[str, Any]) -> LatestCrawlResult:
        job = self.job_store.get_job(job_id)
        assert job is not None
        summary = feed["summary"]
        return LatestCrawlResult(
            job_id=job_id,
            status=status,
            target_count=self.target_count,
            covered_count=int(summary["record_count"]),
            failed_count=int(summary["failed_count"]),
            canonical_count=int(summary["canonical_content_count"]),
            resource_count=int(summary["resource_count"]),
            snapshot_http_requests=int(job["snapshot_http_requests"]),
            detail_http_requests=int(job["detail_http_requests"]),
            db_path=str(self.paths.db_path),
            snapshot_path=str(self.paths.snapshot_path),
            feed_path=str(self.paths.feed_path),
        )

    def run(
        self,
        *,
        refresh: bool = False,
        max_batches: int | None = None,
    ) -> LatestCrawlResult:
        if max_batches is not None and max_batches < 0:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "max_batches must be non-negative",
                {"max_batches": max_batches},
            )
        self.paths.output_dir.mkdir(parents=True, exist_ok=True)
        lock = PortableRunLock(self.paths.lock_path)
        with lock:
            self.repo.init_schema()
            snapshot = self._load_or_create_snapshot(refresh=refresh)
            snapshot_hash = hashlib.sha256(_canonical_snapshot_bytes(snapshot)).hexdigest()
            job_id = self._job_id(snapshot_hash)
            self.current_job_id = job_id
            existing = self.job_store.get_job_by_snapshot(
                source_id=self.source_id,
                target_count=self.target_count,
                snapshot_hash=snapshot_hash,
            )
            if existing is not None:
                job_id = existing["job_id"]
                self.current_job_id = job_id
            job = self.job_store.create_or_get_job(
                job_id=job_id,
                source_id=self.source_id,
                target_count=self.target_count,
                batch_size=self.batch_size,
                max_attempts=self.max_attempts,
                snapshot_hash=snapshot_hash,
                snapshot=snapshot,
                snapshot_path=str(self.paths.snapshot_path),
                feed_path=str(self.paths.feed_path),
                snapshot_http_requests=int(snapshot.get("http_requests") or 0),
                now=self.clock(),
            )
            effective_batch_size = int(job["batch_size"])
            effective_max_attempts = int(job["max_attempts"])
            self.job_store.recover_running(job_id, now=self.clock())
            self.job_store.sync_success_from_observations(job_id, now=self.clock())
            initial = self.job_store.summary(job_id)
            if initial["covered_count"] == self.target_count:
                self.job_store.set_job_status(job_id, status="success", now=self.clock())
                feed = self._write_feed(job_id)
                return self._result(job_id, "success", feed)

            processed_batches = 0
            attempted_ranks: set[int] = set()
            while max_batches is None or processed_batches < max_batches:
                batch = self.job_store.next_batch(
                    job_id,
                    batch_size=effective_batch_size,
                    max_attempts=effective_max_attempts,
                    exclude_ranks=attempted_ranks,
                )
                if not batch:
                    break
                run_id = self._run_id(job_id, batch)
                ranks = [int(item["rank"]) for item in batch]
                attempted_ranks.update(ranks)
                urls = [str(item["detail_url"]) for item in batch]
                self.job_store.mark_batch_running(
                    job_id,
                    ranks=ranks,
                    run_id=run_id,
                    now=self.clock(),
                )
                self._log(
                    "latest crawl batch started",
                    job_id=job_id,
                    run_id=run_id,
                    first_rank=min(ranks),
                    last_rank=max(ranks),
                    items=len(urls),
                )
                result: IngestResult | None = None
                caught: BaseException | None = None
                try:
                    policy = LiveFetchPolicy(
                        enabled=True,
                        acknowledged=True,
                        max_pages=self.batch_max_requests,
                        request_delay_seconds=self.delay_seconds,
                        concurrency=1,
                    )
                    policy.assert_allowed()
                    result = self.ingest_fn(
                        repo=self.repo,
                        source_id=self.source_id,
                        detail_urls=urls,
                        limit=len(urls),
                        policy=policy,
                        run_id=run_id,
                    )
                    if result.status == "cancelled":
                        caught = KeyboardInterrupt()
                except KeyboardInterrupt as exc:
                    caught = exc
                except Exception as exc:
                    caught = exc
                http_requests = int(result.http_requests if result is not None else 0)
                if result is None:
                    run_row = self.repo.conn.execute(
                        "SELECT http_requests FROM ingest_runs WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()
                    if run_row is not None:
                        http_requests = int(run_row["http_requests"] or 0)
                self.job_store.close_interrupted_ingest_run(run_id, now=self.clock())
                fallback = self._fallback_error_code(result, caught)
                succeeded, failed = self.job_store.reconcile_batch(
                    job_id,
                    ranks=ranks,
                    run_id=run_id,
                    now=self.clock(),
                    fallback_error_code=fallback,
                    http_requests=http_requests,
                )
                self._log(
                    "latest crawl batch finished",
                    job_id=job_id,
                    run_id=run_id,
                    succeeded=succeeded,
                    failed=failed,
                    http_requests=http_requests,
                )
                processed_batches += 1
                if isinstance(caught, KeyboardInterrupt):
                    self.job_store.set_job_status(job_id, status="paused", now=self.clock())
                    self._write_feed(job_id)
                    raise caught

            self.job_store.sync_success_from_observations(job_id, now=self.clock())
            summary = self.job_store.summary(job_id)
            if summary["covered_count"] == self.target_count:
                status = "success"
            elif summary["exhausted_count"] > 0:
                status = "partial"
            else:
                status = "pending"
            error_summary: dict[str, int] = {}
            for item in self.job_store.items(job_id):
                code = item.get("last_error_code")
                if code and item["status"] != "success":
                    error_summary[code] = error_summary.get(code, 0) + 1
            self.job_store.set_job_status(
                job_id,
                status=status,
                now=self.clock(),
                error_summary=error_summary,
            )
            feed = self._write_feed(job_id)
            return self._result(job_id, status, feed)


def read_latest_status(
    *,
    repo: SqliteResourceRepository,
    paths: LatestCrawlPaths,
    source_id: str,
    target_count: int,
) -> dict[str, Any]:
    repo.init_schema()
    if not paths.snapshot_path.exists():
        return {
            "status": "not_started",
            "source_id": source_id,
            "target_count": target_count,
            "db_path": str(paths.db_path),
            "snapshot_path": str(paths.snapshot_path),
            "feed_path": str(paths.feed_path),
        }
    try:
        snapshot = json.loads(paths.snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(
            LATEST_SNAPSHOT_INVALID,
            "unable to read latest snapshot",
            {"path": str(paths.snapshot_path)},
        ) from exc
    schema_version = snapshot.get("schema_version")
    if (
        not isinstance(schema_version, str)
        or not schema_version.strip()
        or snapshot.get("source_id") != source_id
        or int(snapshot.get("target_count") or 0) != target_count
        or not isinstance(snapshot.get("items"), list)
    ):
        raise ResourceIndexError(
            LATEST_SNAPSHOT_INVALID,
            "latest snapshot does not match the requested status scope",
            {
                "source_id": source_id,
                "target_count": target_count,
                "path": str(paths.snapshot_path),
            },
        )
    snapshot_hash = hashlib.sha256(_canonical_snapshot_bytes(snapshot)).hexdigest()
    store = LatestCrawlJobStore(repo)
    job = store.get_job_by_snapshot(
        source_id=source_id,
        target_count=target_count,
        snapshot_hash=snapshot_hash,
    )
    if job is None:
        return {
            "status": "snapshot_only",
            "source_id": source_id,
            "target_count": target_count,
            "snapshot_hash": snapshot_hash,
            "db_path": str(paths.db_path),
            "snapshot_path": str(paths.snapshot_path),
            "feed_path": str(paths.feed_path),
        }
    summary = store.summary(job["job_id"])
    unresolved = [
        {
            "rank": int(item["rank"]),
            "detail_url": item["detail_url"],
            "status": item["status"],
            "attempts": int(item["attempts"]),
            "last_error_code": item["last_error_code"],
        }
        for item in store.items(job["job_id"])
        if item["status"] != "success"
    ]
    return {
        "status": job["status"],
        "job_id": job["job_id"],
        "source_id": source_id,
        "target_count": target_count,
        **summary,
        "snapshot_http_requests": int(job["snapshot_http_requests"]),
        "detail_http_requests": int(job["detail_http_requests"]),
        "updated_at": job["updated_at"],
        "completed_at": job["completed_at"],
        "unresolved": unresolved[:50],
        "db_path": str(paths.db_path),
        "snapshot_path": str(paths.snapshot_path),
        "feed_path": str(paths.feed_path),
        "log_path": str(paths.log_path),
    }


def run_deployment_doctor(
    *,
    output_dir: str | Path,
    db_path: str | Path,
    source_id: str,
) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}

    python_ok = sys.version_info >= (3, 10)
    checks["python"] = {
        "ok": python_ok,
        "version": ".".join(str(part) for part in sys.version_info[:3]),
        "executable": sys.executable,
    }

    for label, module_name in (
        ("curl_cffi", "curl_cffi"),
        ("beautifulsoup4", "bs4"),
    ):
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "unknown")
            checks[label] = {"ok": True, "version": str(version)}
        except ImportError as exc:
            checks[label] = {"ok": False, "error": str(exc)}

    output = Path(output_dir).expanduser().resolve()
    try:
        output.mkdir(parents=True, exist_ok=True)
        probe = output / f".write-probe-{uuid.uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks["writable_output"] = {"ok": True, "path": str(output)}
    except OSError as exc:
        checks["writable_output"] = {"ok": False, "path": str(output), "error": str(exc)}

    try:
        usage = shutil.disk_usage(output)
        checks["disk_space"] = {
            "ok": usage.free >= 100 * 1024 * 1024,
            "free_bytes": usage.free,
        }
    except OSError as exc:
        checks["disk_space"] = {"ok": False, "error": str(exc)}

    repo: SqliteResourceRepository | None = None
    try:
        repo = SqliteResourceRepository(db_path)
        schema = repo.init_schema()
        integrity = repo.conn.execute("PRAGMA integrity_check").fetchone()[0]
        checks["sqlite"] = {
            "ok": integrity == "ok" and schema == SCHEMA_VERSION,
            "library_version": sqlite3.sqlite_version,
            "schema_version": schema,
            "integrity": integrity,
            "path": str(Path(db_path).expanduser().resolve()),
        }
    except Exception as exc:
        checks["sqlite"] = {"ok": False, "error": str(exc)}
    finally:
        if repo is not None:
            repo.close()

    source_kind = None
    try:
        get_crawler_factory(source_id)
        source_kind = "content"
    except ResourceIndexError as content_error:
        try:
            get_movie_source(source_id)
            source_kind = "movie_latest"
        except ResourceIndexError:
            checks["source_registry"] = {
                "ok": False,
                "source_id": source_id,
                "error_code": content_error.error_code,
                "error": content_error.message,
            }
    if source_kind is not None:
        checks["source_registry"] = {
            "ok": True,
            "source_id": source_id,
            "source_kind": source_kind,
        }

    failed = sorted(name for name, detail in checks.items() if not detail.get("ok"))
    return {
        "status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def require_complete(result: LatestCrawlResult) -> None:
    if result.status != "success":
        raise ResourceIndexError(
            LATEST_CRAWL_INCOMPLETE,
            "latest crawl did not reach full snapshot coverage",
            {
                "job_id": result.job_id,
                "status": result.status,
                "covered_count": result.covered_count,
                "target_count": result.target_count,
            },
        )
