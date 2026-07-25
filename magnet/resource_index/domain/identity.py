"""Deterministic identity builders."""

from __future__ import annotations

import hashlib
import re

from magnet.resource_index.domain.enums import ContentType, MediaType, PersonRole
from magnet.resource_index.errors import CONTENT_CODE_INVALID, ValidationError
from magnet.resource_index.normalize.content_code import normalize_content_code
from magnet.resource_index.normalize.text import normalize_whitespace


def content_id_for(content_type: ContentType, content_code: str) -> str:
    code = normalize_content_code(content_code)
    if not code:
        raise ValidationError(
            CONTENT_CODE_INVALID,
            "content_code required for content_id",
            {"content_code": content_code},
        )
    return f"{content_type.value}:{code}"


def person_id_for(
    *,
    slug: str | None,
    display_name: str,
    source_prefix: str,
) -> str:
    """source_prefix must be supplied by the adapter (never hardcode a site in domain)."""
    if slug:
        clean = slug.strip().strip("/")
        if clean:
            return f"{source_prefix}:person:{clean}"
    name = normalize_whitespace(display_name).casefold()
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:20]
    return f"name:{digest}"


def tag_id_for(
    *,
    external_key: str | None,
    display_name: str,
    source_prefix: str,
) -> str:
    """source_prefix must be supplied by the adapter (never hardcode a site in domain)."""
    if external_key:
        key = external_key.strip().strip("/")
        if key:
            return f"{source_prefix}:tag:{key}"
    name = normalize_whitespace(display_name).casefold()
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:20]
    return f"tag:{digest}"


def media_id_for(content_id: str, media_type: MediaType, source_url: str) -> str:
    digest = hashlib.sha256(f"{content_id}|{media_type.value}|{source_url}".encode("utf-8")).hexdigest()[:24]
    return f"media:{digest}"


def resource_id_for(info_hash: str) -> str:
    h = info_hash.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", h):
        raise ValidationError(
            "INFO_HASH_INVALID",
            "info_hash must be 40 lowercase hex for resource_id",
            {"info_hash": info_hash},
        )
    return f"btih:{h}"


def observation_id_for(resource_id: str, source_id: str, source_item_key: str) -> str:
    digest = hashlib.sha256(
        f"{resource_id}|{source_id}|{source_item_key}".encode("utf-8")
    ).hexdigest()[:24]
    return f"obs:{digest}"


def document_id_for(source_id: str, source_url: str, body_sha256: str) -> str:
    digest = hashlib.sha256(
        f"{source_id}|{source_url}|{body_sha256}".encode("utf-8")
    ).hexdigest()[:24]
    return f"doc:{digest}"


def person_role_or_default(role: str | None) -> PersonRole:
    if role == PersonRole.DIRECTOR.value or role == "director":
        return PersonRole.DIRECTOR
    return PersonRole.ACTOR
