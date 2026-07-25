"""Live acquisition policy gates."""

from __future__ import annotations

import os
from dataclasses import dataclass

from magnet.resource_index.errors import (
    LIVE_FETCH_DISABLED,
    LIVE_POLICY_NOT_ACKNOWLEDGED,
    LIVE_RATE_LIMITED,
    LivePolicyError,
)

MIN_DELAY_SECONDS = 10.0
RECOMMENDED_DELAY_SECONDS = 10.0
DEFAULT_MAX_DETAIL_PAGES = 40
HARD_MAX_PAGES = 200
MAX_CONCURRENCY = 1


@dataclass
class PhysicalRequestBudget:
    limit: int
    used: int = 0

    def assert_available(self, *, url_host: str | None = None) -> None:
        if self.limit <= 0 or self.used >= self.limit:
            raise LivePolicyError(
                LIVE_RATE_LIMITED,
                f"physical request budget exhausted ({self.limit})",
                {"max_pages": self.limit, "used": self.used, "url_host": url_host},
            )

    def consume(self, *, url_host: str | None = None) -> None:
        self.assert_available(url_host=url_host)
        self.used += 1

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


@dataclass(frozen=True)
class LiveFetchPolicy:
    enabled: bool
    acknowledged: bool
    max_pages: int
    request_delay_seconds: float
    concurrency: int = MAX_CONCURRENCY

    @classmethod
    def from_flags(
        cls,
        *,
        env_enabled: bool | None = None,
        acknowledged: bool = False,
        max_pages: int | None = None,
        request_delay_seconds: float | None = None,
    ) -> "LiveFetchPolicy":
        if env_enabled is None:
            env_enabled = os.environ.get(
                "MAGNET_RESOURCE_LIVE_FETCH_ENABLED", "0"
            ).strip().lower() in {"1", "true", "yes", "on"}
        delay = (
            RECOMMENDED_DELAY_SECONDS
            if request_delay_seconds is None
            else float(request_delay_seconds)
        )
        pages = DEFAULT_MAX_DETAIL_PAGES if max_pages is None else int(max_pages)
        return cls(
            enabled=bool(env_enabled),
            acknowledged=bool(acknowledged),
            max_pages=pages,
            request_delay_seconds=delay,
            concurrency=MAX_CONCURRENCY,
        )

    def assert_allowed(self) -> None:
        if not self.enabled:
            raise LivePolicyError(
                LIVE_FETCH_DISABLED,
                "live fetch disabled (pass --live and acknowledge, or set MAGNET_RESOURCE_LIVE_FETCH_ENABLED=1)",
                {},
            )
        if not self.acknowledged:
            raise LivePolicyError(
                LIVE_POLICY_NOT_ACKNOWLEDGED,
                "missing policy acknowledgement (--yes / --acknowledge-source-policy)",
                {},
            )
        if self.max_pages <= 0:
            raise LivePolicyError(
                LIVE_RATE_LIMITED,
                "max_pages must be positive",
                {"max_pages": self.max_pages},
            )
        if self.max_pages > HARD_MAX_PAGES:
            raise LivePolicyError(
                LIVE_RATE_LIMITED,
                f"max_pages exceeds hard cap {HARD_MAX_PAGES}",
                {"max_pages": self.max_pages},
            )
        if self.request_delay_seconds < MIN_DELAY_SECONDS:
            raise LivePolicyError(
                LIVE_RATE_LIMITED,
                f"request_delay_seconds must be >= {MIN_DELAY_SECONDS}",
                {"request_delay_seconds": self.request_delay_seconds},
            )
        if self.concurrency != MAX_CONCURRENCY:
            raise LivePolicyError(
                LIVE_RATE_LIMITED,
                "concurrency must be 1",
                {"concurrency": self.concurrency},
            )


def should_stop_on_status(status_code: int | None, body_snippet: str = "") -> str | None:
    """Return stop reason code if acquisition must halt immediately."""
    if status_code in {403, 429}:
        return f"http_{status_code}"
    lower = (body_snippet or "").lower()
    if "cf-challenge" in lower or "just a moment" in lower or "turnstile" in lower:
        return "access_challenge"
    if "driver-verify" in lower or "age verification" in lower:
        return "age_gate"
    if "成年" in (body_snippet or "") and "movie-box" not in lower:
        # only treat as age gate when not already a content page
        if "確認" in (body_snippet or "") or "确认" in (body_snippet or ""):
            return "age_gate"
    return None
