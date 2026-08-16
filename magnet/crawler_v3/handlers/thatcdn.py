"""thatcdn 平台共享 handler — 逆向自 prod.b5.thatcdn.com 反爬机制。

平台特征：
- 资产 CDN：`prod.b5.thatcdn.com` (CSS + 图标)
- 模板：Bootstrap 3.3.7 + jQuery + jquery.cookie
- 反爬：搜索请求触发 `/anti/recaptcha/v4/verify` captcha challenge
  1. GET /search?keyword={q} → 返回 captcha challenge 页面
  2. JS 调 /anti/recaptcha/v4/gen?aywcUid={uid} 获取 token
  3. 表单提交到 /anti/recaptcha/v4/verify?token=&aywcUid=&costtime=
  4. 验证通过后返回搜索结果（含 /detail/ 链接，需二跳拿 magnet）
- 导航站机制：xiongmaogb.top 等域名是导航页，通过 <meta name="rdata">
  base64 编码指向真实搜索域名

当前命中源：
- xiongmaogb.top → xiongmaoqv.top (磁力熊猫)
- lemonun.top → lemonqv.top (磁力柠檬)
- wuqianso.org → wuqianto.cc (吴签磁力)
- laowangzo.top (老王磁力)
- soxiongmao.top / lemonzc.top / bt1207yx.top / wuqianyx.top (?ref=eeenav)
"""
from __future__ import annotations

import base64
import json
import logging
import random
import re
import string
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin

from curl_cffi import requests as cc_requests

from ..tiers.base import SearchResult, TierError
from ..tiers.tier2_handler import register_handler

log = logging.getLogger(__name__)

PLATFORM_ID = "thatcdn"

_MAGNET_RE = re.compile(
    r"magnet:\?xt=urn:btih:(?:[0-9A-Fa-f]{40}|[A-Z2-7]{32})(?=$|[^A-Za-z0-9])[^\"<>\s]*",
    re.I,
)
_RDATA_RE = re.compile(
    r'<meta[^>]*name=["\']rdata["\'][^>]*content=["\']([^"\']+)["\']', re.I
)
_DETAIL_HREF_RE = re.compile(r'href=["\'](/detail/[^"\'>]+)["\']', re.I)
_TITLE_RE = re.compile(
    r'<h3[^>]*class="[^"]*panel-title[^"]*"[^>]*>.*?'
    r'<a[^>]*href="(/detail/[^">]+)"[^>]*>(.*?)</a>',
    re.I | re.S,
)


def _random_str(n: int = 10) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=n))


def _resolve_redirect_domain(session: cc_requests.Session, origin: str) -> str:
    """If origin is a navigation/redirect page, follow rdata to the real domain."""
    try:
        r = session.get(origin + "/", timeout=15)
        if r.status_code != 200:
            return origin
        m = _RDATA_RE.search(r.text)
        if not m:
            return origin
        decoded = base64.b64decode(m.group(1)[::-1]).strip()
        data = json.loads(decoded)
        urls = data.get("urls") or []
        if urls:
            return urls[0].rstrip("/")
    except Exception as e:
        log.debug("[thatcdn] redirect resolve failed for %s: %s", origin, e)
    return origin


def _solve_captcha(
    session: cc_requests.Session, origin: str, query: str
) -> str | None:
    """Solve the thatcdn recaptcha challenge. Returns the search-results HTML or None."""
    enc_query = quote(query)
    search_url = f"{origin}/search?keyword={enc_query}"
    referer = f"{origin}/"

    # Trigger captcha
    r_search = session.get(search_url, timeout=15, headers={"Referer": referer})
    if r_search.status_code != 200:
        return None

    # If the response already contains magnets, no captcha needed
    if _MAGNET_RE.search(r_search.text):
        return r_search.text

    # Check if it's a captcha challenge page
    if "challenge" not in r_search.text.lower() and "recaptcha" not in r_search.text.lower():
        # Not a captcha page — might be results or homepage
        if len(r_search.text) > 5000:
            return r_search.text
        return None

    # Generate aywcUid
    aywc_uid = _random_str(10) + "_" + datetime.now().strftime("%Y%m%d%H%M%S")
    ts = int(time.time() * 1000)

    # Call gen API
    gen_url = f"{origin}/anti/recaptcha/v4/gen?aywcUid={aywc_uid}&_={ts}"
    r_gen = session.get(gen_url, timeout=15, headers={"Referer": search_url})
    try:
        gen_data = r_gen.json()
    except Exception:
        return None

    if gen_data.get("errno") != 0:
        return None

    token = gen_data["token"]
    costtime = int(time.time() * 1000) - ts + 3000

    # Submit verify
    r_verify = session.get(
        f"{origin}/anti/recaptcha/v4/verify",
        params={"token": token, "aywcUid": aywc_uid, "costtime": costtime},
        timeout=15,
        headers={"Referer": search_url},
    )

    if r_verify.status_code != 200:
        return None

    # Verify should return search results (redirected back to /search?keyword=...)
    if len(r_verify.text) < 5000:
        # Might have been redirected to homepage — captcha failed
        return None

    return r_verify.text


def _parse_search_results(
    html: str, origin: str
) -> list[dict[str, str]]:
    """Parse search results page. Returns list of {title, detail_url}."""
    results = []
    for m in _TITLE_RE.finditer(html):
        href = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if title and href:
            results.append({
                "title": title,
                "detail_url": urljoin(origin, href),
            })
    return results


def _fetch_detail_magnets(
    session: cc_requests.Session, detail_url: str, referer: str
) -> list[str]:
    """Fetch a detail page and extract magnet URIs."""
    try:
        r = session.get(detail_url, timeout=15, headers={"Referer": referer})
        if r.status_code != 200:
            return []
        return _MAGNET_RE.findall(r.text)
    except Exception:
        return []


@register_handler(PLATFORM_ID)
def thatcdn_search(source: dict, query: str) -> list[SearchResult]:
    """thatcdn 平台搜索：captcha bypass + detail follow."""
    origin = source.get("site", {}).get("origin", "").rstrip("/")
    if not origin:
        raise TierError("missing origin", retryable=False)

    session = cc_requests.Session(impersonate="chrome124")

    # Resolve redirect domains (xiongmaogb.top → xiongmaoqv.top etc.)
    real_origin = _resolve_redirect_domain(session, origin)

    # Solve captcha and get search results HTML
    html = _solve_captcha(session, real_origin, query)
    if not html:
        raise TierError(
            "captcha solve failed or zero results",
            retryable=True,
            hint="captcha_algorithm_may_have_changed",
        )

    # Parse search result items
    items = _parse_search_results(html, real_origin)
    if not items:
        raise TierError("no search results parsed from HTML", retryable=False)

    # Follow detail pages to get magnets (up to 10)
    results: list[SearchResult] = []
    seen_magnets: set[str] = set()
    referer = f"{real_origin}/search?keyword={quote(query)}"

    for item in items[:10]:
        magnets = _fetch_detail_magnets(session, item["detail_url"], referer)
        for mag in magnets:
            if mag in seen_magnets:
                continue
            seen_magnets.add(mag)
            results.append(SearchResult(
                title=item["title"],
                magnet=mag,
                detail_url=item["detail_url"],
            ))

    if not results:
        raise TierError(
            "detail pages yielded zero magnets",
            retryable=True,
            hint="detail_page_structure_may_have_changed",
        )

    return results
