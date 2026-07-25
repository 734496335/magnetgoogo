"""SQLite persistence for non-adult movie source data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from magnet.resource_index.adapters.sixv.models import SixVMovieDetail
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository, _iso


@dataclass(frozen=True)
class MovieUpsertStats:
    movie_created: bool
    movie_updated: bool
    resources_created: int
    resources_updated: int


def movie_id_for(source_id: str, source_item_key: str) -> str:
    raw = f"{source_id}\0{source_item_key}".encode("utf-8")
    return "movie:" + hashlib.sha256(raw).hexdigest()


def movie_resource_id_for(movie_id: str, resource_url: str) -> str:
    raw = f"{movie_id}\0{resource_url}".encode("utf-8")
    return "movie-resource:" + hashlib.sha256(raw).hexdigest()


class MovieRepository:
    def __init__(self, repo: SqliteResourceRepository) -> None:
        self.repo = repo
        self.conn = repo.conn

    def upsert(self, movie: SixVMovieDetail, *, now: datetime) -> MovieUpsertStats:
        now_s = _iso(now)
        assert now_s is not None
        movie_id = movie_id_for(movie.source_id, movie.source_item_key)
        existing = self.conn.execute(
            "SELECT movie_id FROM movie_items WHERE movie_id = ?",
            (movie_id,),
        ).fetchone()
        resources_created = 0
        resources_updated = 0
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                """
                INSERT INTO movie_items(
                    movie_id, source_id, source_item_key, detail_url,
                    listing_title, title, original_title, year, update_date,
                    release_date, duration_minutes, countries_json, genres_json,
                    languages_json, directors_json, actors_json, imdb_id,
                    douban_rating, douban_rating_text, douban_url,
                    cover_source_url, synopsis, recommended,
                    highlight_labels_json, quality_tags_json, parser_version,
                    raw_document_hash, first_seen_at, last_seen_at,
                    created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(movie_id) DO UPDATE SET
                    detail_url = excluded.detail_url,
                    listing_title = excluded.listing_title,
                    title = excluded.title,
                    original_title = COALESCE(excluded.original_title, movie_items.original_title),
                    year = COALESCE(excluded.year, movie_items.year),
                    update_date = COALESCE(excluded.update_date, movie_items.update_date),
                    release_date = COALESCE(excluded.release_date, movie_items.release_date),
                    duration_minutes = COALESCE(excluded.duration_minutes, movie_items.duration_minutes),
                    countries_json = CASE
                        WHEN excluded.countries_json <> '[]' THEN excluded.countries_json
                        ELSE movie_items.countries_json
                    END,
                    genres_json = CASE
                        WHEN excluded.genres_json <> '[]' THEN excluded.genres_json
                        ELSE movie_items.genres_json
                    END,
                    languages_json = CASE
                        WHEN excluded.languages_json <> '[]' THEN excluded.languages_json
                        ELSE movie_items.languages_json
                    END,
                    directors_json = CASE
                        WHEN excluded.directors_json <> '[]' THEN excluded.directors_json
                        ELSE movie_items.directors_json
                    END,
                    actors_json = CASE
                        WHEN excluded.actors_json <> '[]' THEN excluded.actors_json
                        ELSE movie_items.actors_json
                    END,
                    imdb_id = COALESCE(excluded.imdb_id, movie_items.imdb_id),
                    douban_rating = COALESCE(excluded.douban_rating, movie_items.douban_rating),
                    douban_rating_text = COALESCE(excluded.douban_rating_text, movie_items.douban_rating_text),
                    douban_url = COALESCE(excluded.douban_url, movie_items.douban_url),
                    cover_source_url = COALESCE(excluded.cover_source_url, movie_items.cover_source_url),
                    synopsis = COALESCE(excluded.synopsis, movie_items.synopsis),
                    recommended = excluded.recommended,
                    highlight_labels_json = excluded.highlight_labels_json,
                    quality_tags_json = CASE
                        WHEN excluded.quality_tags_json <> '[]' THEN excluded.quality_tags_json
                        ELSE movie_items.quality_tags_json
                    END,
                    parser_version = excluded.parser_version,
                    raw_document_hash = excluded.raw_document_hash,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                (
                    movie_id,
                    movie.source_id,
                    movie.source_item_key,
                    movie.detail_url,
                    movie.listing_title,
                    movie.title,
                    movie.original_title,
                    movie.year,
                    movie.update_date.isoformat() if movie.update_date else None,
                    movie.release_date.isoformat() if movie.release_date else None,
                    movie.duration_minutes,
                    json.dumps(movie.countries, ensure_ascii=False),
                    json.dumps(movie.genres, ensure_ascii=False),
                    json.dumps(movie.languages, ensure_ascii=False),
                    json.dumps(movie.directors, ensure_ascii=False),
                    json.dumps(movie.actors, ensure_ascii=False),
                    movie.imdb_id,
                    movie.douban_rating,
                    movie.douban_rating_text,
                    movie.douban_url,
                    movie.cover_source_url,
                    movie.synopsis,
                    int(movie.recommended),
                    json.dumps(movie.highlight_labels, ensure_ascii=False),
                    json.dumps(movie.quality_tags, ensure_ascii=False),
                    movie.parser_version,
                    movie.raw_document_hash,
                    now_s,
                    now_s,
                    now_s,
                    now_s,
                ),
            )
            for resource in movie.resources:
                resource_id = movie_resource_id_for(movie_id, resource.resource_url)
                existed = self.conn.execute(
                    "SELECT 1 FROM movie_resources WHERE resource_id = ?",
                    (resource_id,),
                ).fetchone()
                self.conn.execute(
                    """
                    INSERT INTO movie_resources(
                        resource_id, movie_id, resource_type, provider,
                        resource_url, info_hash, display_title, extraction_code,
                        quality_tags_json, first_seen_at, last_seen_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(resource_id) DO UPDATE SET
                        resource_type = excluded.resource_type,
                        provider = excluded.provider,
                        info_hash = excluded.info_hash,
                        display_title = excluded.display_title,
                        extraction_code = COALESCE(excluded.extraction_code, movie_resources.extraction_code),
                        quality_tags_json = excluded.quality_tags_json,
                        last_seen_at = excluded.last_seen_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        resource_id,
                        movie_id,
                        resource.resource_type,
                        resource.provider,
                        resource.resource_url,
                        resource.info_hash,
                        resource.display_title,
                        resource.extraction_code,
                        json.dumps(resource.quality_tags, ensure_ascii=False),
                        now_s,
                        now_s,
                        now_s,
                        now_s,
                    ),
                )
                if existed is None:
                    resources_created += 1
                else:
                    resources_updated += 1
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return MovieUpsertStats(
            movie_created=existing is None,
            movie_updated=existing is not None,
            resources_created=resources_created,
            resources_updated=resources_updated,
        )

    def exists(self, *, source_id: str, detail_url: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM movie_items WHERE source_id = ? AND detail_url = ? LIMIT 1",
            (source_id, detail_url),
        ).fetchone()
        return row is not None

    def counts(self, *, source_id: str) -> dict[str, int]:
        movies = self.conn.execute(
            "SELECT COUNT(*) FROM movie_items WHERE source_id = ?",
            (source_id,),
        ).fetchone()[0]
        resources = self.conn.execute(
            """
            SELECT COUNT(*) FROM movie_resources r
            JOIN movie_items m ON m.movie_id = r.movie_id
            WHERE m.source_id = ?
            """,
            (source_id,),
        ).fetchone()[0]
        recommended = self.conn.execute(
            "SELECT COUNT(*) FROM movie_items WHERE source_id = ? AND recommended = 1",
            (source_id,),
        ).fetchone()[0]
        return {
            "movies": int(movies),
            "resources": int(resources),
            "recommended": int(recommended),
        }

    def feed_item(self, *, source_id: str, detail_url: str, rank: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM movie_items WHERE source_id = ? AND detail_url = ?",
            (source_id, detail_url),
        ).fetchone()
        if row is None:
            return None
        resources = self.conn.execute(
            """
            SELECT resource_type, provider, resource_url, info_hash,
                   display_title, extraction_code, quality_tags_json
            FROM movie_resources
            WHERE movie_id = ?
            ORDER BY resource_type, provider, display_title, resource_url
            """,
            (row["movie_id"],),
        ).fetchall()
        return {
            "rank": rank,
            "movie_id": row["movie_id"],
            "source_id": row["source_id"],
            "source_item_key": row["source_item_key"],
            "detail_url": row["detail_url"],
            "listing_title": row["listing_title"],
            "title": row["title"],
            "original_title": row["original_title"],
            "year": row["year"],
            "update_date": row["update_date"],
            "release_date": row["release_date"],
            "duration_minutes": row["duration_minutes"],
            "countries": json.loads(row["countries_json"]),
            "genres": json.loads(row["genres_json"]),
            "languages": json.loads(row["languages_json"]),
            "directors": json.loads(row["directors_json"]),
            "actors": json.loads(row["actors_json"]),
            "imdb_id": row["imdb_id"],
            "douban_rating": row["douban_rating"],
            "douban_rating_text": row["douban_rating_text"],
            "douban_url": row["douban_url"],
            "cover_source_url": row["cover_source_url"],
            "synopsis": row["synopsis"],
            "recommended": bool(row["recommended"]),
            "highlight_labels": json.loads(row["highlight_labels_json"]),
            "quality_tags": json.loads(row["quality_tags_json"]),
            "resources": [
                {
                    "resource_type": resource["resource_type"],
                    "provider": resource["provider"],
                    "url": resource["resource_url"],
                    "info_hash": resource["info_hash"],
                    "display_title": resource["display_title"],
                    "extraction_code": resource["extraction_code"],
                    "quality_tags": json.loads(resource["quality_tags_json"]),
                }
                for resource in resources
            ],
        }
