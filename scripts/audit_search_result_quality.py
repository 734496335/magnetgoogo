#!/usr/bin/env python3
"""Audit K30S per-source search reports for normalized-result quality defects."""

from __future__ import annotations

import argparse
import collections
import json
import logging
import math
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler("magnet/run.log", encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

PURE_HASH_RE = re.compile(r"^(?:[a-f0-9]{32,64}|[a-z2-7]{32})$", re.I)
HASH_LABEL_RE = re.compile(
    r"^(?:hash|btih|info[-_\s]?hash)\s*[:：=]?\s*(?:[a-f0-9]{8,64}|[a-z2-7]{16,32})(?:\.{3}|…)?$",
    re.I,
)
BTIH_RE = re.compile(r"^(?:(?:\(brute\)\s*)?magnet:\?\S*|urn:btih:|btih:)\s*[a-z0-9]+", re.I)
URL_RE = re.compile(r"^(?:https?|ftp)://", re.I)
HTML_RE = re.compile(r"<[^>]+>")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
CANONICAL_SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?) (B|KB|MB|GB|TB)$")
CANONICAL_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
FULL_HASH_RE = re.compile(r"^[a-f0-9]{40}$", re.I)
TRUNCATED_HASH_RE = re.compile(r"^[a-f0-9]{8,39}$", re.I)
GENERIC_TITLES = {
    "download", "download torrent", "torrent", "magnet", "magnet link", "link",
    "detail", "details", "view", "more", "unknown", "unknown title", "untitled",
    "no title", "下载", "磁力", "磁力链接", "种子", "详情", "查看", "更多", "未知标题", "无标题",
}
UNIT_BYTES = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
    "TB": 1024 ** 4,
}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    query: str = ""
    source: str = ""
    origin: str = ""
    hash: str = ""
    title: str = ""
    detail: str = ""


def _finding(code: str, severity: str, *, query: str = "", source: dict[str, Any] | None = None,
             item: dict[str, Any] | None = None, detail: str = "") -> Finding:
    source = source or {}
    item = item or {}
    return Finding(
        code=code,
        severity=severity,
        query=query,
        source=str(source.get("name") or ""),
        origin=str(source.get("origin") or ""),
        hash=str(item.get("hash") or ""),
        title=str(item.get("title") or "")[:500],
        detail=detail,
    )


def _normalize_title(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n\"'`")


def _is_hash_title(title: str) -> bool:
    return bool(PURE_HASH_RE.fullmatch(title) or HASH_LABEL_RE.fullmatch(title) or BTIH_RE.match(title))


def _size_bytes(value: Any) -> int:
    match = CANONICAL_SIZE_RE.fullmatch(str(value or "").strip())
    if not match:
        return 0
    numeric = float(match.group(1))
    if not math.isfinite(numeric) or numeric <= 0:
        return 0
    return int(numeric * UNIT_BYTES[match.group(2)])


def _canonical_date(value: Any) -> date | None:
    match = CANONICAL_DATE_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def audit_item(query: str, source: dict[str, Any], item: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    title = _normalize_title(item.get("title"))
    hash_value = str(item.get("hash") or "").lower().strip()
    size = str(item.get("size") or "").strip()
    date_value = str(item.get("date") or "").strip()
    file_count = item.get("fileCount")
    relevance = item.get("relevance")

    if not title:
        findings.append(_finding("EMPTY_TITLE", "error", query=query, source=source, item=item))
    else:
        lower = title.casefold()
        if _is_hash_title(title):
            findings.append(_finding("HASH_PLACEHOLDER_TITLE", "error", query=query, source=source, item=item))
        if URL_RE.match(title):
            findings.append(_finding("URL_AS_TITLE", "error", query=query, source=source, item=item))
        if HTML_RE.search(title):
            findings.append(_finding("HTML_IN_TITLE", "error", query=query, source=source, item=item))
        if CONTROL_RE.search(title):
            findings.append(_finding("CONTROL_CHAR_IN_TITLE", "error", query=query, source=source, item=item))
        if "\ufffd" in title:
            findings.append(_finding("MOJIBAKE_REPLACEMENT_CHAR", "error", query=query, source=source, item=item))
        if lower in GENERIC_TITLES:
            findings.append(_finding("GENERIC_TITLE", "error", query=query, source=source, item=item))
        if len(title) > 500:
            findings.append(_finding("EXCESSIVE_TITLE_LENGTH", "error", query=query, source=source, item=item, detail=f"length={len(title)}"))
        elif len(title) > 240:
            findings.append(_finding("LONG_TITLE", "warning", query=query, source=source, item=item, detail=f"length={len(title)}"))

    if not hash_value:
        findings.append(_finding("EMPTY_INFO_HASH", "error", query=query, source=source, item=item))
    elif FULL_HASH_RE.fullmatch(hash_value):
        pass
    elif TRUNCATED_HASH_RE.fullmatch(hash_value):
        findings.append(_finding("TRUNCATED_DEBUG_HASH", "warning", query=query, source=source, item=item, detail=f"length={len(hash_value)}"))
    else:
        findings.append(_finding("INVALID_INFO_HASH", "error", query=query, source=source, item=item, detail=f"length={len(hash_value)}"))

    if size:
        bytes_value = _size_bytes(size)
        if bytes_value <= 0:
            findings.append(_finding("INVALID_SIZE_LABEL", "error", query=query, source=source, item=item, detail=size))
        elif bytes_value < 1024:
            findings.append(_finding("SUSPICIOUS_SUB_KIB_SIZE", "error", query=query, source=source, item=item, detail=size))
        elif bytes_value > 1024 ** 5:
            findings.append(_finding("IMPOSSIBLE_PETABYTE_SIZE", "error", query=query, source=source, item=item, detail=size))
        elif bytes_value > 64 * 1024 ** 4:
            findings.append(_finding("EXTREME_SIZE", "warning", query=query, source=source, item=item, detail=size))

    if date_value:
        parsed_date = _canonical_date(date_value)
        if parsed_date is None:
            findings.append(_finding("INVALID_DATE_LABEL", "error", query=query, source=source, item=item, detail=date_value))
        elif parsed_date > date.today() + timedelta(days=2):
            findings.append(_finding("FUTURE_DATE", "error", query=query, source=source, item=item, detail=date_value))
        elif parsed_date.year < 1970:
            findings.append(_finding("PRE_EPOCH_DATE", "error", query=query, source=source, item=item, detail=date_value))

    if file_count is not None:
        if isinstance(file_count, bool) or not isinstance(file_count, int) or file_count <= 0:
            findings.append(_finding("INVALID_FILE_COUNT", "error", query=query, source=source, item=item, detail=repr(file_count)))
        elif file_count > 1_000_000:
            findings.append(_finding("EXTREME_FILE_COUNT", "error", query=query, source=source, item=item, detail=str(file_count)))

    if not isinstance(relevance, int) or relevance < -30 or relevance > 100:
        findings.append(_finding("INVALID_RELEVANCE", "error", query=query, source=source, item=item, detail=repr(relevance)))

    return findings


def _group_items(reports: Iterable[dict[str, Any]]) -> dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]]:
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = collections.defaultdict(list)
    for report in reports:
        query = str(report.get("query") or "")
        for source in report.get("sourceResults") or []:
            if not isinstance(source, dict):
                continue
            for item in source.get("items") or []:
                if not isinstance(item, dict):
                    continue
                hash_value = str(item.get("hash") or "").lower().strip()
                if FULL_HASH_RE.fullmatch(hash_value):
                    grouped[(query, hash_value)].append((source, item))
    return grouped


def audit_cross_source(reports: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    for (query, hash_value), rows in _group_items(reports).items():
        origins = {str(source.get("origin") or source.get("name") or "") for source, _ in rows}
        if len(origins) < 2:
            continue

        sizes = [(source, item, _size_bytes(item.get("size"))) for source, item in rows]
        sizes = [entry for entry in sizes if entry[2] > 0]
        if len({entry[0].get("origin") or entry[0].get("name") for entry in sizes}) >= 2:
            low = min(sizes, key=lambda entry: entry[2]) if sizes else None
            high = max(sizes, key=lambda entry: entry[2]) if sizes else None
            if low and high:
                ratio = high[2] / low[2]
                if ratio >= 4:
                    findings.append(_finding(
                        "CROSS_SOURCE_SIZE_CONFLICT",
                        "error",
                        query=query,
                        source=high[0],
                        item=high[1],
                        detail=f"hash={hash_value} low={low[1].get('size')}@{low[0].get('name')} high={high[1].get('size')}@{high[0].get('name')} ratio={ratio:.2f}",
                    ))
                elif ratio > 1.2:
                    findings.append(_finding(
                        "CROSS_SOURCE_SIZE_DRIFT",
                        "warning",
                        query=query,
                        source=high[0],
                        item=high[1],
                        detail=f"hash={hash_value} low={low[1].get('size')} high={high[1].get('size')} ratio={ratio:.2f}",
                    ))

        counts = [(source, item, item.get("fileCount")) for source, item in rows if isinstance(item.get("fileCount"), int) and item.get("fileCount") > 0]
        distinct_counts = {entry[2] for entry in counts}
        if len(distinct_counts) > 1:
            low = min(counts, key=lambda entry: entry[2])
            high = max(counts, key=lambda entry: entry[2])
            ratio = high[2] / low[2]
            severity = "error" if ratio >= 2 and high[2] - low[2] >= 5 else "warning"
            findings.append(_finding(
                "CROSS_SOURCE_FILE_COUNT_CONFLICT",
                severity,
                query=query,
                source=high[0],
                item=high[1],
                detail=f"hash={hash_value} low={low[2]}@{low[0].get('name')} high={high[2]}@{high[0].get('name')}",
            ))
    return findings


def audit_payload(payload: dict[str, Any], require_complete: bool = False) -> dict[str, Any]:
    raw_reports = payload.get("reports") or {}
    if isinstance(raw_reports, dict):
        reports = [value for value in raw_reports.values() if isinstance(value, dict)]
    elif isinstance(raw_reports, list):
        reports = [value for value in raw_reports if isinstance(value, dict)]
    else:
        reports = []

    findings: list[Finding] = []
    source_attempts: collections.Counter[str] = collections.Counter()
    source_successes: collections.Counter[str] = collections.Counter()
    source_item_counts: collections.Counter[str] = collections.Counter()

    if not reports:
        findings.append(Finding("NO_REPORTS", "error", detail="payload has no search reports"))

    for report in reports:
        query = str(report.get("query") or "")
        sources = report.get("sourceResults") or []
        if not isinstance(sources, list):
            findings.append(Finding("INVALID_SOURCE_RESULTS", "error", query=query))
            continue
        inventory = report.get("inventory") or {}
        attempted = int(report.get("attemptedHostCount") or len(sources))
        loaded = int(inventory.get("loadedHostCount") or 0)
        if attempted != len(sources):
            findings.append(Finding("ATTEMPTED_HOST_COUNT_MISMATCH", "error", query=query, detail=f"attempted={attempted} rows={len(sources)}"))
        if require_complete and inventory.get("benchmarkMode") is True and loaded > 0 and attempted != loaded:
            findings.append(Finding("INCOMPLETE_BENCHMARK_HOST_COVERAGE", "error", query=query, detail=f"attempted={attempted} loaded={loaded}"))

        for source in sources:
            if not isinstance(source, dict):
                findings.append(Finding("INVALID_SOURCE_RESULT", "error", query=query))
                continue
            name = str(source.get("name") or "")
            origin = str(source.get("origin") or "")
            identity = f"{name}|{origin}"
            source_attempts[identity] += 1
            status = source.get("status")
            items = source.get("items") or []
            if not isinstance(items, list):
                findings.append(_finding("INVALID_ITEMS_ARRAY", "error", query=query, source=source))
                continue
            source_item_counts[identity] += len(items)
            if status == "ok":
                source_successes[identity] += 1
                if not items:
                    findings.append(_finding("OK_SOURCE_WITHOUT_ITEM_LOGS", "error", query=query, source=source))
            if status in {"failed", "skipped"} and items:
                findings.append(_finding("NON_OK_SOURCE_WITH_ITEMS", "error", query=query, source=source, detail=f"status={status}"))
            if status == "empty" and items:
                relevant_count = source.get("relevantResultCount")
                if isinstance(relevant_count, int) and relevant_count > 0:
                    findings.append(_finding(
                        "EMPTY_SOURCE_WITH_RELEVANT_ITEMS",
                        "error",
                        query=query,
                        source=source,
                        detail=f"relevant={relevant_count} items={len(items)}",
                    ))
            unique_count = source.get("uniqueResultCount")
            if isinstance(unique_count, int) and unique_count != len(items):
                findings.append(_finding("UNIQUE_COUNT_ITEM_LOG_MISMATCH", "error", query=query, source=source, detail=f"unique={unique_count} items={len(items)}"))
            relevant_count = source.get("relevantResultCount")
            if status == "ok" and items and isinstance(relevant_count, int) and relevant_count == 0:
                findings.append(_finding(
                    "ZERO_RELEVANT_SOURCE_RESULTS",
                    "error",
                    query=query,
                    source=source,
                    detail=f"items={len(items)} precision={source.get('relevancePrecision')}",
                ))
            precision = source.get("relevancePrecision")
            if status == "ok" and items and isinstance(precision, (int, float)) and 0 < precision < 0.2:
                findings.append(_finding(
                    "VERY_LOW_SOURCE_RELEVANCE_PRECISION",
                    "warning",
                    query=query,
                    source=source,
                    detail=f"items={len(items)} precision={precision:.3f}",
                ))

            per_hash: collections.defaultdict[str, list[dict[str, Any]]] = collections.defaultdict(list)
            for item in items:
                if not isinstance(item, dict):
                    findings.append(_finding("INVALID_ITEM", "error", query=query, source=source))
                    continue
                findings.extend(audit_item(query, source, item))
                hash_value = str(item.get("hash") or "").lower().strip()
                if hash_value:
                    per_hash[hash_value].append(item)
            for hash_value, duplicates in per_hash.items():
                if len(duplicates) <= 1:
                    continue
                titles = {_normalize_title(item.get("title")) for item in duplicates}
                sizes = {str(item.get("size") or "") for item in duplicates if item.get("size")}
                counts = {item.get("fileCount") for item in duplicates if item.get("fileCount") is not None}
                if len(sizes) > 1 or len(counts) > 1:
                    findings.append(_finding(
                        "SAME_SOURCE_DUPLICATE_HASH_METADATA_CONFLICT",
                        "error",
                        query=query,
                        source=source,
                        item=duplicates[0],
                        detail=f"hash={hash_value} titles={len(titles)} sizes={sorted(sizes)} fileCounts={sorted(counts)}",
                    ))
                elif len(titles) > 1:
                    findings.append(_finding(
                        "SAME_SOURCE_DUPLICATE_HASH_TITLE_VARIANTS",
                        "warning",
                        query=query,
                        source=source,
                        item=duplicates[0],
                        detail=f"hash={hash_value} titles={len(titles)} count={len(duplicates)}",
                    ))
                else:
                    findings.append(_finding(
                        "SAME_SOURCE_DUPLICATE_HASH",
                        "warning",
                        query=query,
                        source=source,
                        item=duplicates[0],
                        detail=f"hash={hash_value} count={len(duplicates)}",
                    ))

    findings.extend(audit_cross_source(reports))
    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warning"]
    by_code = collections.Counter(finding.code for finding in findings)
    return {
        "status": "PASS" if not errors else "FAIL",
        "reportCount": len(reports),
        "uniqueAttemptedSources": len(source_attempts),
        "uniqueSuccessfulSources": len(source_successes),
        "sourcesWithItems": sum(1 for count in source_item_counts.values() if count > 0),
        "hardFindingCount": len(errors),
        "warningCount": len(warnings),
        "findingCounts": dict(sorted(by_code.items())),
        "sourceAttempts": dict(sorted(source_attempts.items())),
        "sourceSuccesses": dict(sorted(source_successes.items())),
        "findings": [asdict(finding) for finding in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit per-source K30S search result quality")
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.report.read_text(encoding="utf-8"))
    result = audit_payload(payload, require_complete=args.require_complete)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    log.info(rendered)
    return 2 if result["hardFindingCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
