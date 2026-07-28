# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from magnet.rating_resolver.models import LookupQuery, RatingValue


class Provider(ABC):
    name: str = "base"

    @abstractmethod
    def lookup(self, query: LookupQuery) -> RatingValue:
        raise NotImplementedError

    def safe_lookup(self, query: LookupQuery) -> RatingValue:
        t0 = time.monotonic()
        try:
            result = self.lookup(query)
        except Exception as exc:  # noqa: BLE001 — provider isolation
            result = RatingValue(
                source=self.name,
                status="error",
                note=f"{type(exc).__name__}: {exc}",
            )
        if result.latency_ms is None:
            result.latency_ms = int((time.monotonic() - t0) * 1000)
        return result
