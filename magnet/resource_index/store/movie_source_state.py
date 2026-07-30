"""Durable low-frequency and daily-budget state for movie sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository, _iso


@dataclass(frozen=True)
class MovieSourceReservation:
    allowed: bool
    reason: str
    reserved_requests: int
    remaining_daily_requests: int
    next_due_at: str | None


class MovieSourceStateStore:
    def __init__(self, repo: SqliteResourceRepository) -> None:
        self.repo = repo
        self.conn = repo.conn

    def get(self, source_id: str) -> dict[str, object] | None:
        row = self.conn.execute(
            "SELECT * FROM movie_source_state WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        return dict(row) if row else None

    def reserve(
        self,
        *,
        source_id: str,
        now: datetime,
        minimum_interval_hours: int,
        daily_budget: int,
        requested_requests: int,
    ) -> MovieSourceReservation:
        if requested_requests <= 0 or daily_budget <= 0 or minimum_interval_hours < 0:
            raise ValueError("movie source reservation values are invalid")
        now_s = _iso(now)
        assert now_s is not None
        today = now.date().isoformat()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT * FROM movie_source_state WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            reserved = 0
            last_attempt_at = None
            consecutive_failures = 0
            if row is not None:
                if row["daily_budget_date"] == today:
                    reserved = int(row["daily_reserved_requests"] or 0)
                last_attempt_at = row["last_attempt_at"]
                consecutive_failures = int(row["consecutive_failures"] or 0)
            next_due_at = None
            if last_attempt_at:
                parsed = datetime.fromisoformat(str(last_attempt_at).replace("Z", "+00:00"))
                failure_multiplier = 2 ** min(consecutive_failures, 3)
                effective_interval_hours = min(
                    72,
                    minimum_interval_hours * failure_multiplier,
                )
                next_due = parsed + timedelta(hours=effective_interval_hours)
                if now < next_due:
                    next_due_at = _iso(next_due)
                    self.conn.execute("ROLLBACK")
                    return MovieSourceReservation(
                        allowed=False,
                        reason=(
                            "failure_backoff"
                            if consecutive_failures > 0
                            else "minimum_interval"
                        ),
                        reserved_requests=0,
                        remaining_daily_requests=max(0, daily_budget - reserved),
                        next_due_at=next_due_at,
                    )
            remaining = max(0, daily_budget - reserved)
            if requested_requests > remaining:
                self.conn.execute("ROLLBACK")
                return MovieSourceReservation(
                    allowed=False,
                    reason="daily_budget",
                    reserved_requests=0,
                    remaining_daily_requests=remaining,
                    next_due_at=next_due_at,
                )
            new_reserved = reserved + requested_requests
            self.conn.execute(
                """
                INSERT INTO movie_source_state(
                    source_id, last_attempt_at, daily_budget_date,
                    daily_reserved_requests, consecutive_failures, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    last_attempt_at = excluded.last_attempt_at,
                    daily_budget_date = excluded.daily_budget_date,
                    daily_reserved_requests = excluded.daily_reserved_requests,
                    updated_at = excluded.updated_at
                """,
                (source_id, now_s, today, new_reserved, now_s),
            )
            self.conn.execute("COMMIT")
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise
        return MovieSourceReservation(
            allowed=True,
            reason="reserved",
            reserved_requests=requested_requests,
            remaining_daily_requests=daily_budget - new_reserved,
            next_due_at=None,
        )

    def complete(
        self,
        *,
        source_id: str,
        now: datetime,
        reserved_requests: int,
        actual_requests: int,
        snapshot_hash: str | None,
        success: bool,
    ) -> None:
        if actual_requests < 0 or reserved_requests < actual_requests:
            raise ValueError("actual requests exceed reserved requests")
        now_s = _iso(now)
        assert now_s is not None
        refund = reserved_requests - actual_requests
        self.conn.execute(
            """
            UPDATE movie_source_state SET
                daily_reserved_requests = MAX(0, daily_reserved_requests - ?),
                last_completed_at = CASE WHEN ? THEN ? ELSE last_completed_at END,
                last_snapshot_hash = COALESCE(?, last_snapshot_hash),
                consecutive_failures = CASE
                    WHEN ? THEN 0 ELSE consecutive_failures + 1
                END,
                updated_at = ?
            WHERE source_id = ?
            """,
            (
                refund,
                int(success),
                now_s,
                snapshot_hash,
                int(success),
                now_s,
                source_id,
            ),
        )

    def status(self, *, source_id: str, daily_budget: int) -> dict[str, object]:
        row = self.get(source_id)
        if row is None:
            return {
                "source_id": source_id,
                "status": "never_run",
                "daily_request_budget": daily_budget,
                "daily_reserved_requests": 0,
                "remaining_daily_requests": daily_budget,
            }
        reserved = int(row["daily_reserved_requests"] or 0)
        return {
            **row,
            "status": "ready",
            "daily_request_budget": daily_budget,
            "remaining_daily_requests": max(0, daily_budget - reserved),
        }
