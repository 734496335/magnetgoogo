"""Shared live HTTP client (curl_cffi Session, memory cookies only)."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from magnet.resource_index.acquisition.policy import should_stop_on_status
from magnet.resource_index.errors import LIVE_RATE_LIMITED, LivePolicyError, ResourceIndexError

try:
    from curl_cffi import requests as cc_requests
except ImportError:  # pragma: no cover
    cc_requests = None  # type: ignore


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


@dataclass
class FetchResponse:
    url: str
    status_code: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)


class LiveHttpClient:
    """Single-flight HTTP client with delay + hard-stop on challenge pages."""

    def __init__(
        self,
        *,
        request_delay_seconds: float = 1.5,
        timeout_seconds: float = 30.0,
        impersonate: str = "chrome124",
        max_retries: int = 2,
    ) -> None:
        if cc_requests is None:
            raise ResourceIndexError(
                "CONFIG_ERROR",
                "curl_cffi is required for live crawl; pip install curl_cffi",
                {},
            )
        self.request_delay_seconds = max(0.0, float(request_delay_seconds))
        self.timeout_seconds = float(timeout_seconds)
        self.impersonate = impersonate
        self.max_retries = max_retries
        self._session = cc_requests.Session(impersonate=impersonate)
        self._last_request_at = 0.0
        self._stopped_reason: str | None = None

    @property
    def stopped_reason(self) -> str | None:
        return self._stopped_reason

    def clear_cookies(self) -> None:
        try:
            self._session.cookies.clear()
        except Exception:
            pass

    def cookies_snapshot(self) -> dict[str, str]:
        try:
            return {str(k): str(v) for k, v in self._session.cookies.items()}
        except Exception:
            return {}

    def _throttle(self) -> None:
        if self.request_delay_seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        wait = self.request_delay_seconds - elapsed
        if wait > 0:
            # small jitter avoids lockstep
            time.sleep(wait + random.uniform(0, min(0.3, self.request_delay_seconds * 0.1)))

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: Any = None,
        referer: str | None = None,
    ) -> FetchResponse:
        if self._stopped_reason:
            raise LivePolicyError(
                LIVE_RATE_LIMITED,
                f"client stopped: {self._stopped_reason}",
                {"reason": self._stopped_reason},
            )

        hdrs = dict(DEFAULT_HEADERS)
        if headers:
            hdrs.update(headers)
        if referer:
            hdrs["Referer"] = referer

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                resp = self._session.request(
                    method.upper(),
                    url,
                    headers=hdrs,
                    data=data,
                    timeout=self.timeout_seconds,
                    allow_redirects=True,
                )
                self._last_request_at = time.monotonic()
                text = resp.text or ""
                status = int(resp.status_code)
                stop = should_stop_on_status(status, text[:4000])
                # age_gate is handled by source crawler (session bootstrap), not hard-stop here
                # unless it's mid-crawl unexpected gate after session
                if stop and stop.startswith("http_"):
                    self._stopped_reason = stop
                    raise LivePolicyError(
                        LIVE_RATE_LIMITED,
                        f"hard stop on status {status}",
                        {"url_host": urlparse(url).netloc, "status": status},
                    )
                if stop == "access_challenge":
                    self._stopped_reason = stop
                    raise LivePolicyError(
                        "ACCESS_CHALLENGE",
                        "access challenge page detected",
                        {"url_host": urlparse(url).netloc},
                    )
                return FetchResponse(
                    url=str(resp.url),
                    status_code=status,
                    text=text,
                    headers={k: str(v) for k, v in dict(resp.headers).items()},
                )
            except LivePolicyError:
                raise
            except Exception as exc:  # network blips
                last_err = exc
                time.sleep(0.5 * (attempt + 1))
        raise ResourceIndexError(
            "LIVE_RATE_LIMITED",
            f"request failed after retries: {last_err}",
            {"url_host": urlparse(url).netloc},
        )

    def get(self, url: str, **kwargs: Any) -> FetchResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> FetchResponse:
        return self.request("POST", url, **kwargs)
