"""Deterministic online sampling for non-magnet source resources."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.pipeline.latest_crawl import _atomic_write_json


@dataclass(frozen=True)
class ResourceProbeResponse:
    status: int
    content_type: str
    prefix: bytes


Transport = Callable[[str, str], ResourceProbeResponse]


@dataclass(frozen=True)
class SourceResourceProbeResult:
    status: str
    source_id: str
    selected_count: int
    passed_count: int
    failed_count: int
    skipped_magnet_count: int
    report_path: str


def _load_feed(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceIndexError(CONFIG_ERROR, "failed to read resource probe feed", {"path": str(path)}) from exc
    if value.get("schema_version") != "movie-feed/1" or not isinstance(value.get("items"), list):
        raise ResourceIndexError(CONFIG_ERROR, "resource probe feed contract mismatch", {"path": str(path)})
    return value


def _quoted_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/%:@"),
            urllib.parse.quote(urllib.parse.unquote(parsed.query), safe="=&?/:@+"),
            "",
        )
    )


def _default_transport(url: str, resource_type: str) -> ResourceProbeResponse:
    target = _quoted_url(url)
    headers = {
        "User-Agent": "MagnetGoogo-Source-Probe/1.0",
        "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,text/html,*/*;q=0.8",
    }
    if target.startswith(("http://", "https://")):
        headers["Range"] = "bytes=0-4095"
    request = urllib.request.Request(target, headers=headers, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            status = int(getattr(response, "status", 200) or 200)
            content_type = str(response.headers.get("content-type") or "")
            prefix = response.read(4096)
            return ResourceProbeResponse(status, content_type, prefix)
    except urllib.error.HTTPError as exc:
        return ResourceProbeResponse(int(exc.code), str(exc.headers.get("content-type") or ""), exc.read(4096))


def probe_source_resources(
    *,
    feed_path: str | Path,
    output_path: str | Path,
    max_per_provider: int = 20,
    delay_seconds: float = 0.5,
    transport: Transport | None = None,
) -> SourceResourceProbeResult:
    if max_per_provider <= 0 or delay_seconds < 0:
        raise ResourceIndexError(CONFIG_ERROR, "resource probe limits are invalid", {})
    feed = _load_feed(Path(feed_path).expanduser().resolve())
    source_id = str(feed.get("source_id") or "")
    selected: list[dict[str, Any]] = []
    provider_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    skipped_magnets = 0
    for item in feed["items"]:
        if not isinstance(item, dict):
            continue
        for resource in item.get("resources") or []:
            if not isinstance(resource, dict):
                continue
            resource_type = str(resource.get("resource_type") or "").casefold()
            provider = str(resource.get("provider") or "").casefold()
            if resource_type == "magnet":
                skipped_magnets += 1
                continue
            key = (resource_type, provider)
            if provider_counts[key] >= max_per_provider:
                continue
            provider_counts[key] += 1
            selected.append(
                {
                    "movie_id": item.get("movie_id"),
                    "title": item.get("title"),
                    "resource_type": resource_type,
                    "provider": provider,
                    "url": resource.get("url") or resource.get("resource_url"),
                }
            )

    fetch = transport or _default_transport
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    for index, item in enumerate(selected):
        if index and delay_seconds:
            time.sleep(delay_seconds)
        url = str(item["url"] or "")
        try:
            response = fetch(url, str(item["resource_type"]))
            is_m3u8 = item["provider"] == "m3u8" or urllib.parse.urlsplit(url).path.casefold().endswith(".m3u8")
            if is_m3u8:
                ok = 200 <= response.status < 400 and response.prefix.lstrip().startswith(b"#EXTM3U")
            else:
                ok = 200 <= response.status < 400
            record = {
                **item,
                "status": response.status,
                "content_type": response.content_type,
                "prefix_size": len(response.prefix),
                "passed": ok,
            }
        except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
            ok = False
            record = {**item, "passed": False, "error": type(exc).__name__}
        results.append(record)
        if ok:
            passed += 1
        else:
            failed += 1

    summary_by_provider: dict[str, dict[str, int]] = {}
    for item in results:
        key = f"{item['resource_type']}:{item['provider']}"
        bucket = summary_by_provider.setdefault(key, {"selected": 0, "passed": 0, "failed": 0})
        bucket["selected"] += 1
        bucket["passed" if item["passed"] else "failed"] += 1
    report = {
        "schema_version": "source-resource-probe/1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "pass" if selected and failed == 0 else "fail",
        "source_id": source_id,
        "max_per_provider": max_per_provider,
        "selected_count": len(selected),
        "passed_count": passed,
        "failed_count": failed,
        "skipped_magnet_count": skipped_magnets,
        "providers": summary_by_provider,
        "results": results,
    }
    destination = Path(output_path).expanduser().resolve()
    _atomic_write_json(destination, report)
    return SourceResourceProbeResult(
        status=report["status"],
        source_id=source_id,
        selected_count=len(selected),
        passed_count=passed,
        failed_count=failed,
        skipped_magnet_count=skipped_magnets,
        report_path=str(destination),
    )
