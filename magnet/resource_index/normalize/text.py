"""Text normalization helpers."""

from __future__ import annotations

import html
import re
import unicodedata


_WS_RE = re.compile(r"\s+")


def nfkc(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def normalize_whitespace(value: str) -> str:
    return _WS_RE.sub(" ", nfkc(value)).strip()


def decode_html_entities(value: str) -> str:
    return html.unescape(value)


def normalize_title(value: str, *, content_code: str | None = None) -> str:
    text = normalize_whitespace(decode_html_entities(value))
    if content_code:
        code = content_code.strip()
        # Strip leading duplicate content code prefix once.
        pattern = re.compile(
            rf"^{re.escape(code)}\s*[-:：]?\s*",
            re.IGNORECASE,
        )
        stripped = pattern.sub("", text, count=1).strip()
        if stripped:
            text = stripped
    return text


def normalize_person_name(value: str) -> str:
    return normalize_whitespace(decode_html_entities(value))
