"""Optional live fetcher stub — network path intentionally not used in phase-1 CI."""

from __future__ import annotations

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.errors import LIVE_FETCH_DISABLED, LivePolicyError


class LiveFetcher:
    """Phase-1: policy gate only; real HTTP is out of scope for CI."""

    def __init__(self, policy: LiveFetchPolicy) -> None:
        self.policy = policy
        self._cookies: dict[str, str] = {}  # memory only; never persisted

    def fetch(self, url: str) -> str:
        self.policy.assert_allowed()
        # Explicit hard stop: phase-1 implementation does not perform network I/O.
        raise LivePolicyError(
            LIVE_FETCH_DISABLED,
            "live HTTP fetch is not implemented for phase-1 acceptance; use fixtures",
            {"url_host": "redacted"},
        )

    def cookies_snapshot(self) -> dict[str, str]:
        # Return a copy; callers must not log values.
        return dict(self._cookies)

    def clear_cookies(self) -> None:
        self._cookies.clear()
