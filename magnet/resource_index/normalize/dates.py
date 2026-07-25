"""Date and duration parsing."""

from __future__ import annotations

import re
from datetime import date, datetime

from magnet.resource_index.errors import DATE_INVALID, DURATION_INVALID, ValidationError

_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y年%m月%d日",
)


def parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    # Extract first YYYY-MM-DD-like token
    m = re.search(r"(\d{4})[./年\-](\d{1,2})[./月\-](\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError as exc:
            raise ValidationError(DATE_INVALID, f"invalid date: {text}", {"value": text}) from exc
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError(DATE_INVALID, f"unrecognized date: {text}", {"value": text})


def parse_duration_minutes(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    m = re.search(r"(\d+)\s*(?:分鐘|分钟|min|minutes?|m)?", text, re.IGNORECASE)
    if not m:
        raise ValidationError(
            DURATION_INVALID,
            f"unrecognized duration: {text}",
            {"value": text},
        )
    minutes = int(m.group(1))
    if minutes <= 0 or minutes > 24 * 60:
        raise ValidationError(
            DURATION_INVALID,
            f"duration out of range: {minutes}",
            {"value": text},
        )
    return minutes
