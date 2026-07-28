# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class JsonCache:
    def __init__(self, root: Path, ttl_seconds: int = 86400 * 7) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:180]
        return self.root / f"{safe}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        ts = float(data.get("_cached_at") or 0)
        if self.ttl_seconds > 0 and (time.time() - ts) > self.ttl_seconds:
            return None
        return data.get("payload")

    def set(self, key: str, payload: dict[str, Any]) -> None:
        path = self._path(key)
        blob = {"_cached_at": time.time(), "payload": payload}
        path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
