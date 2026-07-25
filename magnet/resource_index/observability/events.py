"""Structured logging helpers."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any


def setup_logging(
    log_path: str | Path | None = None,
    *,
    append: bool = False,
) -> logging.Logger:
    logger = logging.getLogger("resource_index")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    fmt = logging.Formatter("%(asctime)s %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_path:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(
            path,
            encoding="utf-8",
            mode="a" if append else "w",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def log_event(
    logger: logging.Logger,
    *,
    run_id: str | None,
    source_id: str | None,
    stage: str,
    message: str,
    document_id: str | None = None,
    source_item_key: str | None = None,
    parser_version: str | None = None,
    error_code: str | None = None,
    **extra: Any,
) -> None:
    parts = [
        f"stage={stage}",
        f"msg={message}",
    ]
    if run_id:
        parts.insert(0, f"run_id={run_id}")
    if source_id:
        parts.append(f"source_id={source_id}")
    if document_id:
        parts.append(f"document_id={document_id}")
    if source_item_key:
        parts.append(f"source_item_key={source_item_key}")
    if parser_version:
        parts.append(f"parser_version={parser_version}")
    if error_code:
        parts.append(f"error_code={error_code}")
    for k, v in sorted(extra.items()):
        if k.lower() in {"cookie", "cookies", "authorization", "magnet", "magnet_uri"}:
            continue
        parts.append(f"{k}={v}")
    logger.info(" ".join(parts))
