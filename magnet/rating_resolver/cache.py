# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


class JsonCache:
    def __init__(self, root: Path, ttl_seconds: int = 86400 * 7) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _legacy_path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:180]
        return self.root / f"{safe}.json"

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        while len(safe.encode("utf-8")) > 96:
            safe = safe[:-1]
        safe = safe or "cache"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return self.root / f"{safe}-{digest}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        for path in (self._path(key), self._legacy_path(key)):
            try:
                if not path.exists():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            ts = float(data.get("_cached_at") or 0)
            if self.ttl_seconds > 0 and (time.time() - ts) > self.ttl_seconds:
                continue
            return data.get("payload")
        return None

    def set(self, key: str, payload: dict[str, Any]) -> None:
        path = self._path(key)
        blob = {"_cached_at": time.time(), "payload": payload}
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
