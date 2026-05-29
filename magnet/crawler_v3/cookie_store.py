"""Per-origin cookie persistence with TTL.

Storage: ~/.cache/magnet/cookies/<origin_safe>.json
Format: {"cookies": [{"name", "value", "domain", "path", "expires"}], "stored_at": iso_ts}

Design:
- Pure JSON files, no external KV dependency
- Lazy expiry pruning at get() time
- Empty cookie list is valid (site passed verification without setting cookies)
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_ROOT = Path.home() / ".cache" / "magnet" / "cookies"


class CookieStore:
    """Per-origin cookie persistence with TTL."""

    def __init__(self, root: Path | None = None, default_ttl_days: int = 30):
        self.root = root or _DEFAULT_ROOT
        self.default_ttl_days = default_ttl_days
        self.root.mkdir(parents=True, exist_ok=True)

    # ── path helpers ──

    @staticmethod
    def _origin_safe(origin: str) -> str:
        """Convert origin to filesystem-safe name."""
        return re.sub(r"[^\w.-]", "_", origin)

    def path_for(self, origin: str) -> Path:
        return self.root / f"{self._origin_safe(origin)}.json"

    # ── core CRUD ──

    def get(self, origin: str) -> list[dict]:
        """Return non-expired cookies for origin (empty list if none/expired)."""
        p = self.path_for(origin)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("CookieStore: corrupt file %s: %s", p, e)
            return []

        cookies = data.get("cookies", [])
        now = time.time()
        alive = [c for c in cookies if not c.get("expires") or c["expires"] > now]

        if len(alive) != len(cookies):
            # prune expired and rewrite
            data["cookies"] = alive
            try:
                p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass

        return alive

    def put(self, origin: str, cookies: list[dict]) -> None:
        """Replace all cookies for origin."""
        p = self.path_for(origin)
        data = {
            "cookies": cookies,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def merge(self, origin: str, cookies: list[dict]) -> None:
        """Add to existing without dropping unrelated cookies."""
        existing = {self._cookie_key(c): c for c in self.get(origin)}
        for c in cookies:
            existing[self._cookie_key(c)] = c
        self.put(origin, list(existing.values()))

    def delete(self, origin: str) -> None:
        p = self.path_for(origin)
        if p.exists():
            p.unlink()

    def list_origins(self) -> list[str]:
        """List all origins that have stored cookies."""
        origins = []
        for f in self.root.glob("*.json"):
            origins.append(f.stem)
        return origins

    # ── format helpers ──

    def to_header(self, origin: str) -> str:
        """Return Cookie header string for HTTP requests."""
        cookies = self.get(origin)
        if not cookies:
            return ""
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies if "name" in c and "value" in c)

    def to_curl_cffi_format(self, origin: str) -> dict:
        """Return dict suitable for curl_cffi.requests.Session.cookies.update()."""
        cookies = self.get(origin)
        return {c["name"]: c["value"] for c in cookies if "name" in c and "value" in c}

    # ── internal ──

    @staticmethod
    def _cookie_key(c: dict) -> str:
        """Unique key for a cookie: (domain, path, name)."""
        return f"{c.get('domain', '')}|{c.get('path', '/')}|{c.get('name', '')}"
