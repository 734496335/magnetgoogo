"""JavBus resource source adapter."""

from __future__ import annotations

from magnet.resource_index.adapters.javbus import detail_parser, listing_parser, resource_parser
from magnet.resource_index.adapters.javbus.selectors import PARSER_VERSION, SOURCE_ID
from magnet.resource_index.domain.models import (
    ContentCandidate,
    ParsedContentBundle,
    RawDocumentEnvelope,
    ResourceRelease,
    ResourceRequestDescriptor,
)


class JavBusAdapter:
    source_id = SOURCE_ID
    parser_version = PARSER_VERSION

    def parse_listing(self, document: RawDocumentEnvelope) -> list[ContentCandidate]:
        return listing_parser.parse_listing(document)

    def parse_detail(self, document: RawDocumentEnvelope) -> ParsedContentBundle:
        return detail_parser.parse_detail(document)

    def parse_resource_table(
        self,
        document: RawDocumentEnvelope,
        *,
        content_id: str,
        fallback_title: str | None = None,
    ) -> list[ResourceRelease]:
        releases, _warnings = resource_parser.parse_resource_table(
            document,
            content_id=content_id,
            fallback_title=fallback_title,
        )
        return releases

    def parse_resource_table_with_warnings(
        self,
        document: RawDocumentEnvelope,
        *,
        content_id: str,
        fallback_title: str | None = None,
    ) -> tuple[list[ResourceRelease], list]:
        return resource_parser.parse_resource_table(
            document,
            content_id=content_id,
            fallback_title=fallback_title,
        )

    def derive_resource_request(
        self,
        detail_document: RawDocumentEnvelope,
    ) -> ResourceRequestDescriptor | None:
        return detail_parser.derive_resource_request(detail_document)
