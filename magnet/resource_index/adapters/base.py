"""Source adapter protocol."""

from __future__ import annotations

from typing import Protocol

from magnet.resource_index.domain.models import (
    ContentCandidate,
    ParsedContentBundle,
    RawDocumentEnvelope,
    ResourceRelease,
    ResourceRequestDescriptor,
)


class ResourceSourceAdapter(Protocol):
    source_id: str
    parser_version: str

    def parse_listing(self, document: RawDocumentEnvelope) -> list[ContentCandidate]: ...

    def parse_detail(self, document: RawDocumentEnvelope) -> ParsedContentBundle: ...

    def parse_resource_table(
        self,
        document: RawDocumentEnvelope,
        *,
        content_id: str,
    ) -> list[ResourceRelease]: ...

    def derive_resource_request(
        self,
        detail_document: RawDocumentEnvelope,
    ) -> ResourceRequestDescriptor | None: ...
