"""SQLite migration runner."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from magnet.resource_index.config import SCHEMA_VERSION
from magnet.resource_index.errors import DATABASE_CONSTRAINT_ERROR, StorageError

SQL_DIR = Path(__file__).resolve().parent / "sql"


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
    return files


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    applied = {
        row[0]: row[1]
        for row in conn.execute("SELECT version, checksum FROM schema_migrations")
    }
    latest = SCHEMA_VERSION
    for path in migration_files():
        version = path.stem.split("_", 1)[0]
        checksum = file_checksum(path)
        if version in applied:
            if applied[version] != checksum:
                raise StorageError(
                    DATABASE_CONSTRAINT_ERROR,
                    "migration checksum mismatch",
                    {"version": version},
                )
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
