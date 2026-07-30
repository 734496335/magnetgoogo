"""Idempotent durable repairs for DYTT resources parsed by older versions."""

from __future__ import annotations

from dataclasses import dataclass

from magnet.resource_index.adapters.dytt.parser import direct_resource_kind, unwrap_jianpian_url
from magnet.resource_index.store.movie_repository import movie_resource_id_for
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository


@dataclass(frozen=True)
class DyttResourceRepairResult:
    examined: int
    repaired: int
    merged: int
    unchanged: int


def normalize_dytt_player_resources(
    repo: SqliteResourceRepository,
    *,
    source_id: str = "dytt8899",
) -> DyttResourceRepairResult:
    repo.init_schema()
    rows = repo.conn.execute(
        """
        SELECT r.*
        FROM movie_external_resources r
        JOIN movie_items m ON m.movie_id = r.movie_id
        WHERE m.source_id = ?
          AND r.resource_type = 'player'
          AND (r.provider = 'jianpian' OR r.resource_url LIKE 'jianpian://%')
        ORDER BY r.movie_id, r.resource_id
        """,
        (source_id,),
    ).fetchall()
    repaired = 0
    merged = 0
    unchanged = 0
    repo.conn.execute("BEGIN IMMEDIATE")
    try:
        for row in rows:
            target = unwrap_jianpian_url(str(row["resource_url"] or ""))
            if target is None:
                unchanged += 1
                continue
            resource_type, provider = direct_resource_kind(target)
            new_id = movie_resource_id_for(str(row["movie_id"]), target)
            existing = repo.conn.execute(
                """
                SELECT resource_id
                FROM movie_external_resources
                WHERE movie_id = ? AND resource_url = ?
                """,
                (row["movie_id"], target),
            ).fetchone()
            if existing is not None and existing["resource_id"] != row["resource_id"]:
                repo.conn.execute(
                    """
                    UPDATE movie_external_resources
                    SET resource_type = ?, provider = ?,
                        display_title = CASE
                            WHEN TRIM(display_title) = '' THEN ? ELSE display_title
                        END,
                        first_seen_at = MIN(first_seen_at, ?),
                        last_seen_at = MAX(last_seen_at, ?),
                        updated_at = MAX(updated_at, ?)
                    WHERE resource_id = ?
                    """,
                    (
                        resource_type,
                        provider,
                        row["display_title"],
                        row["first_seen_at"],
                        row["last_seen_at"],
                        row["updated_at"],
                        existing["resource_id"],
                    ),
                )
                repo.conn.execute(
                    "DELETE FROM movie_external_resources WHERE resource_id = ?",
                    (row["resource_id"],),
                )
                merged += 1
                continue
            repo.conn.execute(
                """
                UPDATE movie_external_resources
                SET resource_id = ?, resource_type = ?, provider = ?, resource_url = ?
                WHERE resource_id = ?
                """,
                (new_id, resource_type, provider, target, row["resource_id"]),
            )
            repaired += 1
        repo.conn.execute("COMMIT")
    except Exception:
        repo.conn.execute("ROLLBACK")
        raise
    return DyttResourceRepairResult(
        examined=len(rows),
        repaired=repaired,
        merged=merged,
        unchanged=unchanged,
    )
