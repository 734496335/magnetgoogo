"""ssbc 平台共享 handler — 逆向自磁力天堂/磁力发/磁力王等 CryptoJS+AJAX 框架。

平台特征：
- 后端 API：POST /api/ssbc，表单数据 {key, type, from}
- 响应：JSON {data: {infos: {torrent: [{infohash, name_simple, size, category, ...}], sum, page}}}
- magnet 直接由 infohash 构造：magnet:?xt=urn:btih:{infohash}
- 前端用 CryptoJS DES-CBC 加密查询参数（仅用于 URL 美化，API 本身不需要加密）

当前命中源：
- berrl.com → cltt1.shop (磁力天堂)
- jzcilifa1.shop (磁力发)
- jzciliwang123.shop / movih.com (磁力王)
"""
from __future__ import annotations

import logging
import re
from typing import Any

from curl_cffi import requests as cc_requests

from ..tiers.base import SearchResult, TierError
from ..tiers.tier2_handler import register_handler

log = logging.getLogger(__name__)

PLATFORM_ID = "ssbc"

_MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:[A-Za-z0-9]{32,}[^\"<>\s]*", re.I)


def _format_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    decimals = 0 if value >= 100 else 1 if value >= 10 else 2
    numeric = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return f"{numeric} {units[unit_index]}"


def _expected_range(title: str) -> tuple[float, float] | None:
    normalized = (title or "").lower()
    mib = 1024 ** 2
    gib = 1024 ** 3
    if re.search(r"\b(?:2160p|4k|uhd)\b", normalized):
        return (1 * gib, 300 * gib)
    if re.search(r"\b(?:1080[pi]|remux|blu[ ._-]?ray|bdrip|hdrip|webrip|web[ ._-]?dl)\b", normalized):
        return (100 * mib, 300 * gib)
    if re.search(r"\b720[pi]\b", normalized):
        return (100 * mib, 80 * gib)
    if re.search(r"\.(?:mkv|mp4|avi|mov|wmv|m2ts|ts)(?:\b|$)", normalized):
        return (50 * mib, 300 * gib)
    if re.search(r"\.(?:iso|dmg|pkg|exe|msi|apk|zip|rar|7z)(?:\b|$)", normalized):
        return (1 * mib, 500 * gib)
    return None


def format_ssbc_size(raw: Any, title: str = "") -> str:
    """Resolve SSBC's mixed bytes/KiB field; hide ambiguous values."""
    try:
        numeric = float(str(raw or "0").replace(",", "").strip())
    except (TypeError, ValueError):
        return ""
    if not numeric or numeric <= 0:
        return ""
    candidates = (numeric, numeric * 1024)
    expected = _expected_range(title)
    if expected:
        plausible = [value for value in candidates if expected[0] <= value <= expected[1]]
    else:
        plausible = [value for value in candidates if 1024 ** 2 <= value <= 64 * 1024 ** 4]
    return _format_bytes(plausible[0]) if len(plausible) == 1 else ""


@register_handler(PLATFORM_ID)
def ssbc_search(source: dict, query: str) -> list[SearchResult]:
    """ssbc 平台搜索：直接调 /api/ssbc JSON 接口。"""
    origin = source.get("site", {}).get("origin", "").rstrip("/")
    if not origin:
        raise TierError("missing origin", retryable=False)

    # Strip query string from origin (e.g. ?ref=eeenav.com)
    origin = origin.split("?")[0].rstrip("/")

    session = cc_requests.Session(impersonate="chrome124")

    # Resolve redirect (berrl.com → cltt1.shop etc.)
    try:
        r = session.get(f"{origin}/", timeout=10, allow_redirects=True)
        real_origin = r.url.rstrip("/").split("?")[0].rstrip("/")
        if not real_origin or real_origin == origin:
            real_origin = origin
    except Exception:
        real_origin = origin

    # Call the search API on the real domain
    api_url = f"{real_origin}/api/ssbc"
    try:
        resp = session.post(
            api_url,
            data={"key": query, "type": "all", "from": 1},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        raise TierError(f"API request failed: {e}", retryable=True)

    # Parse JSON response
    try:
        body = resp.json()
    except Exception as e:
        raise TierError(f"API response not JSON: {e}", retryable=True)

    if body.get("code") != 200:
        raise TierError(f"API error: code={body.get('code')}", retryable=True)

    infos = (body.get("data") or {}).get("infos") or {}
    torrents = infos.get("torrent") or []
    if not torrents:
        raise TierError("API returned zero torrents", retryable=False)

    # Build results
    results: list[SearchResult] = []
    seen: set[str] = set()
    for t in torrents:
        infohash = t.get("infohash") or t.get("infohash_IK", "")
        if not infohash or infohash in seen:
            continue
        seen.add(infohash)
        magnet = f"magnet:?xt=urn:btih:{infohash}"
        name = t.get("name_simple") or t.get("name_IK", "")
        # Strip HTML tags from name
        name = re.sub(r"<[^>]+>", "", name)
        results.append(SearchResult(
            title=name,
            magnet=magnet,
            size=format_ssbc_size(t.get("size"), name),
        ))

    if not results:
        raise TierError("zero valid torrents after dedup", retryable=False)

    return results
