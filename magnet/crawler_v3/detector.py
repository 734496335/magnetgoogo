"""Anti-bot fingerprint detection → Tier routing decision.

Two-phase classification:
1. Static: look at sources.json metadata (tier_override, requires_browser,
   health.status_detail) for explicit hints.
2. Dynamic (optional, on-demand): HEAD/GET probe a source homepage, classify
   response content for CF/Turnstile/captcha markers.

Output: ordered list of TierKind to try, e.g. [HANDLER, HTTP, CLOAK].
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .tiers.base import TierKind

log = logging.getLogger(__name__)


@dataclass
class TierPlan:
    """Ordered list of Tiers to try, plus why."""
    order: list[TierKind]
    reason: str


def classify(source: dict) -> TierPlan:
    """Decide which Tiers to try for this source, in priority order.

    Static-only decision (no network). Dynamic classification is done by the
    orchestrator catching TierError("escalate_to_tier1") and walking down.
    """
    # Explicit override always wins
    override = source.get("tier_override") or {}
    if isinstance(override, dict) and override.get("tier"):
        forced = override["tier"]
        try:
            kind = TierKind(forced)
        except ValueError:
            log.warning("Unknown tier_override.tier %r, ignoring", forced)
        else:
            return TierPlan(order=_with_fallbacks(kind), reason=f"tier_override={forced}")

    # Heuristics on sources.json metadata
    requires_browser = source.get("requires_browser") or source.get("site", {}).get("requires_browser")
    status_detail = (source.get("health") or {}).get("status_detail")

    if requires_browser or status_detail == "waf":
        return TierPlan(order=[TierKind.CLOAK, TierKind.HTTP], reason="requires_browser or WAF history")

    # Default: fast path first, browser as escalation
    return TierPlan(order=[TierKind.HTTP, TierKind.CLOAK], reason="default fast-first")


def _with_fallbacks(primary: TierKind) -> list[TierKind]:
    """When forced to a specific Tier, still keep reasonable fallbacks."""
    if primary == TierKind.HANDLER:
        return [TierKind.HANDLER, TierKind.HTTP, TierKind.CLOAK]
    if primary == TierKind.HTTP:
        return [TierKind.HTTP, TierKind.CLOAK]
    if primary == TierKind.CLOAK:
        return [TierKind.CLOAK]  # no fallback below
    return [primary]


# ── Dynamic probing (optional, network call) ──

CHALLENGE_PATTERNS = {
    "cf_js": re.compile(r"challenge-platform|cf-browser-verification|Just a moment", re.I),
    "cf_turnstile": re.compile(r"turnstile|cf-turnstile", re.I),
    "custom_captcha": re.compile(r"/recaptcha/v4/challenge|hCaptcha|geetest", re.I),
    "ddos_guard": re.compile(r"ddos-guard|DDoS-GUARD", re.I),
    "cn_block": re.compile(r"请稍候|正在进行安全验证", re.I),
}


def probe_anti_bot(html_head: str) -> str | None:
    """Inspect HTML head for known anti-bot markers. Return marker name or None."""
    for name, pat in CHALLENGE_PATTERNS.items():
        if pat.search(html_head):
            return name
    return None
