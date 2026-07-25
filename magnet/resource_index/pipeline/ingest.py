"""Fixture ingest pipeline."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from magnet.resource_index.acquisition.fixture_reader import iter_envelopes, load_manifest
from magnet.resource_index.adapters.registry import get_adapter
from magnet.resource_index.domain.enums import DocumentType, IngestMode, IngestRunStatus
from magnet.resource_index.domain.models import RawDocumentEnvelope
from magnet.resource_index.domain.validation import validate_bundle
from magnet.resource_index.errors import ConflictError, ResourceIndexError
from magnet.resource_index.pipeline.reconcile import attach_resources
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

Clock = Callable[[], datetime]


def default_clock() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IngestResult:
    run_id: str
    status: str
    documents_seen: int = 0
    contents_created: int = 0
    contents_updated: int = 0
    resources_created: int = 0
    resources_updated: int = 0
    warnings: int = 0
    errors: int = 0
    error_summary: dict[str, Any] = field(default_factory=dict)


def _get_adapter(source_id: str):
    return get_adapter(source_id)


def ingest_fixture(
    *,
    manifest_path: str | Path,
    repo: SqliteResourceRepository,
    source_id: str = "javbus",
    clock: Clock = default_clock,
    run_id: str | None = None,
) -> IngestResult:
    adapter = _get_adapter(source_id)
    manifest = load_manifest(manifest_path)
    if manifest.source_id != source_id:
        raise ResourceIndexError(
            "FIXTURE_MANIFEST_INVALID",
            "manifest source_id mismatch",
            {"expected": source_id, "actual": manifest.source_id},
        )

    rid = run_id or uuid.uuid4().hex
    started = clock()
    repo.start_ingest_run(rid, source_id, IngestMode.FIXTURE.value, started)

    result = IngestResult(run_id=rid, status=IngestRunStatus.RUNNING.value)
    error_codes: dict[str, int] = {}

    # Index documents by name for linking detail <-> resource_table
    pairs = iter_envelopes(manifest)
    by_name: dict[str, RawDocumentEnvelope] = {doc.name: env for doc, env in pairs}
    doc_meta = {doc.name: doc for doc, _ in pairs}

    detail_docs = [doc for doc, _ in pairs if doc.document_type == DocumentType.DETAIL.value]
    listing_docs = [doc for doc, _ in pairs if doc.document_type == DocumentType.LISTING.value]
    # age_gate / drift docs are not ingested as content but counted
    special_docs = [
        doc
        for doc, _ in pairs
        if doc.document_type
        in {DocumentType.AGE_GATE.value, DocumentType.OTHER.value, DocumentType.LISTING.value}
    ]

    result.documents_seen = len(pairs)

    # Optional: parse listings for observability only (candidates not auto-followed in fixture mode)
    for doc in listing_docs:
        env = by_name[doc.name]
        try:
            adapter.parse_listing(env)
            repo.add_ingest_event(
                rid,
                occurred_at=clock(),
                stage="listing",
                severity="info",
                message=f"listing parsed: {doc.name}",
                source_item_key=doc.name,
            )
        except ResourceIndexError as exc:
            repo.add_ingest_event(
                rid,
                occurred_at=clock(),
                stage="listing",
                severity="warning",
                message=exc.message,
                source_item_key=doc.name,
                error_code=exc.error_code,
                context=exc.context,
            )
            result.warnings += 1
            error_codes[exc.error_code] = error_codes.get(exc.error_code, 0) + 1

    for doc in detail_docs:
        env = by_name[doc.name]
        try:
            bundle = adapter.parse_detail(env)
            # Attach linked resource tables
            resources = []
            res_warnings = []
            res_hash = None
            for link_name in doc.links_to:
                if link_name not in by_name:
                    continue
                res_env = by_name[link_name]
                res_hash = res_env.sha256
                rels, warns = adapter.parse_resource_table_with_warnings(
                    res_env,
                    content_id=bundle.content.content_id,
                    fallback_title=bundle.content.title,
                )
                resources.extend(rels)
                res_warnings.extend(warns)
            # Also match by content_code field on resource docs
            if not resources and doc.content_code:
                for rdoc in doc_meta.values():
                    if (
                        rdoc.document_type == DocumentType.RESOURCE_TABLE.value
                        and (rdoc.content_code or "").upper() == doc.content_code.upper()
                    ):
                        res_env = by_name[rdoc.name]
                        res_hash = res_env.sha256
                        rels, warns = adapter.parse_resource_table_with_warnings(
                            res_env,
                            content_id=bundle.content.content_id,
                            fallback_title=bundle.content.title,
                        )
                        resources.extend(rels)
                        res_warnings.extend(warns)

            full = attach_resources(
                bundle,
                resources,
                res_warnings,
                resource_document_sha256=res_hash,
            )
            validate_bundle(full)
            stats = repo.upsert_bundle(full, now=clock())
            if stats.content_created:
                result.contents_created += 1
            if stats.content_updated:
                result.contents_updated += 1
            result.resources_created += stats.resources_created
            result.resources_updated += stats.resources_updated
            result.warnings += stats.warnings
            for w in full.warnings:
                error_codes[w.error_code] = error_codes.get(w.error_code, 0) + 1
            repo.add_ingest_event(
                rid,
                occurred_at=clock(),
                stage="detail",
                severity="info",
                message=f"ingested {full.content.content_code}",
                source_item_key=full.content.source_item_key,
            )
        except ConflictError as exc:
            result.errors += 1
            error_codes[exc.error_code] = error_codes.get(exc.error_code, 0) + 1
            repo.add_ingest_event(
                rid,
                occurred_at=clock(),
                stage="upsert",
                severity="error",
                message=exc.message,
                source_item_key=doc.name,
                error_code=exc.error_code,
                context=exc.context,
            )
        except ResourceIndexError as exc:
            result.errors += 1
            error_codes[exc.error_code] = error_codes.get(exc.error_code, 0) + 1
            repo.add_ingest_event(
                rid,
                occurred_at=clock(),
                stage="detail",
                severity="error",
                message=exc.message,
                source_item_key=doc.name,
                error_code=exc.error_code,
                context=exc.context,
            )
        except Exception as exc:  # noqa: BLE001 - record unexpected
            result.errors += 1
            error_codes["UNEXPECTED"] = error_codes.get("UNEXPECTED", 0) + 1
            repo.add_ingest_event(
                rid,
                occurred_at=clock(),
                stage="detail",
                severity="error",
                message=str(exc),
                source_item_key=doc.name,
                error_code="UNEXPECTED",
            )

    # Touch special docs count already in documents_seen
    _ = special_docs

    if result.errors and (result.contents_created or result.contents_updated):
        status = IngestRunStatus.PARTIAL.value
    elif result.errors:
        status = IngestRunStatus.FAILED.value
    else:
        status = IngestRunStatus.SUCCESS.value

    result.status = status
    result.error_summary = error_codes
    repo.finish_ingest_run(
        rid,
        status=status,
        finished_at=clock(),
        documents_seen=result.documents_seen,
        contents_created=result.contents_created,
        contents_updated=result.contents_updated,
        resources_created=result.resources_created,
        resources_updated=result.resources_updated,
        warnings=result.warnings,
        errors=result.errors,
        error_summary=error_codes,
    )
    return result
