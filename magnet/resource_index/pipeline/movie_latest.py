"""Shared resumable latest-movie runner for independent site adapters."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from magnet.resource_index.acquisition.http_client import normalized_origin
from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.movie_brand_registry import (
    MovieBrandEndpoint,
    load_movie_brand_registry,
)
from magnet.resource_index.adapters.movie_registry import MovieCrawler, get_movie_source
from magnet.resource_index.domain.movie_models import MovieListingCandidate
from magnet.resource_index.normalize.text import normalize_whitespace
from magnet.resource_index.errors import (
    ACCESS_CHALLENGE,
    CONFIG_ERROR,
    INGEST_CANCELLED,
    LIVE_RATE_LIMITED,
    LIVE_REQUEST_BUDGET_EXHAUSTED,
    LIVE_URL_REJECTED,
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
CrawlerBuilder = Callable[..., MovieCrawler]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MovieLatestResult:
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
    snapshot_changed: bool
    invocation_http_requests: int


class MovieLatestRunner:

    def __init__(
        self,
        *,
        repo: SqliteResourceRepository,
        paths: LatestCrawlPaths,
        source_id: str = "sixv",
        target_count: int = 50,
        batch_size: int = 5,
        max_attempts: int = 3,
        delay_seconds: float = 10.0,
        snapshot_max_requests: int = 8,
        batch_max_requests: int = 8,
        max_listing_pages: int = 4,
        crawler_builder: CrawlerBuilder | None = None,
        snapshot_schema: str | None = None,
        minimum_delay_seconds: float | None = None,
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
        source_spec = get_movie_source(source_id)
        self.repo = repo
        self.paths = paths
        self.source_id = source_id
        self.snapshot_schema = snapshot_schema or source_spec.snapshot_schema
        self.brand_id = source_spec.brand_id
        self.content_kind = source_spec.content_kind
        self.parser_variant = source_spec.parser_variant
        if self.brand_id and self.parser_variant:
            self.endpoints = load_movie_brand_registry().runtime_endpoints(
                brand_id=self.brand_id,
                source_id=self.source_id,
                parser_variant=self.parser_variant,
            )
        else:
            self.endpoints = tuple(
                MovieBrandEndpoint(
                    endpoint_id=f"{source_id}-{index}",
                    origin=value.rstrip("/"),
                    role="primary" if index == 0 else "official_mirror",
                    state="active" if index == 0 else "standby",
                    parser_variant=self.parser_variant or source_id,
                    priority=index * 10,
                    source_ids=(source_id,),
                    evidence="runtime_config",
                    verified_at=None,
                    content_fingerprint=None,
                    allowed_redirect_origins=(),
                    notes=None,
                )
                for index, value in enumerate(source_spec.allowed_origins)
            )
        allowed_origin_values = {
            origin
            for endpoint in self.endpoints
            for origin in endpoint.allowed_origins
        }
        self.allowed_origin_values = tuple(sorted(allowed_origin_values))
        self.allowed_origins = {
            normalized_origin(value) for value in self.allowed_origin_values
        }
        self.allowed_path_prefixes = source_spec.allowed_path_prefixes
        self.target_count = target_count
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        minimum_delay = (
            source_spec.minimum_delay_seconds
            if minimum_delay_seconds is None
            else float(minimum_delay_seconds)
        )
        self.delay_seconds = max(float(delay_seconds), minimum_delay)
        self.snapshot_max_requests = snapshot_max_requests
        self.batch_max_requests = batch_max_requests
        self.max_listing_pages = max_listing_pages
        self.crawler_builder = crawler_builder or source_spec.crawler_factory
        self.clock = clock
        self.logger = logger
        self.job_store = LatestCrawlJobStore(repo)
        self.movie_repo = MovieRepository(repo)
        self.current_job_id: str | None = None
        self._snapshot_changed = False
        self._invocation_http_requests = 0

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

    def _build_crawler(
        self,
        *,
        policy: LiveFetchPolicy,
        endpoint: MovieBrandEndpoint,
    ) -> MovieCrawler:
        try:
            return self.crawler_builder(
                policy,
                origin=endpoint.origin,
                allowed_origins=self.allowed_origin_values,
            )
        except TypeError as exc:
            message = str(exc)
            if "unexpected keyword argument" not in message and "positional argument" not in message:
                raise
            return self.crawler_builder(policy)

    def _endpoint_for_origin(self, origin: str | None) -> MovieBrandEndpoint:
        normalized = normalized_origin(origin or self.endpoints[0].origin)
        for endpoint in self.endpoints:
            if normalized_origin(endpoint.origin) == normalized:
                return endpoint
        raise ResourceIndexError(
            LIVE_URL_REJECTED,
            "movie snapshot references an unregistered endpoint origin",
            {"source_id": self.source_id, "endpoint_origin": origin},
        )

    def _validate_candidates(
        self,
        candidates: list[MovieListingCandidate],
    ) -> None:
        if len(candidates) != self.target_count:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie source returned an unexpected candidate count",
                {"source_id": self.source_id, "expected": self.target_count, "found": len(candidates)},
            )
        seen_urls: set[str] = set()
        seen_source_keys: set[str] = set()
        for expected_rank, candidate in enumerate(candidates, start=1):
            parsed = urlparse(candidate.detail_url)
            try:
                origin = normalized_origin(candidate.detail_url)
            except ResourceIndexError as exc:
                raise ResourceIndexError(
                    LIVE_URL_REJECTED,
                    "movie candidate URL is invalid",
                    {"source_id": self.source_id, "detail_url": candidate.detail_url},
                ) from exc
            if origin not in self.allowed_origins:
                raise ResourceIndexError(
                    LIVE_URL_REJECTED,
                    "movie candidate URL is outside the source origin",
                    {"source_id": self.source_id, "detail_url": candidate.detail_url},
                )
            if not any(parsed.path.startswith(prefix) for prefix in self.allowed_path_prefixes):
                raise ResourceIndexError(
                    LIVE_URL_REJECTED,
                    "movie candidate URL is outside the allowed public paths",
                    {"source_id": self.source_id, "detail_url": candidate.detail_url},
                )
            if candidate.rank != expected_rank:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "movie candidate ranks must be contiguous",
                    {"source_id": self.source_id, "expected_rank": expected_rank, "rank": candidate.rank},
                )
            if candidate.detail_url in seen_urls:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "movie candidate URLs must be unique",
                    {"source_id": self.source_id, "detail_url": candidate.detail_url},
                )
            source_key = str(candidate.source_item_key or "")
            source_key_parts = urlparse(source_key)
            if (
                not source_key.startswith("/")
                or source_key_parts.scheme
                or source_key_parts.netloc
                or source_key_parts.query
                or source_key_parts.fragment
                or source_key != parsed.path
            ):
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "movie candidate source key must equal the canonical detail path",
                    {
                        "source_id": self.source_id,
                        "source_item_key": candidate.source_item_key,
                        "detail_path": parsed.path,
                    },
                )
            if source_key in seen_source_keys:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "movie candidate source keys must be unique",
                    {"source_id": self.source_id, "source_item_key": source_key},
                )
            if not normalize_whitespace(candidate.listing_title):
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "movie candidate title must not be empty",
                    {"source_id": self.source_id, "rank": candidate.rank},
                )
            if candidate.content_kind != self.content_kind:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "movie candidate content kind does not match the source contract",
                    {
                        "source_id": self.source_id,
                        "expected": self.content_kind,
                        "actual": candidate.content_kind,
                    },
                )
            if self.brand_id and candidate.brand_id != self.brand_id:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "movie candidate brand does not match the source contract",
                    {
                        "source_id": self.source_id,
                        "expected": self.brand_id,
                        "actual": candidate.brand_id,
                    },
                )
            seen_urls.add(candidate.detail_url)
            seen_source_keys.add(source_key)

    def _snapshot_payload(
        self,
        candidates: list[MovieListingCandidate],
        *,
        captured_at: datetime,
        http_requests: int,
    ) -> dict[str, Any]:
        return {
            "schema_version": self.snapshot_schema,
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
                    "content_kind": item.content_kind,
                    "series_title": item.series_title,
                    "season_number": item.season_number,
                    "episode_number": item.episode_number,
                    "episode_label": item.episode_label,
                    "update_status": item.update_status,
                    "brand_id": item.brand_id,
                    "endpoint_origin": item.endpoint_origin,
                }
                for item in candidates
            ],
        }

    def _capture_snapshot(self) -> tuple[dict[str, Any], int]:
        previous_hash = None
        if self.paths.snapshot_path.exists():
            try:
                previous = json.loads(self.paths.snapshot_path.read_text(encoding="utf-8"))
                previous_hash = hashlib.sha256(_canonical_snapshot_bytes(previous)).hexdigest()
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                previous_hash = None
        total_requests = 0
        attempts: list[dict[str, Any]] = []
        last_error: Exception | None = None
        selected_endpoint: MovieBrandEndpoint | None = None
        candidates: list[MovieListingCandidate] | None = None
        for endpoint in self.endpoints:
            remaining = self.snapshot_max_requests - total_requests
            if remaining <= 0:
                break
            crawler = self._build_crawler(
                policy=self._policy(remaining),
                endpoint=endpoint,
            )
            try:
                captured = crawler.crawl_latest_candidates(
                    limit=self.target_count,
                    max_listing_pages=self.max_listing_pages,
                )
                total_requests += crawler.http_requests
                annotated = [
                    replace(
                        item,
                        content_kind=item.content_kind or self.content_kind,
                        brand_id=item.brand_id or self.brand_id,
                        endpoint_origin=endpoint.origin,
                    )
                    for item in captured
                ]
                self._validate_candidates(annotated)
                candidates = annotated
                selected_endpoint = endpoint
                attempts.append(
                    {
                        "endpoint_id": endpoint.endpoint_id,
                        "origin": endpoint.origin,
                        "status": "success",
                        "http_requests": crawler.http_requests,
                    }
                )
                break
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                total_requests += crawler.http_requests
                last_error = exc
                attempts.append(
                    {
                        "endpoint_id": endpoint.endpoint_id,
                        "origin": endpoint.origin,
                        "status": "failed",
                        "http_requests": crawler.http_requests,
                        "error": type(exc).__name__,
                    }
                )
                self._log(
                    "movie endpoint snapshot failed",
                    source_id=self.source_id,
                    endpoint_id=endpoint.endpoint_id,
                    error=type(exc).__name__,
                )
        self._invocation_http_requests += total_requests
        if candidates is None or selected_endpoint is None:
            if last_error is not None:
                raise last_error
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie source has no usable endpoint within the request budget",
                {"source_id": self.source_id},
            )
        snapshot = self._snapshot_payload(
            candidates,
            captured_at=self.clock(),
            http_requests=total_requests,
        )
        snapshot["brand_id"] = self.brand_id
        snapshot["content_kind"] = self.content_kind
        snapshot["selected_endpoint"] = {
            "endpoint_id": selected_endpoint.endpoint_id,
            "origin": selected_endpoint.origin,
        }
        snapshot["endpoint_attempts"] = attempts
        current_hash = hashlib.sha256(_canonical_snapshot_bytes(snapshot)).hexdigest()
        self._snapshot_changed = previous_hash != current_hash
        _atomic_write_json(self.paths.snapshot_path, snapshot)
        return snapshot, total_requests

    def _load_snapshot(self) -> dict[str, Any]:
        try:
            snapshot = json.loads(self.paths.snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "unable to read the movie latest snapshot",
                {"path": str(self.paths.snapshot_path)},
            ) from exc
        if (
            snapshot.get("schema_version") != self.snapshot_schema
            or snapshot.get("source_id") != self.source_id
            or int(snapshot.get("target_count") or 0) != self.target_count
            or len(snapshot.get("items") or []) != self.target_count
        ):
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie latest snapshot contract mismatch",
                {"path": str(self.paths.snapshot_path)},
            )
        ranks = [int(item.get("rank") or 0) for item in snapshot["items"]]
        urls = [str(item.get("detail_url") or "") for item in snapshot["items"]]
        if ranks != list(range(1, self.target_count + 1)) or len(set(urls)) != len(urls):
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie latest snapshot ranks or URLs are invalid",
                {"path": str(self.paths.snapshot_path)},
            )
        try:
            candidates = [self._candidate(item) for item in snapshot["items"]]
            self._validate_candidates(candidates)
        except (KeyError, TypeError, ValueError) as exc:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "movie latest snapshot items are malformed",
                {"path": str(self.paths.snapshot_path)},
            ) from exc
        return snapshot

    def _candidate(self, item: dict[str, Any]) -> MovieListingCandidate:
        from datetime import date

        update_date = None
        if item.get("update_date"):
            update_date = date.fromisoformat(item["update_date"])
        return MovieListingCandidate(
            rank=int(item["rank"]),
            detail_url=item["detail_url"],
            source_item_key=item["source_item_key"],
            content_code=item["content_code"],
            listing_title=item["listing_title"],
            update_date=update_date,
            recommended=bool(item.get("recommended")),
            highlight_labels=tuple(item.get("highlight_labels") or ()),
            quality_tags=tuple(item.get("quality_tags") or ()),
            content_kind=str(item.get("content_kind") or self.content_kind),
            series_title=item.get("series_title"),
            season_number=item.get("season_number"),
            episode_number=item.get("episode_number"),
            episode_label=item.get("episode_label"),
            update_status=item.get("update_status"),
            brand_id=item.get("brand_id") or self.brand_id,
            endpoint_origin=item.get("endpoint_origin"),
        )

    def _series_refresh_ranks(
        self,
        job_id: str,
        snapshot: dict[str, Any],
    ) -> set[int]:
        if self.content_kind != "series":
            return set()
        row = self.repo.conn.execute(
            """
            SELECT snapshot_json
            FROM latest_crawl_jobs
            WHERE source_id = ? AND target_count = ? AND job_id <> ?
            ORDER BY created_at DESC, job_id DESC
            LIMIT 1
            """,
            (self.source_id, self.target_count, job_id),
        ).fetchone()
        if row is None:
            return set()
        try:
            previous = json.loads(row["snapshot_json"])
        except (json.JSONDecodeError, TypeError):
            return set()
        previous_items = {
            str(item.get("source_item_key") or item.get("detail_url") or ""): item
            for item in previous.get("items") or []
            if isinstance(item, dict)
        }
        refresh_fields = (
            "detail_url",
            "listing_title",
            "update_date",
            "update_status",
            "series_title",
            "season_number",
            "episode_number",
            "episode_label",
        )
        ranks: set[int] = set()
        for item in snapshot["items"]:
            identity = str(item.get("source_item_key") or item.get("detail_url") or "")
            prior = previous_items.get(identity)
            if prior is None:
                continue
            if any(prior.get(field) != item.get(field) for field in refresh_fields):
                ranks.add(int(item["rank"]))
        return ranks

    def _sync_success(self, job_id: str, snapshot: dict[str, Any]) -> int:
        changed = 0
        refresh_ranks = self._series_refresh_ranks(job_id, snapshot)
        item_states = {
            int(item["rank"]): item for item in self.job_store.items(job_id)
        }
        if refresh_ranks:
            self._log(
                "series listing changes require detail refresh",
                job_id=job_id,
                ranks=sorted(refresh_ranks),
                source_id=self.source_id,
            )
        for item in snapshot["items"]:
            candidate = self._candidate(item)
            if not self.movie_repo.exists(
                source_id=self.source_id,
                source_item_key=candidate.source_item_key,
                detail_url=candidate.detail_url,
            ):
                continue
            self.movie_repo.refresh_from_candidate(
                source_id=self.source_id,
                candidate=candidate,
                now=self.clock(),
            )
            state = item_states.get(candidate.rank) or {}
            refresh_completed = (
                state.get("status") == "success" and bool(state.get("last_run_id"))
            )
            if candidate.rank in refresh_ranks and not refresh_completed:
                if not state.get("last_run_id"):
                    cursor = self.repo.conn.execute(
                        """
                        UPDATE latest_crawl_items
                        SET status = 'pending', attempts = 0, last_run_id = NULL,
                            last_error_code = NULL, detail_url = ?,
                            source_item_key = ?, updated_at = ?
                        WHERE job_id = ? AND rank = ?
                        """,
                        (
                            candidate.detail_url,
                            candidate.source_item_key,
                            self.clock().isoformat().replace("+00:00", "Z"),
                            job_id,
                            candidate.rank,
                        ),
                    )
                    changed += int(cursor.rowcount or 0)
                continue
            cursor = self.repo.conn.execute(
                """
                UPDATE latest_crawl_items
                SET status = 'success', last_error_code = NULL,
                    detail_url = ?, source_item_key = ?, updated_at = ?
                WHERE job_id = ? AND rank = ? AND status <> 'success'
                """,
                (
                    candidate.detail_url,
                    candidate.source_item_key,
                    self.clock().isoformat().replace("+00:00", "Z"),
                    job_id,
                    candidate.rank,
                ),
            )
            changed += int(cursor.rowcount or 0)
        return changed

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
                    AND (
                        m.source_item_key = latest_crawl_items.source_item_key
                        OR m.detail_url = latest_crawl_items.detail_url
                    )
                    AND (
                        m.genres_json = '[]'
                        OR m.synopsis IS NULL
                        OR TRIM(m.synopsis) = ''
                        OR (
                            m.content_kind = 'series'
                            AND (m.season_number IS NULL OR m.episode_number IS NULL)
                        )
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
                    "SELECT detail_url, source_item_key FROM latest_crawl_items WHERE job_id = ? AND rank = ?",
                    (job_id, rank),
                ).fetchone()
                exists = row is not None and self.movie_repo.exists(
                    source_id=self.source_id,
                    detail_url=row["detail_url"],
                    source_item_key=row["source_item_key"],
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
                source_item_key=snapshot_item.get("source_item_key"),
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

    def _result(self, job_id: str, status: str, feed: dict[str, Any]) -> MovieLatestResult:
        summary = self.job_store.summary(job_id)
        job = self.job_store.get_job(job_id)
        assert job is not None
        return MovieLatestResult(
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
            snapshot_changed=self._snapshot_changed,
            invocation_http_requests=self._invocation_http_requests,
        )

    def run(
        self,
        *,
        refresh: bool = False,
        max_batches: int | None = None,
        reparse_incomplete: bool = False,
    ) -> MovieLatestResult:
        if max_batches is not None and max_batches < 0:
            raise ResourceIndexError(CONFIG_ERROR, "max_batches must not be negative", {})
        self._snapshot_changed = False
        self._invocation_http_requests = 0
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
            self._sync_success(job_id, snapshot)
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
                first_candidate = self._candidate(by_rank[ranks[0]])
                crawler = self._build_crawler(
                    policy=self._policy(self.batch_max_requests),
                    endpoint=self._endpoint_for_origin(first_candidate.endpoint_origin),
                )
                errors: dict[int, str] = {}
                processed_ranks: list[int] = []
                created = 0
                updated = 0
                resources_created = 0
                resources_updated = 0
                cancelled = False
                hard_stop = False
                budget_stop = False
                self._log("movie batch started", source_id=self.source_id, job_id=job_id, run_id=run_id, ranks=ranks)
                try:
                    for rank in ranks:
                        candidate = self._candidate(by_rank[rank])
                        processed_ranks.append(rank)
                        try:
                            movie = crawler.crawl_movie_detail(candidate)
                            movie = replace(
                                movie,
                                content_kind=candidate.content_kind,
                                series_title=candidate.series_title or movie.series_title,
                                season_number=candidate.season_number or movie.season_number,
                                episode_number=candidate.episode_number or movie.episode_number,
                                episode_label=candidate.episode_label or movie.episode_label,
                                update_status=candidate.update_status or movie.update_status,
                                brand_id=candidate.brand_id or movie.brand_id,
                                endpoint_origin=candidate.endpoint_origin or movie.endpoint_origin,
                            )
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
                            if exc.error_code == LIVE_REQUEST_BUDGET_EXHAUSTED:
                                budget_stop = True
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
                self._invocation_http_requests += crawler.http_requests
                self._export_feed(job_id, snapshot)
                batches += 1
                self._log(
                    "movie batch finished",
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
                if budget_stop:
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
