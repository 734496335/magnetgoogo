"""Export the durable per-source movie database as a complete library feed."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.store.movie_repository import MovieRepository
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def export_source_library_feed(
    *,
    db_path: str | Path,
    source_id: str,
    output_path: str | Path,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Export every durable media row for one source, not only its latest window."""
    if not source_id.strip():
        raise ResourceIndexError(CONFIG_ERROR, "source_id is required", {})
    repo = SqliteResourceRepository(Path(db_path))
    try:
        repo.init_schema()
        movie_repo = MovieRepository(repo)
        rows = repo.conn.execute(
            """
            SELECT detail_url, source_item_key
            FROM movie_items
            WHERE source_id = ?
            ORDER BY
                COALESCE(NULLIF(update_date, ''), NULLIF(release_date, ''), last_seen_at) DESC,
                last_seen_at DESC,
                movie_id
            """,
            (source_id,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for rank, row in enumerate(rows, start=1):
            item = movie_repo.feed_item(
                source_id=source_id,
                detail_url=str(row["detail_url"]),
                source_item_key=str(row["source_item_key"]),
                rank=rank,
            )
            if item is not None:
                items.append(item)
        counts = movie_repo.counts(source_id=source_id)
        if len(items) != counts["movies"]:
            raise ResourceIndexError(
                CONFIG_ERROR,
                "source library export count does not match durable database",
                {
                    "source_id": source_id,
                    "database_count": counts["movies"],
                    "exported_count": len(items),
                },
            )
        timestamp = generated_at or _utc_now()
        payload = {
            "schema_version": "movie-feed/1",
            "source_id": source_id,
            "generated_at": timestamp.isoformat().replace("+00:00", "Z"),
            "snapshot_captured_at": timestamp.isoformat().replace("+00:00", "Z"),
            "library_scope": "durable_all",
            "items": items,
            "summary": {
                "record_count": len(items),
                "resource_count": sum(len(item.get("resources") or []) for item in items),
                "recommended_count": sum(1 for item in items if item.get("recommended")),
                "database_movie_count": counts["movies"],
                "database_resource_count": counts["resources"],
            },
        }
        _atomic_write_json(Path(output_path), payload)
        return payload
    finally:
        repo.close()
