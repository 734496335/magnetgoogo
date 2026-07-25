"""Repository protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from magnet.resource_index.domain.models import ParsedContentBundle


@dataclass
class UpsertStats:
    content_created: bool = False
    content_updated: bool = False
    resources_created: int = 0
    resources_updated: int = 0
    warnings: int = 0


@dataclass
class TableCounts:
    contents: int
    people: int
    tags: int
    resources: int
    observations: int
    content_people: int
    content_tags: int
    aliases: int
    contents_without_resources: int


class ResourceRepository(Protocol):
    def init_schema(self) -> str: ...

    def upsert_bundle(
        self,
        bundle: ParsedContentBundle,
        *,
        now: datetime,
    ) -> UpsertStats: ...

    def get_content_by_code(self, content_code: str) -> dict[str, Any] | None: ...

    def list_resources_for_content(self, content_code: str) -> list[dict[str, Any]]: ...

    def search_contents(self, query: str, *, limit: int = 50) -> list[dict[str, Any]]: ...

    def counts(self) -> TableCounts: ...

    def start_ingest_run(
        self,
        run_id: str,
        source_id: str,
        mode: str,
        started_at: datetime,
    ) -> None: ...

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
    ) -> None: ...

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
    ) -> None: ...

    def last_successful_run(self) -> dict[str, Any] | None: ...

    def warning_counts(self) -> dict[str, int]: ...

    def export_adult_rows(self, *, limit: int, include_review: bool) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...
