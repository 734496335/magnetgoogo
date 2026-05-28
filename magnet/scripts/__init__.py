"""Operational CLI scripts (NOT next-throwaway tools).

These are the canonical entry points for batch operations. They import
functionality from `crawler/`, `crawler_v2/`, `crawler_v2.ai`, and
`discovery/` — they never reimplement business logic.

Naming:
  - `ai_reverify.py`     — batch-rerun AI selector synthesis on suspect sources
  - `brand_rediscover.py` — batch-find replacement domains for collapsed families
  - (future) `verify_and_heal.py` may move here from magnet/ root

If you find yourself wanting to write a new `_xxx.py` tool, ask first:
"What module does this belong in, and what function does it expose?"
"""
