"""Durable latest-list crawl job state."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from magnet.resource_index.errors import LATEST_BATCH_INTERRUPTED
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository, _iso


class LatestCrawlJobStore:
    def __init__(self, repo: SqliteResourceRepository) -> None:
        self.repo = repo
        self.conn = repo.conn

    def create_or_get_job(
        self,
        *,
        job_id: str,
        source_id: str,
        target_count: int,
        batch_size: int,
        max_attempts: int,
        snapshot_hash: str,
        snapshot: dict[str, Any],
        snapshot_path: str,
        feed_path: str,
        snapshot_http_requests: int,
        now: datetime,
    ) -> dict[str, Any]:
        now_s = _iso(now)
        assert now_s is not None
        existing = self.get_job(job_id)
        if existing is not None:
            self.conn.execute(
                """
                UPDATE latest_crawl_jobs SET
                    snapshot_path = ?, feed_path = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (snapshot_path, feed_path, _iso(now), job_id),
            )
            refreshed = self.get_job(job_id)
            assert refreshed is not None
            return refreshed
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                """
                INSERT INTO latest_crawl_jobs(
                    job_id, source_id, target_count, batch_size, max_attempts,
                    snapshot_hash, snapshot_json, snapshot_path, feed_path,
                    status, snapshot_http_requests, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    job_id,
                    source_id,
                    target_count,
                    batch_size,
                    max_attempts,
                    snapshot_hash,
                    json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
                    snapshot_path,
                    feed_path,
                    snapshot_http_requests,
                    now_s,
                    now_s,
                ),
            )
            for item in snapshot["items"]:
                self.conn.execute(
                    """
                    INSERT INTO latest_crawl_items(
                        job_id, rank, detail_url, source_item_key, content_code,
                        listing_title, status, attempts, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?)
                    """,
                    (
                        job_id,
                        int(item["rank"]),
                        item["detail_url"],
                        item.get("source_item_key"),
                        item.get("content_code"),
                        item.get("listing_title"),
                        now_s,
                    ),
                )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        created = self.get_job(job_id)
        assert created is not None
        return created

    def get_job(self, job_id: str | None) -> dict[str, Any] | None:
        if not job_id:
            return None
        row = self.conn.execute(
            "SELECT * FROM latest_crawl_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_job_by_snapshot(
        self,
        *,
        source_id: str,
        target_count: int,
        snapshot_hash: str,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT * FROM latest_crawl_jobs
            WHERE source_id = ? AND target_count = ? AND snapshot_hash = ?
            """,
            (source_id, target_count, snapshot_hash),
        ).fetchone()
        return dict(row) if row else None

    def items(self, job_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM latest_crawl_items WHERE job_id = ? ORDER BY rank",
            (job_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def recover_running(self, job_id: str, *, now: datetime) -> int:
        now_s = _iso(now)
        assert now_s is not None
        rows = self.conn.execute(
            """
            SELECT rank, last_run_id
            FROM latest_crawl_items
            WHERE job_id = ? AND status = 'running'
            ORDER BY rank
            """,
            (job_id,),
        ).fetchall()
        if not rows:
            return 0
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                run_id = row["last_run_id"]
                if run_id:
                    ingest = self.conn.execute(
                        "SELECT status, errors, error_summary_json FROM ingest_runs WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()
                    if ingest is not None and ingest["status"] == "running":
                        try:
                            summary = json.loads(ingest["error_summary_json"] or "{}")
                        except json.JSONDecodeError:
                            summary = {}
                        summary[LATEST_BATCH_INTERRUPTED] = (
                            summary.get(LATEST_BATCH_INTERRUPTED, 0) + 1
                        )
                        self.conn.execute(
                            """
                            UPDATE ingest_runs SET
                                status = 'failed', finished_at = ?, errors = ?,
                                error_summary_json = ?
                            WHERE run_id = ? AND status = 'running'
                            """,
                            (
                                now_s,
                                int(ingest["errors"] or 0) + 1,
                                json.dumps(summary, ensure_ascii=False, sort_keys=True),
                                run_id,
                            ),
                        )
                self.conn.execute(
                    """
                    UPDATE latest_crawl_items SET
                        status = 'pending', last_error_code = ?, updated_at = ?
                    WHERE job_id = ? AND rank = ? AND status = 'running'
                    """,
                    (LATEST_BATCH_INTERRUPTED, now_s, job_id, row["rank"]),
                )
            self.conn.execute(
                """
                UPDATE latest_crawl_jobs SET status = 'paused', updated_at = ?
                WHERE job_id = ? AND status = 'running'
                """,
                (now_s, job_id),
            )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return len(rows)

    def close_interrupted_ingest_run(self, run_id: str, *, now: datetime) -> bool:
        now_s = _iso(now)
        assert now_s is not None
        row = self.conn.execute(
            "SELECT status, errors, error_summary_json FROM ingest_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None or row["status"] != "running":
            return False
        try:
            summary = json.loads(row["error_summary_json"] or "{}")
        except json.JSONDecodeError:
            summary = {}
        summary[LATEST_BATCH_INTERRUPTED] = summary.get(LATEST_BATCH_INTERRUPTED, 0) + 1
        self.conn.execute(
            """
            UPDATE ingest_runs SET
                status = 'failed', finished_at = ?, errors = ?, error_summary_json = ?
            WHERE run_id = ? AND status = 'running'
            """,
            (
                now_s,
                int(row["errors"] or 0) + 1,
                json.dumps(summary, ensure_ascii=False, sort_keys=True),
                run_id,
            ),
        )
        return True

    def sync_success_from_observations(self, job_id: str, *, now: datetime) -> int:
        now_s = _iso(now)
        assert now_s is not None
        cursor = self.conn.execute(
            """
            UPDATE latest_crawl_items
            SET status = 'success', last_error_code = NULL, updated_at = ?
            WHERE job_id = ?
              AND status <> 'success'
              AND EXISTS (
                  SELECT 1 FROM content_observations o
                  JOIN latest_crawl_jobs j ON j.job_id = latest_crawl_items.job_id
                  WHERE o.source_id = j.source_id
                    AND o.detail_url = latest_crawl_items.detail_url
              )
            """,
            (now_s, job_id),
        )
        return int(cursor.rowcount or 0)

    def next_batch(
        self,
        job_id: str,
        *,
        batch_size: int,
        max_attempts: int,
        exclude_ranks: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        excluded = sorted(exclude_ranks or set())
        exclusion_sql = ""
        parameters: list[Any] = [job_id, max_attempts]
        if excluded:
            placeholders = ",".join("?" for _ in excluded)
            exclusion_sql = f" AND rank NOT IN ({placeholders})"
            parameters.extend(excluded)
        parameters.append(batch_size)
        rows = self.conn.execute(
            f"""
            SELECT * FROM latest_crawl_items
            WHERE job_id = ?
              AND status IN ('pending', 'failed')
              AND attempts < ?
              {exclusion_sql}
            ORDER BY rank
            LIMIT ?
            """,
            tuple(parameters),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_batch_running(
        self,
        job_id: str,
        *,
        ranks: list[int],
        run_id: str,
        now: datetime,
    ) -> None:
        if not ranks:
            return
        now_s = _iso(now)
        assert now_s is not None
        placeholders = ",".join("?" for _ in ranks)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                f"""
                UPDATE latest_crawl_items SET
                    status = 'running', attempts = attempts + 1,
                    last_run_id = ?, last_error_code = NULL, updated_at = ?
                WHERE job_id = ? AND rank IN ({placeholders})
                """,
                (run_id, now_s, job_id, *ranks),
            )
            self.conn.execute(
                """
                UPDATE latest_crawl_jobs SET status = 'running', updated_at = ?
                WHERE job_id = ?
                """,
                (now_s, job_id),
            )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def reconcile_batch(
        self,
        job_id: str,
        *,
        ranks: list[int],
        run_id: str,
        now: datetime,
        fallback_error_code: str | None,
        http_requests: int,
    ) -> tuple[int, int]:
        if not ranks:
            return (0, 0)
        now_s = _iso(now)
        assert now_s is not None
        placeholders = ",".join("?" for _ in ranks)
        items = self.conn.execute(
            f"""
            SELECT i.rank, i.detail_url, j.source_id
            FROM latest_crawl_items i
            JOIN latest_crawl_jobs j ON j.job_id = i.job_id
            WHERE i.job_id = ? AND i.rank IN ({placeholders})
            ORDER BY i.rank
            """,
            (job_id, *ranks),
        ).fetchall()
        succeeded = 0
        failed = 0
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for item in items:
                observed = self.conn.execute(
                    """
                    SELECT 1 FROM content_observations
                    WHERE source_id = ? AND detail_url = ?
                    LIMIT 1
                    """,
                    (item["source_id"], item["detail_url"]),
                ).fetchone()
                if observed is not None:
                    status = "success"
                    error_code = None
                    succeeded += 1
                else:
                    status = "failed"
                    error_code = fallback_error_code or "UNEXPECTED"
                    failed += 1
                self.conn.execute(
                    """
                    UPDATE latest_crawl_items SET
                        status = ?, last_run_id = ?, last_error_code = ?, updated_at = ?
                    WHERE job_id = ? AND rank = ?
                    """,
                    (status, run_id, error_code, now_s, job_id, item["rank"]),
                )
            self.conn.execute(
                """
                UPDATE latest_crawl_jobs SET
                    detail_http_requests = detail_http_requests + ?, updated_at = ?
                WHERE job_id = ?
                """,
                (http_requests, now_s, job_id),
            )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return succeeded, failed

    def set_job_status(
        self,
        job_id: str,
        *,
        status: str,
        now: datetime,
        error_summary: dict[str, int] | None = None,
    ) -> None:
        now_s = _iso(now)
        assert now_s is not None
        completed_at = now_s if status in {"success", "partial", "failed"} else None
        self.conn.execute(
            """
            UPDATE latest_crawl_jobs SET
                status = ?, updated_at = ?, completed_at = ?, error_summary_json = ?
            WHERE job_id = ?
            """,
            (
                status,
                now_s,
                completed_at,
                json.dumps(error_summary or {}, ensure_ascii=False, sort_keys=True),
                job_id,
            ),
        )

    def summary(self, job_id: str) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS target_count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS covered_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_count,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN status <> 'success' AND attempts >= (
                    SELECT max_attempts FROM latest_crawl_jobs WHERE job_id = ?
                ) THEN 1 ELSE 0 END) AS exhausted_count
            FROM latest_crawl_items
            WHERE job_id = ?
            """,
            (job_id, job_id),
        ).fetchone()
        assert row is not None
        return {key: int(row[key] or 0) for key in row.keys()}
