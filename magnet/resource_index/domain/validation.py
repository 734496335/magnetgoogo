"""Domain-level validation for core entities."""

from __future__ import annotations

from magnet.resource_index.domain.enums import ContentType
from magnet.resource_index.domain.models import ContentItem, ParsedContentBundle, ResourceRelease
from magnet.resource_index.errors import (
    CONTENT_CODE_INVALID,
    CONTENT_CODE_MISSING,
    TITLE_MISSING,
    ValidationError,
)
from magnet.resource_index.normalize.content_code import normalize_content_code


def validate_content_item(item: ContentItem) -> None:
    if item.content_type != ContentType.ADULT_VIDEO:
        raise ValidationError(
            "VALIDATION_ERROR",
            "phase-1 only supports adult_video",
            {"content_type": item.content_type.value},
        )
    if not item.adult:
        raise ValidationError(
            "VALIDATION_ERROR",
            "adult content must have adult=true",
            {"content_id": item.content_id},
        )
    if not item.raw_content_code or not item.raw_content_code.strip():
        raise ValidationError(CONTENT_CODE_MISSING, "raw_content_code missing", {})
    code = normalize_content_code(item.content_code)
    if not code:
        raise ValidationError(
            CONTENT_CODE_INVALID,
            "content_code invalid after normalize",
            {"content_code": item.content_code},
        )
    if code != item.content_code:
        raise ValidationError(
            CONTENT_CODE_INVALID,
            "content_code must already be normalized uppercase",
            {"content_code": item.content_code, "expected": code},
        )
    if not item.title or not item.title.strip():
        raise ValidationError(TITLE_MISSING, "title is required", {})
    if item.title.strip().lower() == "unknown title":
        raise ValidationError(TITLE_MISSING, "Unknown Title is not allowed", {})
    if not item.detail_url:
        raise ValidationError("VALIDATION_ERROR", "detail_url required", {})
    if not item.source_id or not item.source_item_key:
        raise ValidationError("VALIDATION_ERROR", "source identity required", {})
    if not item.parser_version:
        raise ValidationError("VALIDATION_ERROR", "parser_version required", {})


def validate_resource_release(resource: ResourceRelease) -> None:
    if not resource.resource_id.startswith("btih:"):
        raise ValidationError(
            "INFO_HASH_INVALID",
            "resource_id must be btih:{hash}",
            {"resource_id": resource.resource_id},
        )
    if resource.info_hash != resource.resource_id.removeprefix("btih:"):
        raise ValidationError(
            "INFO_HASH_INVALID",
            "resource_id/info_hash mismatch",
            {
                "resource_id": resource.resource_id,
                "info_hash": resource.info_hash,
            },
        )
    if not resource.magnet_uri.startswith("magnet:?"):
        raise ValidationError(
            "MAGNET_INVALID",
            "magnet_uri must start with magnet:?",
            {},
        )
    if not resource.display_title.strip():
        raise ValidationError("VALIDATION_ERROR", "display_title required", {})


def validate_bundle(bundle: ParsedContentBundle) -> None:
    validate_content_item(bundle.content)
    provenance = bundle.provenance
    if (
        provenance.source_id != bundle.content.source_id
        or provenance.source_item_key != bundle.content.source_item_key
        or provenance.detail_url != bundle.content.detail_url
        or provenance.parser_version != bundle.content.parser_version
    ):
        raise ValidationError(
            "VALIDATION_ERROR",
            "content and provenance source identity must match",
            {
                "content_source_id": bundle.content.source_id,
                "provenance_source_id": provenance.source_id,
            },
        )
    for resource in bundle.resources:
        if resource.content_id != bundle.content.content_id:
            raise ValidationError(
                "VALIDATION_ERROR",
                "resource content_id mismatch",
                {
                    "content_id": bundle.content.content_id,
                    "resource_content_id": resource.content_id,
                },
            )
        validate_resource_release(resource)
