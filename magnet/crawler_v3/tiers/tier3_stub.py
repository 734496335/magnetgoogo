"""Tier 3 — User-assisted verification (RN VerifyWebView).

This Tier is implemented in the mobile client (magnetgoogo-app/src/components/
VerifyWebView.tsx + VerifyManager.ts). The Python engine cannot prompt a user,
so this is a stub that always raises TierError("not_implemented_in_python").

Kept here to make the 4-tier topology explicit and to allow the orchestrator
to log a meaningful "would have escalated to Tier 3" decision.
"""
from __future__ import annotations

from .base import SearchResult, Tier, TierError, TierKind


class Tier3UserAssistStub(Tier):
    kind = TierKind.USERASSIST

    def supports(self, source: dict) -> bool:
        return False  # never matches in Python; always declines

    def search(self, source: dict, query: str, *, limit: int = 24) -> list[SearchResult]:
        raise TierError(
            "Tier 3 user-assist is mobile-only (VerifyWebView). Python cannot fulfill.",
            retryable=False,
            hint="escalate_to_mobile_client",
        )
