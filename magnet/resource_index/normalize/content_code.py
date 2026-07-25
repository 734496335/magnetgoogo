"""Content code normalization."""

from __future__ import annotations

import re
import unicodedata

from magnet.resource_index.errors import CONTENT_CODE_INVALID, ValidationError

# Fullwidth hyphen / long dashes / underscore → ASCII hyphen
_DASH_TRANSLATION = str.maketrans(
    {
        "－": "-",
        "—": "-",
        "–": "-",
        "‑": "-",
        "―": "-",
        "_": "-",
        "＿": "-",
    }
)

_CODE_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
# Insert hyphen between letter run and trailing digits when missing: ABC123 → ABC-123
_LETTER_DIGIT_RE = re.compile(r"^([A-Z]+)(\d+)$")


def normalize_content_code(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", raw).strip()
    if not text:
        return None
    text = text.translate(_DASH_TRANSLATION)
    text = re.sub(r"\s+", "", text)
    text = text.upper()
    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text).strip("-")

    m = _LETTER_DIGIT_RE.fullmatch(text)
    if m:
        text = f"{m.group(1)}-{m.group(2)}"

    if not _CODE_RE.fullmatch(text):
        return None
    return text


def require_content_code(raw: str | None) -> str:
    code = normalize_content_code(raw)
    if not code:
        raise ValidationError(
            CONTENT_CODE_INVALID,
            "unable to normalize content_code",
            {"raw": raw},
        )
    return code
