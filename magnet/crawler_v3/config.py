"""Configuration knobs for crawler_v3.

Override via environment variables (prefix MAGNET_V3_):
    MAGNET_V3_HTTP_TIMEOUT=20
    MAGNET_V3_CLOAK_HEADLESS=0      (0 = headed, 1 = headless)
    MAGNET_V3_CLOAK_HUMANIZE=1
    MAGNET_V3_IMPERSONATE=chrome124
"""
from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(f"MAGNET_V3_{name}", default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(f"MAGNET_V3_{name}")
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


HTTP_TIMEOUT = _env_int("HTTP_TIMEOUT", 15)
CLOAK_TIMEOUT = _env_int("CLOAK_TIMEOUT", 30)
CLOAK_HEADLESS = _env_bool("CLOAK_HEADLESS", True)
CLOAK_HUMANIZE = _env_bool("CLOAK_HUMANIZE", True)
IMPERSONATE = os.environ.get("MAGNET_V3_IMPERSONATE", "chrome124")
