"""Backend-neutral publisher contract for immutable media artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class PublishedObject:
    key: str
    size: int
    sha256: str | None
    etag: str | None = None
    metadata: Mapping[str, str] | None = None


@dataclass(frozen=True)
class UploadRequest:
    key: str
    source_path: Path
    sha256: str
    size: int
    content_type: str
    cache_control: str
    release_id: str
    object_kind: str
    immutable: bool = True


@dataclass(frozen=True)
class UploadOutcome:
    object: PublishedObject
    uploaded: bool
    reused: bool
    deep_verified: bool


class PublisherBackend(ABC):
    """Minimal interface required by the media publish orchestrator."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def destination(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def head(self, key: str) -> PublishedObject | None:
        raise NotImplementedError

    @abstractmethod
    def upload(self, request: UploadRequest, *, deep_verify: bool = True) -> UploadOutcome:
        raise NotImplementedError

    @abstractmethod
    def verify(self, request: UploadRequest, *, deep: bool = True) -> PublishedObject:
        raise NotImplementedError

    def promote_current(self, *_args: object, **_kwargs: object) -> None:
        """M2 intentionally forbids production current-pointer promotion."""

        raise NotImplementedError("current.json promotion is not available in the M2 publisher")
