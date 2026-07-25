"""Lightweight in-process metrics counters."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class IngestMetrics:
    counters: Counter[str] = field(default_factory=Counter)

    def inc(self, name: str, n: int = 1) -> None:
        self.counters[name] += n

    def as_dict(self) -> dict[str, int]:
        return dict(self.counters)
