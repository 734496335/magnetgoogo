"""Reverse-engineered handlers (Tier 2 payload).

Each module in this package registers itself via @register_handler("platform_id").
The Tier 2 dispatcher auto-imports everything here at startup.

To add a new handler:
1. Use hello_js_reverse_skill + js-reverse-mcp to reverse the target site's
   token/signature algorithm (workflow: Phase 0 → 5).
2. Translate the recovered JS into a pure-Python function.
3. Save as `magnet/crawler_v3/handlers/{platform_id}.py`.
4. Map sources.json rules to it via `tier_override: {tier: "tier2_handler",
   platform: "{platform_id}"}`.

See `_example.py` for the minimum skeleton.
"""
