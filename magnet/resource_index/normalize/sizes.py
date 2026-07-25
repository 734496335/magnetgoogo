"""Size string → bytes."""

from __future__ import annotations

import re

from magnet.resource_index.errors import SIZE_INVALID, ValidationError

_SIZE_RE = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]i?B|B|字节|位元組)?\s*$",
    re.IGNORECASE,
)

_UNIT_MULTIPLIER = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
    "字节": 1,
    "位元組": 1,
}


def parse_size_bytes(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    m = _SIZE_RE.fullmatch(text)
    if not m:
        raise ValidationError(SIZE_INVALID, f"unrecognized size: {text}", {"value": text})
    amount = float(m.group(1))
    unit_raw = (m.group(2) or "B").upper()
    # Normalize Chinese units already mapped by exact key lower path
    unit = unit_raw
    if unit_raw in {"字节".upper(), "位元組".upper()}:
        unit = "B"
    # map KiB style
    if unit.endswith("IB"):
        unit = unit  # already KIB/MIB...
    elif unit in {"K", "M", "G", "T"}:
        unit = unit + "B"
    mult = _UNIT_MULTIPLIER.get(unit)
    if mult is None:
        # try original case for Chinese
        mult = _UNIT_MULTIPLIER.get(m.group(2) or "B")
    if mult is None:
        raise ValidationError(SIZE_INVALID, f"unknown size unit: {text}", {"value": text})
    return int(amount * mult)
