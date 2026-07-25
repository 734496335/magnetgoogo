"""Core domain models (site-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from magnet.resource_index.domain.enums import (
    AliasType,
    ContentType,
    DocumentType,
    MediaStatus,
    MediaType,
    PersonRole,
)


@dataclass(frozen=True)
class ContentItem:
    content_id: str
    content_type: ContentType
    content_code: str
    raw_content_code: str
    title: str
    original_title: str | None
    release_date: date | None
    duration_minutes: int | None
    maker_name: str | None
    publisher_name: str | None
    label_name: str | None
    series_name: str | None
    cover_source_url: str | None
    detail_url: str
    adult: bool
    source_id: str
    source_item_key: str
    parser_version: str


@dataclass(frozen=True)
class ContentAlias:
    alias: str
    normalized_alias: str
    alias_type: AliasType


@dataclass(frozen=True)
class PersonRef:
    person_id: str
    display_name: str
    role: PersonRole
    source_profile_url: str | None
    source_external_key: str | None
    sort_order: int


@dataclass(frozen=True)
class TagRef:
    tag_id: str
    display_name: str
    source_url: str | None
    source_external_key: str | None


@dataclass(frozen=True)
class MediaAssetRef:
    media_id: str
    media_type: MediaType
    source_url: str
    stored_url: str | None
    content_hash: str | None
    width: int | None
    height: int | None
    adult: bool
    status: MediaStatus


@dataclass(frozen=True)
class ResourceRelease:
    resource_id: str
    content_id: str
    info_hash: str
    magnet_uri: str
    display_title: str
    size_bytes: int | None
    size_display: str | None
    published_at: date | None
    has_subtitle: bool | None
    has_hd: bool | None
    quality_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResourceObservation:
    observation_id: str
    resource_id: str
    content_id: str
    source_id: str
    source_item_key: str
    detail_url: str
    observed_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    parser_version: str
    raw_document_hash: str | None


@dataclass(frozen=True)
class RawDocumentEnvelope:
    document_id: str
    source_id: str
    document_type: DocumentType
    source_url: str
    captured_at: datetime
    status_code: int | None
    content_type: str
    encoding: str
    sha256: str
    body: str
    fixture_name: str | None
    sanitized: bool


@dataclass(frozen=True)
class ContentCandidate:
    raw_title: str | None
    raw_content_code: str | None
    content_code: str | None
    detail_url: str
    cover_source_url: str | None
    list_position: int
    source_item_key: str


@dataclass(frozen=True)
class ParseWarning:
    error_code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParseProvenance:
    source_id: str
    source_item_key: str
    detail_url: str
    parser_version: str
    document_sha256: str | None
    resource_document_sha256: str | None = None
    internal: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedContentBundle:
    content: ContentItem
    aliases: tuple[ContentAlias, ...]
    people: tuple[PersonRef, ...]
    tags: tuple[TagRef, ...]
    media: tuple[MediaAssetRef, ...]
    resources: tuple[ResourceRelease, ...]
    warnings: tuple[ParseWarning, ...]
    provenance: ParseProvenance


@dataclass(frozen=True)
class ResourceRequestDescriptor:
    """Describes how to fetch a resource table; never executes network I/O."""

    method: str
    url_template: str
    headers: dict[str, str]
    query: dict[str, str]
    referer: str | None
    notes: str | None = None
