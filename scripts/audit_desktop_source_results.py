#!/usr/bin/env python3
"""Desktop result-level audit for green sources that do not require App WebView.

This is complementary evidence only. The Android/K30S exhaustive benchmark
remains authoritative for App-only handlers, cookies and browser verification.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import logging
import math
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_search_result_quality import audit_payload  # noqa: E402
from magnet.crawler_v3.tiers.base import SearchResult, TierError  # noqa: E402
from magnet.crawler_v3.tiers.tier0_http import Tier0Http  # noqa: E402
from magnet.crawler_v3.tiers.tier2_handler import HANDLER_REGISTRY, Tier2Handler  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(ROOT / "magnet" / "run.log", encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

SIZE_RE = re.compile(
    r"(?<![a-z0-9])([0-9]+(?:[.,][0-9]+)?)\s*(bytes?|[kmgt]i?b|[kmgt]字节|[kmgt]字節|字节|字節)(?![a-z0-9])",
    re.I,
)
UNIT_POWER = {
    "b": 0, "byte": 0, "bytes": 0, "字节": 0, "字節": 0,
    "kb": 1, "kib": 1, "k字节": 1, "k字節": 1,
    "mb": 2, "mib": 2, "m字节": 2, "m字節": 2,
    "gb": 3, "gib": 3, "g字节": 3, "g字節": 3,
    "tb": 4, "tib": 4, "t字节": 4, "t字節": 4,
}
BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
PLACEHOLDER_TITLE_RE = re.compile(
    r"^(?:(?:\(brute\)\s*)?magnet:\?\S*|(?:hash|btih|info[-_\s]?hash)\s*[:：=]?\s*[a-z0-9.….]+|[a-f0-9]{32,64}|[a-z2-7]{32})$",
    re.I,
)
GENERIC_TITLE_RE = re.compile(
    r"^(?:unknown(?:\s+title)?|untitled|no\s+title|download(?:\s+torrent)?|torrent|magnet(?:\s+link)?|details?|view(?:\s+more)?|click(?:\s+here)?|未知标题|无标题|下载|下载种子|种子|磁力|磁力链接|详情|查看|查看更多|点击查看)$",
    re.I,
)


def load_green_sources(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        rule
        for ruleset in payload.get("rulesets") or []
        for rule in ruleset.get("rules") or []
        if (rule.get("health") or {}).get("status") == "green"
    ]


def canonical_hash(magnet: str) -> str:
    match = re.search(r"(?:urn:)?btih:([0-9a-f]{40})(?=$|[^0-9a-f])", magnet or "", re.I)
    if match:
        return match.group(1).lower()
    match = re.search(r"(?:urn:)?btih:([a-z2-7]{32})(?=$|[^a-z2-7])", magnet or "", re.I)
    if not match:
        return ""
    bits = ""
    for character in match.group(1).upper():
        index = BASE32_ALPHABET.find(character)
        if index < 0:
            return ""
        bits += f"{index:05b}"
    return "".join(f"{int(bits[offset:offset + 4], 2):x}" for offset in range(0, 160, 4))


def format_bytes(value: float) -> str:
    if not math.isfinite(value) or value < 1024:
        return ""
    units = ("B", "KB", "MB", "GB", "TB")
    unit = 0
    while value >= 1024 and unit < len(units) - 1:
        value /= 1024
        unit += 1
    decimals = 0 if value >= 100 else 1 if value >= 10 else 2
    rendered = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return f"{rendered} {units[unit]}"


def normalize_size(raw: str | None) -> str:
    best = 0.0
    for match in SIZE_RE.finditer(raw or ""):
        numeric = float(match.group(1).replace(",", "."))
        power = UNIT_POWER.get(match.group(2).lower())
        if power is None:
            continue
        best = max(best, numeric * (1024 ** power))
    return format_bytes(best)


def relevance(title: str, query: str) -> int:
    normalized_title = re.sub(r"\s+", " ", title.casefold())
    normalized_query = re.sub(r"\s+", " ", query.casefold()).strip()
    if normalized_query and normalized_query in normalized_title:
        return 100
    tokens = [token for token in re.split(r"[^0-9a-z\u4e00-\u9fff]+", normalized_query) if token]
    if not tokens:
        return 0
    matched = sum(token in normalized_title for token in tokens)
    return int(100 * matched / len(tokens))


def displayable_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(title or "")).strip()
    return bool(
        normalized
        and len(normalized) <= 500
        and "\ufffd" not in normalized
        and not PLACEHOLDER_TITLE_RE.fullmatch(normalized)
        and not GENERIC_TITLE_RE.fullmatch(normalized)
        and not re.match(r"^(?:https?|ftp)://", normalized, re.I)
    )


def result_item(value: SearchResult, query: str) -> dict[str, Any]:
    extra = value.extra or {}
    file_count = extra.get("file_count") or extra.get("fileCount")
    if isinstance(file_count, str) and file_count.isdigit():
        file_count = int(file_count)
    if not isinstance(file_count, int):
        file_count = None
    return {
        "title": value.title or "",
        "hash": canonical_hash(value.magnet or ""),
        "size": normalize_size(value.size),
        "date": value.date or "",
        "fileCount": file_count,
        "relevance": relevance(value.title or "", query),
    }


def execution_kind(source: dict[str, Any]) -> tuple[str, str]:
    search = source.get("search") or {}
    platform = (source.get("tier_override") or {}).get("platform")
    handler = search.get("handler") or ""
    if platform in HANDLER_REGISTRY:
        return "tier2", platform
    if search.get("requires_browser"):
        return "skip", "browser_required"
    if handler:
        return "skip", f"app_handler:{handler}"
    return "tier0", "http"


def execute_source(source: dict[str, Any], query: str, limit: int) -> dict[str, Any]:
    started = time.monotonic()
    kind, reason = execution_kind(source)
    site = source.get("site") or {}
    base = {
        "ruleId": source.get("id") or "",
        "name": site.get("name") or "",
        "origin": site.get("origin") or "",
        "poolId": (source.get("quality") or {}).get("pool_id") or "",
        "executor": kind,
        "executorDetail": reason,
        "requiresWaf": bool((source.get("search") or {}).get("requires_waf")),
        "requiresBrowser": bool((source.get("search") or {}).get("requires_browser")),
        "qualityScore": (source.get("quality") or {}).get("score") or 0,
    }
    if kind == "skip":
        return {**base, "status": "skipped", "durationMs": 0, "resultCount": 0,
                "uniqueResultCount": 0, "relevantResultCount": 0, "relevancePrecision": 0,
                "items": [], "error": reason}
    try:
        values = Tier2Handler().search(source, query, limit=limit) if kind == "tier2" else Tier0Http().search(source, query, limit=limit)
        raw_sub_kib_sizes = sum(
            0 < max(
                (float(match.group(1).replace(",", ".")) * (1024 ** UNIT_POWER.get(match.group(2).lower(), 0))
                 for match in SIZE_RE.finditer(value.size or "")),
                default=0,
            ) < 1024
            for value in values
        )
        raw_rejected_titles = sum(not displayable_title(value.title or "") for value in values)
        raw_items = [result_item(value, query) for value in values if displayable_title(value.title or "")]
        deduped: dict[str, dict[str, Any]] = {}
        unresolved: list[dict[str, Any]] = []
        duplicate_hash_rows = 0
        for item in raw_items:
            hash_value = item["hash"]
            if not hash_value:
                unresolved.append(item)
                continue
            existing = deduped.get(hash_value)
            if existing is None:
                deduped[hash_value] = item
                continue
            duplicate_hash_rows += 1
            existing_richness = (
                existing["relevance"],
                bool(existing["size"]),
                bool(existing["date"]),
                bool(existing["fileCount"]),
                len(existing["title"]),
            )
            candidate_richness = (
                item["relevance"],
                bool(item["size"]),
                bool(item["date"]),
                bool(item["fileCount"]),
                len(item["title"]),
            )
            if candidate_richness > existing_richness:
                deduped[hash_value] = item
        items = [*deduped.values(), *unresolved]
        relevant_count = sum(item["relevance"] >= 30 for item in items)
        return {
            **base,
            "status": "ok" if relevant_count > 0 else "empty",
            "durationMs": int((time.monotonic() - started) * 1000),
            "resultCount": len(items),
            "uniqueResultCount": len(items),
            "relevantResultCount": relevant_count,
            "relevancePrecision": relevant_count / len(items) if items else 0,
            "rawResultCount": len(raw_items),
            "rawDuplicateHashRows": duplicate_hash_rows,
            "rawRejectedSubKibSizes": raw_sub_kib_sizes,
            "rawRejectedPlaceholderTitles": raw_rejected_titles,
            "items": items,
            "error": "",
        }
    except (TierError, Exception) as error:
        return {
            **base,
            "status": "failed",
            "durationMs": int((time.monotonic() - started) * 1000),
            "resultCount": 0,
            "uniqueResultCount": 0,
            "relevantResultCount": 0,
            "relevancePrecision": 0,
            "items": [],
            "error": str(error)[:500],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Desktop per-source result audit")
    parser.add_argument("--sources", type=Path, default=ROOT / "sources.json")
    parser.add_argument("--query", required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sources = load_green_sources(args.sources)
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(execute_source, source, args.query, args.limit): source for source in sources}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            log.info("[%d/%d] %s %s n=%d %s", index, len(sources), row["status"], row["name"], len(row["items"]), row["error"][:100])

    report = {
        "query": args.query,
        "completed": True,
        "attemptedHostCount": len(rows),
        "inventory": {
            "benchmarkMode": False,
            "loadedHostCount": len(sources),
            "loadedPoolCount": len({row["poolId"] for row in rows if row["poolId"]}),
        },
        "sourceResults": rows,
    }
    quality = audit_payload({"reports": {args.query: report}}, require_complete=False)
    payload = {
        "schema_version": "desktop-source-result-audit/1",
        "query": args.query,
        "sourceCount": len(sources),
        "okCount": sum(row["status"] == "ok" for row in rows),
        "failedCount": sum(row["status"] == "failed" for row in rows),
        "skippedCount": sum(row["status"] == "skipped" for row in rows),
        "itemCount": sum(len(row["items"]) for row in rows),
        "report": report,
        "quality": quality,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("query", "sourceCount", "okCount", "failedCount", "skippedCount", "itemCount")}, ensure_ascii=False, indent=2))
    print(json.dumps({key: quality[key] for key in ("status", "hardFindingCount", "warningCount", "findingCounts")}, ensure_ascii=False, indent=2))
    return 2 if quality["hardFindingCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
