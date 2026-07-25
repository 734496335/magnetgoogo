"""Merge detail + resource table into a single bundle."""

from __future__ import annotations

from magnet.resource_index.domain.models import (
    ParsedContentBundle,
    ParseProvenance,
    ParseWarning,
    ResourceRelease,
)
from magnet.resource_index.pipeline.deduplicate import dedupe_resources_by_hash


def attach_resources(
    detail_bundle: ParsedContentBundle,
    resources: list[ResourceRelease],
    extra_warnings: list[ParseWarning] | None = None,
    *,
    resource_document_sha256: str | None = None,
) -> ParsedContentBundle:
    merged = dedupe_resources_by_hash(list(resources))
    # Force content_id consistency
    fixed = [
        ResourceRelease(
            resource_id=r.resource_id,
            content_id=detail_bundle.content.content_id,
            info_hash=r.info_hash,
            magnet_uri=r.magnet_uri,
            display_title=r.display_title,
            size_bytes=r.size_bytes,
            size_display=r.size_display,
            published_at=r.published_at,
            has_subtitle=r.has_subtitle,
            has_hd=r.has_hd,
            quality_tags=r.quality_tags,
        )
        for r in merged
    ]
    warnings = list(detail_bundle.warnings)
    if extra_warnings:
        warnings.extend(extra_warnings)
    prov = ParseProvenance(
        source_id=detail_bundle.provenance.source_id,
        source_item_key=detail_bundle.provenance.source_item_key,
        detail_url=detail_bundle.provenance.detail_url,
        parser_version=detail_bundle.provenance.parser_version,
        document_sha256=detail_bundle.provenance.document_sha256,
        resource_document_sha256=resource_document_sha256,
        internal=dict(detail_bundle.provenance.internal),
    )
    return ParsedContentBundle(
        content=detail_bundle.content,
        aliases=detail_bundle.aliases,
        people=detail_bundle.people,
        tags=detail_bundle.tags,
        media=detail_bundle.media,
        resources=tuple(fixed),
        warnings=tuple(warnings),
        provenance=prov,
    )
