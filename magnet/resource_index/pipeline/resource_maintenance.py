"""Idempotent normalization and deduplication for durable media resources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, unquote

from magnet.resource_index.store.movie_repository import movie_resource_id_for
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository


@dataclass(frozen=True)
class ResourceMaintenanceResult:
    malformed_urls_repaired: int
    malformed_urls_merged: int
    duplicate_magnets_removed: int


def _normalized_http_typo(value: str) -> str:
    stripped = value.strip()
    folded = stripped.casefold()
    if folded.startswith("ttps://") or folded.startswith("ttp://"):
        return "h" + stripped
    return stripped


def _canonical_magnet(info_hash: str, urls: list[str]) -> tuple[str, str]:
    trackers: set[str] = set()
    display_names: list[str] = []
    for url in urls:
        for key, value in parse_qsl(url.removeprefix("magnet:?"), keep_blank_values=False):
            lower = key.casefold()
            if lower == "tr" and value.strip():
                trackers.add(unquote(value).strip())
            elif lower == "dn" and value.strip():
                display_names.append(unquote(value).strip())
    display_name = max(display_names, key=len) if display_names else info_hash
    parts = [f"xt=urn:btih:{info_hash}", f"dn={quote(display_name, safe='')}" ]
    parts.extend(f"tr={quote(tracker, safe=':/?&=%')}" for tracker in sorted(trackers))
    return "magnet:?" + "&".join(parts), display_name


def normalize_durable_resources(
    repo: SqliteResourceRepository,
    *,
    source_id: str,
) -> ResourceMaintenanceResult:
    repo.init_schema()
    malformed_rows = repo.conn.execute(
        """
        SELECT r.*
        FROM movie_resources r
        JOIN movie_items m ON m.movie_id = r.movie_id
        WHERE m.source_id = ?
          AND r.resource_type = 'cloud'
          AND (r.resource_url LIKE 'ttps://%' OR r.resource_url LIKE 'ttp://%')
        ORDER BY r.movie_id, r.resource_id
        """,
        (source_id,),
    ).fetchall()
    duplicate_groups = repo.conn.execute(
        """
        SELECT r.movie_id, r.info_hash
        FROM movie_resources r
        JOIN movie_items m ON m.movie_id = r.movie_id
        WHERE m.source_id = ?
          AND r.resource_type = 'magnet'
          AND r.info_hash IS NOT NULL
          AND TRIM(r.info_hash) <> ''
        GROUP BY r.movie_id, r.info_hash
        HAVING COUNT(*) > 1
        ORDER BY r.movie_id, r.info_hash
        """,
        (source_id,),
    ).fetchall()
    repaired = 0
    merged = 0
    removed = 0
    repo.conn.execute("BEGIN IMMEDIATE")
    try:
        for row in malformed_rows:
            target = _normalized_http_typo(str(row["resource_url"] or ""))
            new_id = movie_resource_id_for(str(row["movie_id"]), target)
            existing = repo.conn.execute(
                "SELECT resource_id FROM movie_resources WHERE movie_id = ? AND resource_url = ?",
                (row["movie_id"], target),
            ).fetchone()
            if existing is not None and existing["resource_id"] != row["resource_id"]:
                repo.conn.execute(
                    "DELETE FROM movie_resources WHERE resource_id = ?",
                    (row["resource_id"],),
                )
                merged += 1
            else:
                repo.conn.execute(
                    """
                    UPDATE movie_resources
                    SET resource_id = ?, resource_url = ?, updated_at = last_seen_at
                    WHERE resource_id = ?
                    """,
                    (new_id, target, row["resource_id"]),
                )
                repaired += 1

        for group in duplicate_groups:
            rows = repo.conn.execute(
                """
                SELECT *
                FROM movie_resources
                WHERE movie_id = ? AND info_hash = ? AND resource_type = 'magnet'
                ORDER BY resource_id
                """,
                (group["movie_id"], group["info_hash"]),
            ).fetchall()
            if len(rows) < 2:
                continue
            urls = [str(row["resource_url"]) for row in rows]
            canonical_url, display_name = _canonical_magnet(str(group["info_hash"]), urls)
            winner = max(
                rows,
                key=lambda row: (
                    len(str(row["resource_url"])),
                    len(str(row["display_title"])),
                    str(row["resource_id"]),
                ),
            )
            tags: list[str] = []
            for row in rows:
                try:
                    values = json.loads(str(row["quality_tags_json"] or "[]"))
                except json.JSONDecodeError:
                    values = []
                for value in values if isinstance(values, list) else []:
                    text = str(value).strip()
                    if text and text not in tags:
                        tags.append(text)
            old_ids = [str(row["resource_id"]) for row in rows]
            repo.conn.execute(
                f"DELETE FROM movie_resources WHERE resource_id IN ({','.join('?' for _ in old_ids)})",
                old_ids,
            )
            canonical_id = movie_resource_id_for(str(group["movie_id"]), canonical_url)
            repo.conn.execute(
                """
                INSERT INTO movie_resources(
                    resource_id, movie_id, resource_type, provider,
                    resource_url, info_hash, display_title, extraction_code,
                    quality_tags_json, first_seen_at, last_seen_at,
                    created_at, updated_at
                ) VALUES (?, ?, 'magnet', 'magnet', ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    canonical_id,
                    group["movie_id"],
                    canonical_url,
                    group["info_hash"],
                    display_name,
                    json.dumps(tags, ensure_ascii=False),
                    min(str(row["first_seen_at"]) for row in rows),
                    max(str(row["last_seen_at"]) for row in rows),
                    min(str(row["created_at"]) for row in rows),
                    max(str(row["updated_at"]) for row in rows),
                ),
            )
            removed += len(rows) - 1
        repo.conn.execute("COMMIT")
    except Exception:
        repo.conn.execute("ROLLBACK")
        raise
    return ResourceMaintenanceResult(
        malformed_urls_repaired=repaired,
        malformed_urls_merged=merged,
        duplicate_magnets_removed=removed,
    )
