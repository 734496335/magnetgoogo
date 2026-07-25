"""Domain enumerations."""

from __future__ import annotations

from enum import Enum


class ContentType(str, Enum):
    ADULT_VIDEO = "adult_video"


class PersonRole(str, Enum):
    ACTOR = "actor"
    DIRECTOR = "director"


class MediaType(str, Enum):
    COVER = "cover"
    SAMPLE = "sample"


class MediaStatus(str, Enum):
    REMOTE_REFERENCE_ONLY = "remote_reference_only"


class DocumentType(str, Enum):
    LISTING = "listing"
    DETAIL = "detail"
    RESOURCE_TABLE = "resource_table"
    AGE_GATE = "age_gate"
    OTHER = "other"


class AliasType(str, Enum):
    PREVIOUS_TITLE = "previous_title"
    RAW_CODE = "raw_code"
    ALTERNATE_CODE = "alternate_code"


class IngestMode(str, Enum):
    FIXTURE = "fixture"
    MANUAL_CAPTURE = "manual_capture"
    LIVE_ONE_SHOT = "live_one_shot"


class IngestRunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class RiskStatus(str, Enum):
    ALLOWED = "allowed"
    BLOCKED_AGE_AMBIGUITY = "blocked_age_ambiguity"
    BLOCKED_POLICY = "blocked_policy"
    BLOCKED_TAKEDOWN = "blocked_takedown"
    BLOCKED_MALWARE = "blocked_malware"
    MANUAL_REVIEW = "manual_review"
