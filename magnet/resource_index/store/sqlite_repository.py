"""SQLite implementation of ResourceRepository."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from magnet.resource_index.domain.enums import AliasType
from magnet.resource_index.domain.identity import observation_id_for
from magnet.resource_index.domain.models import ContentItem, ParsedContentBundle, ResourceRelease
from magnet.resource_index.domain.validation import validate_bundle
from magnet.resource_index.errors import (
    DATABASE_CONSTRAINT_ERROR,
    RESOURCE_CONTENT_CONFLICT,
    ConflictError,
    StorageError,
)
from magnet.resource_index.normalize.text import normalize_whitespace
from magnet.resource_index.store.migrations import apply_migrations
from magnet.resource_index.store.repository import TableCounts, UpsertStats


def _iso(dt: datetime | date | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(microsecond=0).isoformat() + "Z"
        return dt.astimezone().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return dt.isoformat()


def _coalesce(new: Any, old: Any) -> Any:
    """Prefer non-empty new; never overwrite non-empty old with empty new."""
    if new is None:
        return old
    if isinstance(new, str) and not new.strip():
        return old
    return new


class SqliteResourceRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")

    def init_schema(self) -> str:
        return apply_migrations(self.conn)

    def close(self) -> None:
        self.conn.close()

    def start_ingest_run(
        self,
        run_id: str,
        source_id: str,
        mode: str,
        started_at: datetime,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO ingest_runs(
                run_id, source_id, mode, started_at, status
            ) VALUES (?, ?, ?, ?, 'running')
            """,
            (run_id, source_id, mode, _iso(started_at)),
        )

    def finish_ingest_run(
        self,
        run_id: str,
        *,
        status: str,
        finished_at: datetime,
        documents_seen: int,
        contents_created: int,
        contents_updated: int,
        resources_created: int,
        resources_updated: int,
        warnings: int,
        errors: int,
        error_summary: dict[str, Any],
    ) -> None:
        self.conn.execute(
            """
            UPDATE ingest_runs SET
                finished_at = ?,
                status = ?,
                documents_seen = ?,
                contents_created = ?,
                contents_updated = ?,
                resources_created = ?,
                resources_updated = ?,
                warnings = ?,
                errors = ?,
                error_summary_json = ?
            WHERE run_id = ?
            """,
            (
                _iso(finished_at),
                status,
                documents_seen,
                contents_created,
                contents_updated,
                resources_created,
                resources_updated,
                warnings,
                errors,
                json.dumps(error_summary, ensure_ascii=False, sort_keys=True),
                run_id,
            ),
        )

    def add_ingest_event(
        self,
        run_id: str,
        *,
        occurred_at: datetime,
        stage: str,
        severity: str,
        message: str,
        source_item_key: str | None = None,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO ingest_events(
                run_id, occurred_at, stage, severity, source_item_key,
                error_code, message, context_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _iso(occurred_at),
                stage,
                severity,
                source_item_key,
                error_code,
                message,
                json.dumps(context or {}, ensure_ascii=False, sort_keys=True),
            ),
        )

    def upsert_bundle(self, bundle: ParsedContentBundle, *, now: datetime) -> UpsertStats:
        validate_bundle(bundle)
        stats = UpsertStats(warnings=len(bundle.warnings))
        now_s = _iso(now)
        assert now_s is not None

        try:
            self.conn.execute("BEGIN IMMEDIATE")
            content = bundle.content
            existing = self.conn.execute(
                "SELECT * FROM content_items WHERE content_id = ?",
                (content.content_id,),
            ).fetchone()
            if existing is None:
                # Also check unique content_code collision under different id
                by_code = self.conn.execute(
                    "SELECT * FROM content_items WHERE content_type = ? AND content_code = ?",
                    (content.content_type.value, content.content_code),
                ).fetchone()
                if by_code is not None:
                    existing = by_code

            if existing is None:
                self._insert_content(content, now_s)
                stats.content_created = True
                content_id = content.content_id
            else:
                content_id = existing["content_id"]
                self._update_content(existing, content, now_s)
                stats.content_updated = True
                if existing["title"] and existing["title"] != content.title:
                    self._add_alias(
                        content_id,
                        existing["title"],
                        AliasType.PREVIOUS_TITLE.value,
                        now_s,
                    )

            # raw code alias
            self._add_alias(
                content_id,
                content.raw_content_code,
                AliasType.RAW_CODE.value,
                now_s,
            )
            for alias in bundle.aliases:
                self._add_alias(content_id, alias.alias, alias.alias_type.value, now_s)

            # people replace (dedupe person_id+role for safety)
            self.conn.execute("DELETE FROM content_people WHERE content_id = ?", (content_id,))
            seen_pr: set[tuple[str, str]] = set()
            for person in bundle.people:
                pr_key = (person.person_id, person.role.value)
                if pr_key in seen_pr:
                    continue
                seen_pr.add(pr_key)
                self.conn.execute(
                    """
                    INSERT INTO people(person_id, display_name, normalized_name,
                        source_profile_url, source_external_key, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(person_id) DO UPDATE SET
                        display_name = excluded.display_name,
                        normalized_name = excluded.normalized_name,
                        source_profile_url = COALESCE(excluded.source_profile_url, people.source_profile_url),
                        source_external_key = COALESCE(excluded.source_external_key, people.source_external_key),
                        updated_at = excluded.updated_at
                    """,
                    (
                        person.person_id,
                        person.display_name,
                        normalize_whitespace(person.display_name).casefold(),
                        person.source_profile_url,
                        person.source_external_key,
                        now_s,
                        now_s,
                    ),
                )
                self.conn.execute(
                    """
                    INSERT INTO content_people(content_id, person_id, role, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (content_id, person.person_id, person.role.value, person.sort_order),
                )

            # tags replace
            self.conn.execute("DELETE FROM content_tags WHERE content_id = ?", (content_id,))
            for tag in bundle.tags:
                self.conn.execute(
                    """
                    INSERT INTO tags(tag_id, display_name, normalized_name,
                        source_url, source_external_key, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tag_id) DO UPDATE SET
                        display_name = excluded.display_name,
                        normalized_name = excluded.normalized_name,
                        source_url = COALESCE(excluded.source_url, tags.source_url),
                        source_external_key = COALESCE(excluded.source_external_key, tags.source_external_key),
                        updated_at = excluded.updated_at
                    """,
                    (
                        tag.tag_id,
                        tag.display_name,
                        normalize_whitespace(tag.display_name).casefold(),
                        tag.source_url,
                        tag.source_external_key,
                        now_s,
                        now_s,
                    ),
                )
                self.conn.execute(
                    "INSERT INTO content_tags(content_id, tag_id) VALUES (?, ?)",
                    (content_id, tag.tag_id),
                )

            # media upsert
            for media in bundle.media:
                self.conn.execute(
                    """
                    INSERT INTO media_assets(
                        media_id, content_id, media_type, source_url, stored_url,
                        content_hash, width, height, adult, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    ON CONFLICT(media_id) DO UPDATE SET
                        updated_at = excluded.updated_at
                    """,
                    (
                        media.media_id,
                        content_id,
                        media.media_type.value,
                        media.source_url,
                        media.stored_url,
                        media.content_hash,
                        media.width,
                        media.height,
                        media.status.value,
                        now_s,
                        now_s,
                    ),
                )

            for resource in bundle.resources:
                created = self._upsert_resource(resource, content_id=content_id, now_s=now_s)
                if created:
                    stats.resources_created += 1
                else:
                    stats.resources_updated += 1
                self._upsert_observation(
                    resource_id=resource.resource_id,
                    content_id=content_id,
                    source_id=content.source_id,
                    source_item_key=content.source_item_key,
                    detail_url=content.detail_url,
                    parser_version=content.parser_version,
                    raw_document_hash=bundle.provenance.resource_document_sha256
                    or bundle.provenance.document_sha256,
                    now_s=now_s,
                )

            self.conn.execute("COMMIT")
        except ConflictError:
            self.conn.execute("ROLLBACK")
            raise
        except sqlite3.Error as exc:
            self.conn.execute("ROLLBACK")
            raise StorageError(
                DATABASE_CONSTRAINT_ERROR,
                str(exc),
                {"content_id": bundle.content.content_id},
            ) from exc
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return stats

    def _insert_content(self, content: ContentItem, now_s: str) -> None:
        self.conn.execute(
            """
            INSERT INTO content_items(
                content_id, content_type, content_code, raw_content_code, title,
                original_title, release_date, duration_minutes, maker_name,
                publisher_name, label_name, series_name, cover_source_url,
                detail_url, adult, source_id, source_item_key, parser_version,
                risk_status, first_seen_at, last_seen_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'manual_review', ?, ?, ?, ?)
            """,
            (
                content.content_id,
                content.content_type.value,
                content.content_code,
                content.raw_content_code,
                content.title,
                content.original_title,
                _iso(content.release_date),
                content.duration_minutes,
                content.maker_name,
                content.publisher_name,
                content.label_name,
                content.series_name,
                content.cover_source_url,
                content.detail_url,
                content.source_id,
                content.source_item_key,
                content.parser_version,
                now_s,
                now_s,
                now_s,
                now_s,
            ),
        )

    def _update_content(self, existing: sqlite3.Row, content: ContentItem, now_s: str) -> None:
        self.conn.execute(
            """
            UPDATE content_items SET
                title = ?,
                original_title = ?,
                release_date = ?,
                duration_minutes = ?,
                maker_name = ?,
                publisher_name = ?,
                label_name = ?,
                series_name = ?,
                cover_source_url = ?,
                detail_url = ?,
                parser_version = ?,
                last_seen_at = ?,
                updated_at = ?
            WHERE content_id = ?
            """,
            (
                _coalesce(content.title, existing["title"]),
                _coalesce(content.original_title, existing["original_title"]),
                _coalesce(_iso(content.release_date), existing["release_date"]),
                _coalesce(content.duration_minutes, existing["duration_minutes"]),
                _coalesce(content.maker_name, existing["maker_name"]),
                _coalesce(content.publisher_name, existing["publisher_name"]),
                _coalesce(content.label_name, existing["label_name"]),
                _coalesce(content.series_name, existing["series_name"]),
                _coalesce(content.cover_source_url, existing["cover_source_url"]),
                _coalesce(content.detail_url, existing["detail_url"]),
                content.parser_version or existing["parser_version"],
                now_s,
                now_s,
                existing["content_id"],
            ),
        )

    def _add_alias(self, content_id: str, alias: str, alias_type: str, now_s: str) -> None:
        text = normalize_whitespace(alias)
        if not text:
            return
        self.conn.execute(
            """
            INSERT OR IGNORE INTO content_aliases(
                content_id, alias, normalized_alias, alias_type, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (content_id, text, text.casefold(), alias_type, now_s),
        )

    def _upsert_resource(
        self,
        resource: ResourceRelease,
        *,
        content_id: str,
        now_s: str,
    ) -> bool:
        existing = self.conn.execute(
            "SELECT * FROM resource_releases WHERE info_hash = ?",
            (resource.info_hash,),
        ).fetchone()
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO resource_releases(
                    resource_id, content_id, info_hash, magnet_uri, display_title,
                    size_bytes, size_display, published_at, has_subtitle, has_hd,
                    quality_tags_json, first_seen_at, last_seen_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resource.resource_id,
                    content_id,
                    resource.info_hash,
                    resource.magnet_uri,
                    resource.display_title,
                    resource.size_bytes,
                    resource.size_display,
                    _iso(resource.published_at),
                    None if resource.has_subtitle is None else int(resource.has_subtitle),
                    None if resource.has_hd is None else int(resource.has_hd),
                    json.dumps(list(resource.quality_tags), ensure_ascii=False),
                    now_s,
                    now_s,
                    now_s,
                    now_s,
                ),
            )
            return True

        if existing["content_id"] != content_id:
            raise ConflictError(
                RESOURCE_CONTENT_CONFLICT,
                "same info_hash linked to different content",
                {
                    "info_hash": resource.info_hash,
                    "existing_content_id": existing["content_id"],
                    "new_content_id": content_id,
                },
            )

        self.conn.execute(
            """
            UPDATE resource_releases SET
                magnet_uri = ?,
                display_title = ?,
                size_bytes = ?,
                size_display = ?,
                published_at = ?,
                has_subtitle = ?,
                has_hd = ?,
                quality_tags_json = ?,
                last_seen_at = ?,
                updated_at = ?
            WHERE resource_id = ?
            """,
            (
                resource.magnet_uri or existing["magnet_uri"],
                _coalesce(resource.display_title, existing["display_title"]),
                _coalesce(resource.size_bytes, existing["size_bytes"]),
                _coalesce(resource.size_display, existing["size_display"]),
                _coalesce(_iso(resource.published_at), existing["published_at"]),
                _coalesce(
                    None if resource.has_subtitle is None else int(resource.has_subtitle),
                    existing["has_subtitle"],
                ),
                _coalesce(
                    None if resource.has_hd is None else int(resource.has_hd),
                    existing["has_hd"],
                ),
                json.dumps(
                    list(resource.quality_tags)
                    if resource.quality_tags
                    else json.loads(existing["quality_tags_json"] or "[]"),
                    ensure_ascii=False,
                ),
                now_s,
                now_s,
                existing["resource_id"],
            ),
        )
        return False

    def _upsert_observation(
        self,
        *,
        resource_id: str,
        content_id: str,
        source_id: str,
        source_item_key: str,
        detail_url: str,
        parser_version: str,
        raw_document_hash: str | None,
        now_s: str,
    ) -> None:
        obs_id = observation_id_for(resource_id, source_id, source_item_key)
        existing = self.conn.execute(
            """
            SELECT observation_id, seen_count FROM resource_observations
            WHERE resource_id = ? AND source_id = ? AND source_item_key = ?
            """,
            (resource_id, source_id, source_item_key),
        ).fetchone()
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO resource_observations(
                    observation_id, resource_id, content_id, source_id, source_item_key,
                    detail_url, parser_version, raw_document_hash,
                    first_seen_at, last_seen_at, seen_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    obs_id,
                    resource_id,
                    content_id,
                    source_id,
                    source_item_key,
                    detail_url,
                    parser_version,
                    raw_document_hash,
                    now_s,
                    now_s,
                ),
            )
        else:
            self.conn.execute(
                """
                UPDATE resource_observations SET
                    last_seen_at = ?,
                    seen_count = seen_count + 1,
                    parser_version = ?,
                    raw_document_hash = COALESCE(?, raw_document_hash)
                WHERE observation_id = ?
                """,
                (now_s, parser_version, raw_document_hash, existing["observation_id"]),
            )

    def get_content_by_code(self, content_code: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM content_items WHERE content_code = ?",
            (content_code.upper(),),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        people = self.conn.execute(
            """
            SELECT p.display_name, cp.role, cp.sort_order
            FROM content_people cp
            JOIN people p ON p.person_id = cp.person_id
            WHERE cp.content_id = ?
            ORDER BY cp.sort_order, p.display_name
            """,
            (data["content_id"],),
        ).fetchall()
        tags = self.conn.execute(
            """
            SELECT t.display_name
            FROM content_tags ct
            JOIN tags t ON t.tag_id = ct.tag_id
            WHERE ct.content_id = ?
            ORDER BY t.display_name
            """,
            (data["content_id"],),
        ).fetchall()
        data["people"] = [dict(p) for p in people]
        data["tags"] = [t["display_name"] for t in tags]
        return data

    def list_resources_for_content(self, content_code: str) -> list[dict[str, Any]]:
        content = self.get_content_by_code(content_code)
        if content is None:
            return []
        rows = self.conn.execute(
            """
            SELECT * FROM resource_releases
            WHERE content_id = ?
            ORDER BY published_at DESC NULLS LAST, info_hash
            """,
            (content["content_id"],),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_contents(self, query: str, *, limit: int = 50) -> list[dict[str, Any]]:
        q = f"%{query.strip()}%"
        rows = self.conn.execute(
            """
            SELECT content_id, content_code, title, release_date, maker_name, adult
            FROM content_items
            WHERE content_code LIKE ? OR title LIKE ? OR series_name LIKE ?
            ORDER BY content_code
            LIMIT ?
            """,
            (q.upper() if query.isascii() else q, q, q, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> TableCounts:
        def c(table: str) -> int:
            return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

        without = int(
            self.conn.execute(
                """
                SELECT COUNT(*) FROM content_items c
                WHERE NOT EXISTS (
                    SELECT 1 FROM resource_releases r WHERE r.content_id = c.content_id
                )
                """
            ).fetchone()[0]
        )
        return TableCounts(
            contents=c("content_items"),
            people=c("people"),
            tags=c("tags"),
            resources=c("resource_releases"),
            observations=c("resource_observations"),
            content_people=c("content_people"),
            content_tags=c("content_tags"),
            aliases=c("content_aliases"),
            contents_without_resources=without,
        )

    def last_successful_run(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT * FROM ingest_runs
            WHERE status IN ('success', 'partial')
            ORDER BY finished_at DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def warning_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT error_code, COUNT(*) AS n
            FROM ingest_events
            WHERE severity = 'warning' AND error_code IS NOT NULL
            GROUP BY error_code
            """
        ).fetchall()
        return {r["error_code"]: int(r["n"]) for r in rows}

    def export_adult_rows(self, *, limit: int, include_review: bool) -> list[dict[str, Any]]:
        risk_filter = "" if include_review else "AND c.risk_status = 'allowed'"
        rows = self.conn.execute(
            f"""
            SELECT
                c.content_id,
                c.content_type,
                c.content_code,
                c.title,
                c.release_date,
                c.duration_minutes,
                c.maker_name,
                c.series_name,
                c.adult,
                c.risk_status,
                (
                    SELECT COUNT(*) FROM resource_releases r WHERE r.content_id = c.content_id
                ) AS resource_count,
                (
                    SELECT MAX(r.last_seen_at) FROM resource_releases r WHERE r.content_id = c.content_id
                ) AS latest_resource_at
            FROM content_items c
            WHERE c.adult = 1 {risk_filter}
            ORDER BY c.content_code
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            people = [
                r["display_name"]
                for r in self.conn.execute(
                    """
                    SELECT p.display_name FROM content_people cp
                    JOIN people p ON p.person_id = cp.person_id
                    WHERE cp.content_id = ?
                    ORDER BY cp.sort_order, p.display_name
                    """,
                    (row["content_id"],),
                ).fetchall()
            ]
            tags = [
                r["display_name"]
                for r in self.conn.execute(
                    """
                    SELECT t.display_name FROM content_tags ct
                    JOIN tags t ON t.tag_id = ct.tag_id
                    WHERE ct.content_id = ?
                    ORDER BY t.display_name
                    """,
                    (row["content_id"],),
                ).fetchall()
            ]
            item = dict(row)
            item["people"] = people
            item["tags"] = tags
            result.append(item)
        return result
