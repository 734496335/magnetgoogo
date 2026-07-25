"""Magnet URI and info-hash normalization."""

from __future__ import annotations

import base64
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse

from magnet.resource_index.errors import INFO_HASH_INVALID, MAGNET_INVALID, ValidationError

_HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
_B32 = re.compile(r"^[A-Z2-7]{32}$")


def info_hash_from_btih(token: str) -> str:
    raw = unquote(token).strip()
    if _HEX40.fullmatch(raw):
        return raw.lower()
    upper = raw.upper().replace("=", "")
    if _B32.fullmatch(upper):
        try:
            data = base64.b32decode(upper + ("=" * ((8 - len(upper) % 8) % 8)))
        except Exception as exc:  # noqa: BLE001 - map to domain error
            raise ValidationError(
                INFO_HASH_INVALID,
                "base32 decode failed",
                {"token": token},
            ) from exc
        if len(data) != 20:
            raise ValidationError(
                INFO_HASH_INVALID,
                "base32 hash must decode to 20 bytes",
                {"token": token},
            )
        return data.hex()
    raise ValidationError(
        INFO_HASH_INVALID,
        "info hash must be 40 hex or 32 base32",
        {"token": token},
    )


def extract_info_hash(magnet_uri: str) -> str:
    if not magnet_uri or not magnet_uri.startswith("magnet:?"):
        raise ValidationError(MAGNET_INVALID, "not a magnet URI", {"uri": magnet_uri})
    # Parse query without requiring full URL authority
    query = magnet_uri[len("magnet:?") :]
    pairs = parse_qsl(query, keep_blank_values=False)
    for key, value in pairs:
        if key.lower() != "xt":
            continue
        val = unquote(value)
        lower = val.lower()
        if lower.startswith("urn:btih:"):
            return info_hash_from_btih(val[9:])
    raise ValidationError(MAGNET_INVALID, "missing xt=urn:btih", {"uri": magnet_uri})


def normalize_magnet_uri(magnet_uri: str, *, fallback_dn: str | None = None) -> tuple[str, str]:
    """Return (normalized_magnet_uri, info_hash_hex40)."""
    if not magnet_uri or not magnet_uri.startswith("magnet:?"):
        raise ValidationError(MAGNET_INVALID, "not a magnet URI", {"uri": magnet_uri})

    query = magnet_uri[len("magnet:?") :]
    pairs = parse_qsl(query, keep_blank_values=True)

    info_hash: str | None = None
    dn: str | None = None
    trackers: list[str] = []
    others: list[tuple[str, str]] = []

    for key, value in pairs:
        lk = key.lower()
        if not value and lk not in {"dn"}:
            continue
        if lk == "xt":
            val = unquote(value)
            if val.lower().startswith("urn:btih:"):
                info_hash = info_hash_from_btih(val[9:])
            else:
                raise ValidationError(MAGNET_INVALID, "unsupported xt", {"xt": value})
        elif lk == "dn":
            try:
                dn = unquote(value)
            except Exception:  # noqa: BLE001
                dn = fallback_dn
        elif lk == "tr":
            tr = unquote(value).strip()
            if tr and tr not in trackers:
                trackers.append(tr)
        else:
            others.append((lk, value))

    if not info_hash:
        raise ValidationError(MAGNET_INVALID, "missing btih", {})

    if not dn:
        dn = fallback_dn

    trackers = sorted(set(trackers))
    parts: list[str] = [f"xt=urn:btih:{info_hash}"]
    if dn:
        parts.append(f"dn={quote(dn, safe='')}")
    for tr in trackers:
        parts.append(f"tr={quote(tr, safe=':/?&=%')}")
    for k, v in sorted(others, key=lambda x: x[0]):
        if v:
            parts.append(f"{k}={quote(v, safe='')}")

    return "magnet:?" + "&".join(parts), info_hash
