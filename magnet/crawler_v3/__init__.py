"""crawler_v3 — 4-Tier unified crawler.

Public API:
    from magnet.crawler_v3 import search, classify, SearchResult

See README.md for architecture.
"""
from .orchestrator import search, classify
from .tiers.base import SearchResult, Tier, TierError

__all__ = ["search", "classify", "SearchResult", "Tier", "TierError"]
__version__ = "3.0.0-alpha"
