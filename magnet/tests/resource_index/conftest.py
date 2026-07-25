"""Shared fixtures for resource_index tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "resource_index" / "javbus"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"

FIXED_NOW = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def fixture_root() -> Path:
    return FIXTURE_ROOT


@pytest.fixture
def manifest_path() -> Path:
    return MANIFEST_PATH


@pytest.fixture
def fixed_now() -> datetime:
    return FIXED_NOW


@pytest.fixture
def repo(tmp_path: Path) -> SqliteResourceRepository:
    db = tmp_path / "test.resource.db"
    r = SqliteResourceRepository(db)
    r.init_schema()
    yield r
    r.close()
