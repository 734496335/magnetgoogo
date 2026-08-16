"""Tier base interface — every Tier (0/1/2/3) implements the same shape.

Design notes:
- Tiers are stateless: they receive `source` (sources.json rule) + `query` and
  return a list of SearchResult. Any session/cookie/state lives inside the Tier
  instance via its constructor args, not in the call signature.
- A Tier MAY raise `TierError(reason)` to signal "I cannot handle this", which
  triggers orchestrator fallback to the next Tier.
- A Tier MUST NOT raise generic exceptions on transient failures — wrap them in
  TierError so the orchestrator can decide whether to retry/fall back.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any


class TierKind(str, Enum):
    HTTP = "tier0_http"
    CLOAK = "tier1_cloak"
    HANDLER = "tier2_handler"
    USERASSIST = "tier3_userassist"


@dataclass
class SearchResult:
    """Standard output across all Tiers."""

    title: str
    magnet: str
    size: str | None = None
    seeders: int | None = None
    leechers: int | None = None
    date: str | None = None
    detail_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


_VALID_BTIH_RE = re.compile(
    r"(?:urn:)?btih:(?:[0-9A-Fa-f]{40}|[A-Z2-7]{32})(?=$|[^A-Za-z0-9])",
    re.I,
)
_HASH_TITLE_RE = re.compile(r"^(?:[0-9A-Fa-f]{40}|[A-Z2-7]{32})$", re.I)
_HASH_LABEL_TITLE_RE = re.compile(
    r"^(?:hash|btih|info[-_\s]?hash)\s*[:：=]?\s*(?:[0-9A-Fa-f]{8,64}|[A-Z2-7]{16,32})(?:\.{3}|…)?$",
    re.I,
)


def has_valid_btih_magnet(value: str) -> bool:
    return bool(isinstance(value, str) and value.startswith("magnet:?") and _VALID_BTIH_RE.search(value))


def has_bound_result_title(result: SearchResult) -> bool:
    title = result.title.strip() if isinstance(result.title, str) else ""
    if not title or title.lower().startswith("magnet:?"):
        return False
    return not (_HASH_TITLE_RE.fullmatch(title) or _HASH_LABEL_TITLE_RE.fullmatch(title))


def valid_search_results(results: list[SearchResult]) -> list[SearchResult]:
    return [
        result
        for result in results
        if has_valid_btih_magnet(result.magnet) and has_bound_result_title(result)
    ]


def valid_magnet_results(results: list[SearchResult]) -> list[SearchResult]:
    """Backward-compatible magnet-only filter for callers that explicitly need it."""
    return [result for result in results if has_valid_btih_magnet(result.magnet)]


class TierError(Exception):
    """Raised when a Tier declines or fails recoverably. Triggers orchestrator fallback."""

    def __init__(self, reason: str, *, retryable: bool = False, hint: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable
        self.hint = hint


class Tier(ABC):
    """Tier interface. Subclasses live in tier0_http.py / tier1_cloak.py / ..."""

    kind: TierKind

    @abstractmethod
    def search(self, source: dict, query: str, *, limit: int = 24) -> list[SearchResult]:
        """Execute search on `source` for `query`. Return list of SearchResult.

        Raise TierError on declined/recoverable failure. Raise other exceptions
        only for genuine bugs.
        """
        raise NotImplementedError

    def supports(self, source: dict) -> bool:
        """Quick check whether this Tier can plausibly handle this source.

        Default: yes. Subclasses override for stronger filtering (e.g. Tier 2
        only supports sources with a registered handler).
        """
        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} kind={self.kind.value}>"
