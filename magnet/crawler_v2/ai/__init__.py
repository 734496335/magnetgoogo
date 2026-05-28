"""crawler_v2.ai — LLM-driven selector synthesis (OFFLINE-only).

This subpackage is NEVER called from the real-time search path. It exists to
generate `sources.json` selector drafts for sources that the deterministic
healer pipeline (Fetcher → Stealthy → LocalHeuristic) failed to parse.

Public API
----------
- resolve_llm_choice(): pick first available LLM provider from env
- synthesize_selectors_for_url(url, query, llm_choice): one-shot pipeline
  that fetches the page (StealthyFetcher) and asks the LLM to emit CSS
  selectors compatible with sources.json `search.parse_metadata.selectors`.
- validate_selectors(html, selectors): run candidate selectors against the
  fetched HTML to get a magnets/list_items confidence number.
- render_rule_draft(...): turn the synthesized + validated output into a
  sources.json rule-shaped dict (with `_ai_proposal` metadata).

CLI entry points live in `magnet/scripts/ai_reverify.py`, not here.
"""

from .llm_provider import LLMChoice, resolve_llm_choice
from .selector_synth import (
    MAGNET_RE,
    expand_search_url,
    fetch_page_html,
    synthesize_selectors_for_html,
    synthesize_selectors_for_url,
    validate_selectors,
    render_rule_draft,
)

__all__ = [
    "LLMChoice", "resolve_llm_choice",
    "MAGNET_RE", "expand_search_url",
    "fetch_page_html",
    "synthesize_selectors_for_html", "synthesize_selectors_for_url",
    "validate_selectors", "render_rule_draft",
]
