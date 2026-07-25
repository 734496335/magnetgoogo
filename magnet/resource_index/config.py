"""Runtime configuration for resource_index."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PARSER_VERSION = "javbus-parser/1.0.0"
SOURCE_ID_JAVBUS = "javbus"
SCHEMA_VERSION = "0001"

# Risk status reserved for future policy engine
RISK_MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class ResourceIndexConfig:
    db_path: Path
    fixture_root: Path | None
    live_fetch_enabled: bool
    log_path: Path | None
    parser_version: str = DEFAULT_PARSER_VERSION

    @classmethod
    def from_env(
        cls,
        *,
        db_path: str | Path | None = None,
        fixture_root: str | Path | None = None,
        log_path: str | Path | None = None,
    ) -> "ResourceIndexConfig":
        raw_db = db_path or os.environ.get("MAGNET_RESOURCE_DB") or "resource_index.db"
        raw_fix = fixture_root or os.environ.get("MAGNET_RESOURCE_FIXTURE_ROOT")
        raw_log = log_path or os.environ.get("MAGNET_RESOURCE_LOG_PATH")
        live = os.environ.get("MAGNET_RESOURCE_LIVE_FETCH_ENABLED", "0").strip() in {
            "1",
            "true",
            "TRUE",
            "yes",
            "YES",
        }
        return cls(
            db_path=Path(raw_db),
            fixture_root=Path(raw_fix) if raw_fix else None,
            live_fetch_enabled=live,
            log_path=Path(raw_log) if raw_log else None,
        )


def package_root() -> Path:
    return Path(__file__).resolve().parent


def default_javbus_source_config_path() -> Path:
    return package_root() / "config" / "sources" / "javbus.json"
