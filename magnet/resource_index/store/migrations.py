"""SQLite migration runner."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from magnet.resource_index.config import SCHEMA_VERSION
from magnet.resource_index.errors import DATABASE_CONSTRAINT_ERROR, StorageError

_DEFAULT_SQL_DIR = Path(__file__).resolve().parent / "sql"
SQL_DIR = _DEFAULT_SQL_DIR

# An early development build used version 0007 for optional IMDb rating columns
# before the committed 0007 media-brand migration was frozen. This exact hash is
# accepted only when the database structure proves that legacy variant was
# applied completely and the committed 0007 structure is still absent.
_LEGACY_0007_IMDB_CHECKSUM = "9316572ec726f5910e4ad3bae98aebd40d9c5e5dc1b72bb4d0c63bb2013c8fa9"
_LEGACY_0007_ARCHIVE_VERSION = "0007_legacy_imdb_rating_9316572e"
_LEGACY_0007_COLUMNS = {"imdb_rating", "imdb_rating_text"}
_MEDIA_0007_MOVIE_COLUMNS = {
    "content_kind",
    "series_title",
    "season_number",
    "episode_number",
    "episode_label",
    "update_status",
    "brand_id",
    "endpoint_origin",
}
_MEDIA_0007_INDEXES = {
    "idx_movie_items_kind_update",
    "idx_movie_items_brand",
    "idx_movie_items_series",
    "idx_latest_crawl_items_source_key",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def migration_files() -> list[Path]:
    files = sorted(SQL_DIR.glob("*.sql"))
    if not files:
        raise StorageError(
            DATABASE_CONSTRAINT_ERROR,
            "no migration SQL files found",
            {"sql_dir": str(SQL_DIR)},
        )
    versions = [path.stem.split("_", 1)[0] for path in files]
    if len(versions) != len(set(versions)):
        duplicates = sorted({version for version in versions if versions.count(version) > 1})
        raise StorageError(
            DATABASE_CONSTRAINT_ERROR,
            "duplicate migration versions",
            {"versions": duplicates},
        )
    try:
        numeric_versions = [int(version) for version in versions]
    except ValueError as exc:
        raise StorageError(
            DATABASE_CONSTRAINT_ERROR,
            "migration versions must be numeric",
            {"actual": versions},
        ) from exc
    expected = [f"{number:04d}" for number in range(1, max(numeric_versions) + 1)]
    production_dir = SQL_DIR.resolve() == _DEFAULT_SQL_DIR.resolve()
    if versions != expected or (production_dir and versions[-1] != SCHEMA_VERSION):
        production_expected = (
            [f"{number:04d}" for number in range(1, int(SCHEMA_VERSION) + 1)]
            if production_dir
            else expected
        )
        raise StorageError(
            DATABASE_CONSTRAINT_ERROR,
            "migration sequence is incomplete or out of order",
            {"expected": production_expected, "actual": versions},
        )
    return files


def _canonical_sql_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def file_checksum(path: Path) -> str:
    return hashlib.sha256(_canonical_sql_bytes(path)).hexdigest()


def raw_file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compatible_file_checksums(path: Path) -> set[str]:
    canonical = _canonical_sql_bytes(path)
    crlf = canonical.replace(b"\n", b"\r\n")
    return {
        hashlib.sha256(canonical).hexdigest(),
        hashlib.sha256(crlf).hexdigest(),
        raw_file_checksum(path),
    }


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_xinfo({table})")}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }


def _normalize_legacy_0007_collision(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = '0007'"
    ).fetchone()
    if row is None or str(row[0]) != _LEGACY_0007_IMDB_CHECKSUM:
        return False
    movie_columns = _column_names(conn, "movie_items")
    latest_columns = _column_names(conn, "latest_crawl_items")
    indexes = _index_names(conn)
    legacy_complete = _LEGACY_0007_COLUMNS <= movie_columns
    media_absent = (
        not (_MEDIA_0007_MOVIE_COLUMNS & movie_columns)
        and "source_item_key" not in latest_columns
        and not (_MEDIA_0007_INDEXES & indexes)
    )
    if not legacy_complete or not media_absent:
        raise StorageError(
            DATABASE_CONSTRAINT_ERROR,
            "legacy migration 0007 structure does not match its approved fingerprint",
            {
                "version": "0007",
                "legacy_columns_present": sorted(_LEGACY_0007_COLUMNS & movie_columns),
                "media_columns_present": sorted(_MEDIA_0007_MOVIE_COLUMNS & movie_columns),
                "media_indexes_present": sorted(_MEDIA_0007_INDEXES & indexes),
            },
        )
    existing = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (_LEGACY_0007_ARCHIVE_VERSION,),
    ).fetchone()
    if existing is not None:
        raise StorageError(
            DATABASE_CONSTRAINT_ERROR,
            "legacy migration archive marker already exists",
            {"version": _LEGACY_0007_ARCHIVE_VERSION},
        )
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE schema_migrations SET version = ? WHERE version = '0007'",
            (_LEGACY_0007_ARCHIVE_VERSION,),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return True


def apply_migrations(conn: sqlite3.Connection) -> str:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            checksum TEXT NOT NULL
        )
        """
    )
    _normalize_legacy_0007_collision(conn)
    applied = {
        row[0]: row[1]
        for row in conn.execute("SELECT version, checksum FROM schema_migrations")
    }
    latest = SCHEMA_VERSION
    for path in migration_files():
        version = path.stem.split("_", 1)[0]
        checksum = file_checksum(path)
        compatible_checksums = compatible_file_checksums(path)
        if version in applied:
            stored = applied[version]
            if stored not in compatible_checksums:
                raise StorageError(
                    DATABASE_CONSTRAINT_ERROR,
                    "migration checksum mismatch",
                    {"version": version},
                )
            if stored != checksum:
                conn.execute(
                    "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
                    (checksum, version),
                )
                conn.commit()
            latest = version
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
            (version, _utc_now(), checksum),
        )
        latest = version
    conn.commit()
    return latest
