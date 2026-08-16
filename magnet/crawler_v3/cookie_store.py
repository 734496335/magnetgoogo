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
        if not isinstance(data, dict):
            log.warning("CookieStore: invalid document shape in %s", p)
            return []

        raw_cookies = data.get("cookies", [])
        if not isinstance(raw_cookies, list):
            log.warning("CookieStore: invalid cookies shape in %s", p)
            return []
        cookies = [c for c in raw_cookies if isinstance(c, dict)]
        now = time.time()
        alive = [c for c in cookies if self._cookie_is_alive(c, now)]

        if len(alive) != len(raw_cookies):
            # Prune expired/malformed entries with an atomic replacement so a
            # process interruption cannot leave a half-written cookie file.
            data["cookies"] = alive
            try:
                self._write_data(p, data)
            except OSError:
                pass

        return alive

    def put(self, origin: str, cookies: list[dict]) -> None:
        """Replace all cookies for origin."""
        p = self.path_for(origin)
        sanitized = [
            dict(cookie)
            for cookie in cookies
            if isinstance(cookie, dict)
            and isinstance(cookie.get("name"), str)
            and isinstance(cookie.get("value"), str)
        ]
        data = {
            "cookies": sanitized,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_data(p, data)

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
    def _cookie_is_alive(cookie: dict, now: float) -> bool:
        if not isinstance(cookie.get("name"), str) or not isinstance(cookie.get("value"), str):
            return False
        expires = cookie.get("expires")
        if expires in (None, ""):
            return True
        try:
            expiry = float(expires)
        except (TypeError, ValueError):
            return False
        # Playwright/CloakBrowser use -1 for session cookies; 0 is also
        # conventionally non-persistent. Only a positive timestamp can expire.
        return expiry <= 0 or expiry > now

    @staticmethod
    def _write_data(path: Path, data: dict) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _cookie_key(c: dict) -> str:
        """Unique key for a cookie: (domain, path, name)."""
        return f"{c.get('domain', '')}|{c.get('path', '/')}|{c.get('name', '')}"
