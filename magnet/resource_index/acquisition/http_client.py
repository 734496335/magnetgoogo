"""Shared live HTTP client with physical request governance."""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from magnet.resource_index.acquisition.policy import (
    PhysicalRequestBudget,
    should_stop_on_status,
)
from magnet.resource_index.errors import (
    AGE_GATE_PAGE,
    LIVE_HTTP_ERROR,
    LIVE_RATE_LIMITED,
    LIVE_URL_REJECTED,
    LivePolicyError,
    ResourceIndexError,
)

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

_RETRYABLE_STATUS = {408, 425, 500, 502, 503, 504}
_REDIRECT_STATUS = {301, 302, 303, 307, 308}

DnsResolver = Callable[[str, int], list[str]]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]


@dataclass
class FetchResponse:
    url: str
    status_code: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b""


def _effective_port(scheme: str, port: int | None) -> int:
    if port is not None:
        return port
    return 443 if scheme == "https" else 80


def normalized_origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LivePolicyError(
            LIVE_URL_REJECTED,
            "live URL must use http/https and include a host",
            {"scheme": parsed.scheme or None},
        )
    try:
        port = _effective_port(parsed.scheme, parsed.port)
    except ValueError as exc:
        raise LivePolicyError(
            LIVE_URL_REJECTED,
            "live URL contains an invalid port",
            {"url_host": parsed.hostname},
        ) from exc
    return f"{parsed.scheme}://{parsed.hostname.rstrip('.').lower()}:{port}"


_FORBIDDEN_IPV4_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.168.0.0/16",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)
_FORBIDDEN_IPV6_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "2001:db8::/32",
        "ff00::/8",
    )
)


def _is_forbidden_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    networks = (
        _FORBIDDEN_IPV4_NETWORKS
        if isinstance(address, ipaddress.IPv4Address)
        else _FORBIDDEN_IPV6_NETWORKS
    )
    return any(address in network for network in networks)


def _resolve_host_addresses(host: str, port: int) -> list[str]:
    addresses: set[str] = set()
    for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        addresses.add(str(item[4][0]))
    return sorted(addresses)


def validate_live_url(
    url: str,
    *,
    allowed_origins: set[str] | None = None,
    dns_resolver: DnsResolver | None = None,
) -> str:
    parsed = urlparse(url)
    origin = normalized_origin(url)
    if parsed.username or parsed.password:
        raise LivePolicyError(
            LIVE_URL_REJECTED,
            "credentials in live URL are forbidden",
            {"url_origin": origin},
        )

    normalized_allowed = {
        normalized_origin(item) for item in (allowed_origins or set())
    }
    if normalized_allowed and origin not in normalized_allowed:
        raise LivePolicyError(
            LIVE_URL_REJECTED,
            "URL origin is outside the source allowlist",
            {"url_origin": origin, "allowed_origins": sorted(normalized_allowed)},
        )

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise LivePolicyError(
            LIVE_URL_REJECTED,
            "localhost URLs are forbidden",
            {"url_origin": origin},
        )

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and _is_forbidden_ip(str(literal)):
        raise LivePolicyError(
            LIVE_URL_REJECTED,
            "private or special-purpose IP URLs are forbidden",
            {"url_origin": origin},
        )

    if dns_resolver is not None and literal is None:
        try:
            port = _effective_port(parsed.scheme, parsed.port)
            addresses = dns_resolver(host, port)
        except (OSError, ValueError) as exc:
            raise ResourceIndexError(
                LIVE_HTTP_ERROR,
                f"DNS resolution failed: {exc}",
                {"url_origin": origin},
            ) from exc
        if not addresses:
            raise ResourceIndexError(
                LIVE_HTTP_ERROR,
                "DNS resolution returned no addresses",
                {"url_origin": origin},
            )
        forbidden = [address for address in addresses if _is_forbidden_ip(address)]
        if forbidden:
            raise LivePolicyError(
                LIVE_URL_REJECTED,
                "URL resolves to a private or special-purpose address",
                {"url_origin": origin, "addresses": forbidden},
            )
    return origin


def _header(headers: dict[str, Any], name: str) -> str | None:
    target = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == target:
            return str(value)
    return None


def _decode_content(content: bytes, headers: dict[str, str]) -> str:
    candidates: list[str] = []
    content_type = _header(headers, "content-type") or ""
    header_match = re.search(r"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)", content_type, re.I)
    if header_match:
        candidates.append(header_match.group(1))
    meta_match = re.search(
        br"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)",
        content[:4096],
        re.I,
    )
    if meta_match:
        candidates.append(meta_match.group(1).decode("ascii", errors="ignore"))
    candidates.extend(["utf-8", "gb18030"])
    tried: set[str] = set()
    for candidate in candidates:
        normalized = candidate.casefold()
        if normalized in {"gb2312", "gbk", "x-gbk"}:
            candidate = "gb18030"
            normalized = candidate
        if normalized in tried:
            continue
        tried.add(normalized)
        try:
            return content.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


class LiveHttpClient:
    """Single-flight HTTP client with per-attempt budget, spacing and redirect fencing."""

    manages_request_budget = True

    def __init__(
        self,
        *,
        request_delay_seconds: float = 10.0,
        timeout_seconds: float = 30.0,
        impersonate: str = "chrome124",
        max_retries: int = 2,
        max_redirects: int = 5,
        allowed_origins: set[str] | None = None,
        request_budget: PhysicalRequestBudget | None = None,
        dns_resolver: DnsResolver | None = _resolve_host_addresses,
        monotonic: Clock = time.monotonic,
        sleep: Sleeper = time.sleep,
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
        self.max_retries = max(0, int(max_retries))
        self.max_redirects = max(0, int(max_redirects))
        self.allowed_origins = {
            normalized_origin(item) for item in (allowed_origins or set())
        }
        if not self.allowed_origins:
            raise ResourceIndexError(
                "CONFIG_ERROR",
                "allowed_origins is required for live HTTP",
                {},
            )
        self.request_budget = request_budget
        self.dns_resolver = dns_resolver
        self._monotonic = monotonic
        self._sleep = sleep
        self._session = cc_requests.Session(impersonate=impersonate)
        self._last_attempt_at: float | None = None
        self._stopped_reason: str | None = None

    @property
    def stopped_reason(self) -> str | None:
        return self._stopped_reason

    def set_request_budget(self, budget: PhysicalRequestBudget) -> None:
        self.request_budget = budget

    def clear_cookies(self) -> None:
        try:
            self._session.cookies.clear()
        except (AttributeError, KeyError):
            return

    def cookies_snapshot(self) -> dict[str, str]:
        try:
            return {str(k): str(v) for k, v in self._session.cookies.items()}
        except (AttributeError, TypeError):
            return {}

    def _before_attempt(self, url: str, *, retry_number: int) -> None:
        origin = validate_live_url(
            url,
            allowed_origins=self.allowed_origins,
            dns_resolver=self.dns_resolver,
        )
        if self.request_budget is not None:
            self.request_budget.assert_available(url_host=origin)

        now = self._monotonic()
        wait = 0.0
        if self._last_attempt_at is not None:
            elapsed = now - self._last_attempt_at
            wait = max(0.0, self.request_delay_seconds - elapsed)
        if retry_number > 0:
            wait += 0.5 * retry_number
        if wait > 0:
            self._sleep(wait)
        if self.request_budget is not None:
            self.request_budget.consume(url_host=origin)
        self._last_attempt_at = self._monotonic()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: Any = None,
        referer: str | None = None,
        allow_age_gate: bool = False,
    ) -> FetchResponse:
        if self._stopped_reason:
            raise LivePolicyError(
                LIVE_RATE_LIMITED,
                f"client stopped: {self._stopped_reason}",
                {"reason": self._stopped_reason},
            )

        validate_live_url(url, allowed_origins=self.allowed_origins)
        hdrs = dict(DEFAULT_HEADERS)
        if headers:
            hdrs.update(headers)
        if referer:
            validate_live_url(referer, allowed_origins=self.allowed_origins)
            hdrs["Referer"] = referer

        current_url = url
        current_method = method.upper()
        current_data = data
        redirect_count = 0
        retry_number = 0
        last_err: Exception | None = None

        while True:
            self._before_attempt(current_url, retry_number=retry_number)
            try:
                resp = self._session.request(
                    current_method,
                    current_url,
                    headers=hdrs,
                    data=current_data,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
            except Exception as exc:
                last_err = exc
                if retry_number < self.max_retries:
                    retry_number += 1
                    continue
                break

            final_url = str(resp.url or current_url)
            validate_live_url(
                final_url,
                allowed_origins=self.allowed_origins,
                dns_resolver=self.dns_resolver,
            )
            status = int(resp.status_code)
            response_headers = {k: str(v) for k, v in dict(resp.headers).items()}
            raw_content = getattr(resp, "content", None)
            if raw_content is None:
                text = str(getattr(resp, "text", "") or "")
                content = text.encode("utf-8")
            else:
                content = bytes(raw_content or b"")
                text = _decode_content(content, response_headers)

            if status in _REDIRECT_STATUS:
                location = _header(response_headers, "location")
                if not location:
                    raise ResourceIndexError(
                        LIVE_HTTP_ERROR,
                        f"redirect status {status} without Location header",
                        {"url_origin": normalized_origin(final_url), "status": status},
                    )
                if redirect_count >= self.max_redirects:
                    raise ResourceIndexError(
                        LIVE_HTTP_ERROR,
                        "maximum redirect count exceeded",
                        {"max_redirects": self.max_redirects},
                    )
                next_url = urljoin(final_url, location)
                validate_live_url(
                    next_url,
                    allowed_origins=self.allowed_origins,
                    dns_resolver=self.dns_resolver,
                )
                redirect_count += 1
                if status == 303 or (
                    status in {301, 302} and current_method not in {"GET", "HEAD"}
                ):
                    current_method = "GET"
                    current_data = None
                    hdrs.pop("Content-Type", None)
                current_url = next_url
                retry_number = 0
                continue

            stop = should_stop_on_status(status, text[:4000])
            if stop and stop.startswith("http_"):
                self._stopped_reason = stop
                raise LivePolicyError(
                    LIVE_RATE_LIMITED,
                    f"hard stop on status {status}",
                    {"url_origin": normalized_origin(final_url), "status": status},
                )
            if stop == "access_challenge":
                self._stopped_reason = stop
                raise LivePolicyError(
                    "ACCESS_CHALLENGE",
                    "access challenge page detected",
                    {"url_origin": normalized_origin(final_url)},
                )
            if stop == "age_gate" and not allow_age_gate:
                self._stopped_reason = stop
                raise LivePolicyError(
                    AGE_GATE_PAGE,
                    "age verification page detected after session bootstrap",
                    {"url_origin": normalized_origin(final_url)},
                )
            if status in _RETRYABLE_STATUS:
                last_err = ResourceIndexError(
                    LIVE_HTTP_ERROR,
                    f"retryable HTTP status {status}",
                    {"url_origin": normalized_origin(final_url), "status": status},
                )
                if retry_number < self.max_retries:
                    retry_number += 1
                    continue
                raise last_err
            if status < 200 or status >= 300:
                raise ResourceIndexError(
                    LIVE_HTTP_ERROR,
                    f"HTTP status {status}",
                    {"url_origin": normalized_origin(final_url), "status": status},
                )
            return FetchResponse(
                url=final_url,
                status_code=status,
                text=text,
                headers=response_headers,
                content=content,
            )

        raise ResourceIndexError(
            LIVE_HTTP_ERROR,
            f"request failed after retries: {last_err}",
            {"url_origin": normalized_origin(current_url)},
        )

    def get(self, url: str, **kwargs: Any) -> FetchResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> FetchResponse:
        return self.request("POST", url, **kwargs)
