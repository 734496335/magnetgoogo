"""Structured error taxonomy for resource_index."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Canonical error codes (plan §12)
FIXTURE_MANIFEST_INVALID = "FIXTURE_MANIFEST_INVALID"
FIXTURE_HASH_MISMATCH = "FIXTURE_HASH_MISMATCH"
DOCUMENT_ENCODING_ERROR = "DOCUMENT_ENCODING_ERROR"
AGE_GATE_PAGE = "AGE_GATE_PAGE"
ACCESS_CHALLENGE = "ACCESS_CHALLENGE"
LISTING_DOM_DRIFT = "LISTING_DOM_DRIFT"
LISTING_EMPTY = "LISTING_EMPTY"
DETAIL_DOM_DRIFT = "DETAIL_DOM_DRIFT"
CONTENT_CODE_MISSING = "CONTENT_CODE_MISSING"
CONTENT_CODE_INVALID = "CONTENT_CODE_INVALID"
TITLE_MISSING = "TITLE_MISSING"
DATE_INVALID = "DATE_INVALID"
DURATION_INVALID = "DURATION_INVALID"
RESOURCE_DESCRIPTOR_MISSING = "RESOURCE_DESCRIPTOR_MISSING"
RESOURCE_TABLE_DOM_DRIFT = "RESOURCE_TABLE_DOM_DRIFT"
RESOURCE_TABLE_EMPTY = "RESOURCE_TABLE_EMPTY"
MAGNET_INVALID = "MAGNET_INVALID"
INFO_HASH_INVALID = "INFO_HASH_INVALID"
SIZE_INVALID = "SIZE_INVALID"
RESOURCE_CONTENT_CONFLICT = "RESOURCE_CONTENT_CONFLICT"
DATABASE_CONSTRAINT_ERROR = "DATABASE_CONSTRAINT_ERROR"
TRANSACTION_ROLLBACK = "TRANSACTION_ROLLBACK"
LIVE_FETCH_DISABLED = "LIVE_FETCH_DISABLED"
LIVE_POLICY_NOT_ACKNOWLEDGED = "LIVE_POLICY_NOT_ACKNOWLEDGED"
LIVE_RATE_LIMITED = "LIVE_RATE_LIMITED"
VALIDATION_ERROR = "VALIDATION_ERROR"
CONFIG_ERROR = "CONFIG_ERROR"
NOT_FOUND = "NOT_FOUND"
CLI_ERROR = "CLI_ERROR"


@dataclass
class ResourceIndexError(Exception):
    """Base structured error for the resource_index package."""

    error_code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.error_code}: {self.message}"


class FixtureError(ResourceIndexError):
    pass


class ParseError(ResourceIndexError):
    pass


class ValidationError(ResourceIndexError):
    pass


class StorageError(ResourceIndexError):
    pass


class LivePolicyError(ResourceIndexError):
    pass


class ConflictError(ResourceIndexError):
    pass
