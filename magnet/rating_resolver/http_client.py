# -*- coding: utf-8 -*-
"""Minimal HTTP helper for rating crawlers (independent of resource_index)."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

try:
    from curl_cffi import requests as cf_requests
except ImportError:  # pragma: no cover
    cf_requests = None  # type: ignore

try:
    import requests as py_requests
except ImportError:  # pragma: no cover
    py_requests = None  # type: ignore

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class HttpResult:
    url: str
    status_code: int
    text: str
    content: bytes
    headers: dict[str, str]
    elapsed_ms: int


class RateLimiter:
    def __init__(self, min_interval: float = 0.8) -> None:
        self.min_interval = min_interval
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        now = time.monotonic()
        prev = self._last.get(host, 0.0)
        gap = self.min_interval - (now - prev)
        if gap > 0:
            time.sleep(gap)
        self._last[host] = time.monotonic()


_limiter = RateLimiter(float(os.environ.get("RATING_MIN_INTERVAL", "0.7")))


def _proxy() -> str | None:
    return (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("http_proxy")
        or None
    )


def fetch(
    url: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
    impersonate: str = "chrome124",
    allow_redirects: bool = True,
) -> HttpResult:
    from urllib.parse import urlparse

    if params:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urlencode(params)}"

    host = urlparse(url).hostname or "unknown"
    _limiter.wait(host)

    hdrs = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if headers:
        hdrs.update(headers)

    proxies = None
    proxy = _proxy()
    if proxy:
        proxies = {"http": proxy, "https": proxy}

    t0 = time.monotonic()
    status = 0
    text = ""
    content = b""
    resp_headers: dict[str, str] = {}
    final_url = url

    last_err: Exception | None = None
    if cf_requests is not None:
        try:
            resp = cf_requests.request(
                method,
                url,
                headers=hdrs,
                timeout=timeout,
                impersonate=impersonate,
                allow_redirects=allow_redirects,
                proxies=proxies,
            )
            status = int(resp.status_code)
            text = resp.text or ""
            content = resp.content or b""
            resp_headers = {k: v for k, v in (resp.headers or {}).items()}
            final_url = str(getattr(resp, "url", url) or url)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            status = 0

    if status == 0:
        if py_requests is None:
            if last_err is not None:
                raise RuntimeError(f"fetch failed and requests unavailable: {last_err}") from last_err
            raise RuntimeError("no HTTP backend available (need curl_cffi or requests)")
        try:
            resp = py_requests.request(
                method,
                url,
                headers=hdrs,
                timeout=timeout,
                allow_redirects=allow_redirects,
                proxies=proxies,
            )
            status = int(resp.status_code)
            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"
            text = resp.text or ""
            content = resp.content or b""
            resp_headers = {k: v for k, v in resp.headers.items()}
            final_url = str(resp.url)
        except Exception as exc:  # noqa: BLE001
            if last_err is not None:
                raise RuntimeError(f"fetch failed: {exc}") from last_err
            raise

    elapsed = int((time.monotonic() - t0) * 1000)
    return HttpResult(
        url=final_url,
        status_code=status,
        text=text,
        content=content,
        headers=resp_headers,
        elapsed_ms=elapsed,
    )
