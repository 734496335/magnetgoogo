"""Example Tier 2 handler skeleton.

Copy this file to `{platform_id}.py` and fill in the algorithm. The leading
underscore prevents auto-load (it would otherwise register a fake handler).
"""
from __future__ import annotations

from ..tiers.base import SearchResult
from ..tiers.tier2_handler import register_handler


# @register_handler("example_platform")
def example_search(source: dict, query: str) -> list[SearchResult]:
    """Replace this with the reverse-engineered algorithm.

    Steps typically look like:
        token = _compute_token(query, ts=int(time.time()))
        resp = curl_cffi.get(api_url, params={"q": query, "t": token, ...})
        data = resp.json()
        return [SearchResult(title=..., magnet=..., size=..., seeders=...)
                for item in data["list"]]
    """
    raise NotImplementedError("example handler — copy this file and implement")
