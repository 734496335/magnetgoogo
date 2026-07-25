from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from magnet.resource_index.pipeline.ingest import ingest_fixture
from magnet.resource_index.store import migrations
from magnet.resource_index.store.migrations import file_checksum
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository


def test_migration_accepts_legacy_crlf_checksum(monkeypatch, tmp_path: Path):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    sql_path = sql_dir / "0001_test.sql"
    sql_path.write_bytes(b"CREATE TABLE demo(id INTEGER);\n")
    legacy_crlf = hashlib.sha256(b"CREATE TABLE demo(id INTEGER);\r\n").hexdigest()
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL, checksum TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES ('0001', 'x', ?)",
        (legacy_crlf,),
    )
    monkeypatch.setattr(migrations, "SQL_DIR", sql_dir)
    assert migrations.apply_migrations(conn) == "0001"
    stored = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = '0001'"
    ).fetchone()[0]
    assert stored == file_checksum(sql_path)
    conn.close()


def test_fixture_hash_failure_finishes_run(tmp_path: Path):
    root = tmp_path / "fixtures"
    root.mkdir()
    (root / "detail.html").write_text("<html>bad hash</html>", encoding="utf-8")
    manifest = {
        "fixture_schema": "1.0",
        "source_id": "javbus",
        "captured_at": "2026-07-25T00:00:00Z",
        "sanitized": True,
        "documents": [
            {
                "name": "bad",
                "type": "detail",
                "path": "detail.html",
                "sha256": "0" * 64,
                "source_url": "https://fixtures.invalid/bad",
            }
        ],
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    repo = SqliteResourceRepository(tmp_path / "fixture-failure.db")
    repo.init_schema()
    result = ingest_fixture(
        manifest_path=manifest_path,
        repo=repo,
        source_id="javbus",
        run_id="fixture-failure",
    )
    row = repo.conn.execute(
        "SELECT status, finished_at, errors FROM ingest_runs WHERE run_id = ?",
        ("fixture-failure",),
    ).fetchone()
    assert result.status == "failed"
    assert row["status"] == "failed"
    assert row["finished_at"] is not None
    assert row["errors"] == 1
    repo.close()
