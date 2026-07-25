"""Acquisition-layer models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FixtureDocumentRef:
    name: str
    document_type: str
    path: str
    sha256: str
    expected: str | None
    source_url: str
    content_code: str | None = None
    links_to: tuple[str, ...] = ()


@dataclass(frozen=True)
class FixtureManifest:
    fixture_schema: str
    source_id: str
    captured_at: datetime
    sanitized: bool
    documents: tuple[FixtureDocumentRef, ...]
    root_dir: str
