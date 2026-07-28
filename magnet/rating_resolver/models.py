# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RatingValue:
    source: str
    status: str  # ok | no_match | blocked | error | skipped
    score: float | None = None
    scale: float = 10.0
    score_text: str | None = None
    url: str | None = None
    external_id: str | None = None
    matched_title: str | None = None
    matched_year: int | None = None
    confidence: float = 0.0
    note: str | None = None
    latency_ms: int | None = None
    via: str | None = None  # e.g. cinemeta fallback

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LookupQuery:
    title: str
    year: int | None = None
    imdb_id: str | None = None
    original_title: str | None = None

    def cache_key(self) -> str:
        y = self.year if self.year is not None else ""
        iid = (self.imdb_id or "").lower().strip()
        t = (self.title or "").strip().lower()
        original = (self.original_title or "").strip().lower()
        return f"{t}|{original}|{y}|{iid}"


@dataclass
class RatingReport:
    query: dict[str, Any]
    normalized_title: str
    ratings: dict[str, dict[str, Any]] = field(default_factory=dict)
    display: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: str = ""
    cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def ok_count(self) -> int:
        return sum(1 for r in self.ratings.values() if r.get("status") == "ok" and r.get("score") is not None)
