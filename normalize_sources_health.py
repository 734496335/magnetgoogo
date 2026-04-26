#!/usr/bin/env python3
"""
Normalize sources.json health enums to Project Nebula contract.

Contract:
- health.status: green|yellow|gray
- health.status_detail: ok|healed|waf|404|expired|unreachable|parsing_failed

This script maps legacy/extended values back to the contract and preserves the
original values in health.note (non-lossy for audit).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Dict, Tuple


ALLOWED_STATUS = {"green", "yellow", "gray"}
ALLOWED_DETAIL = {"ok", "healed", "waf", "404", "expired", "unreachable", "parsing_failed"}


DETAIL_MAP = {
    # legacy "verified" is equivalent to ok
    "verified": "ok",
    # old/extended classifications -> closest contract bucket
    "dead": "expired",
    "parked": "expired",
    "empty_tiny_page": "expired",
    "blocked_or_empty": "unreachable",
    "search_dead_404": "404",
    "navigation_site_not_search_engine": "parsing_failed",
    "redirect_junk_site": "parsing_failed",
    "blank_page_confirmed_dead": "expired",
    "no_magnet_keywords_confirmed": "parsing_failed",
    "no_magnet_content_playwright_verified": "parsing_failed",
    "has_keywords_needs_browser": "parsing_failed",
    "has_keywords_needs_browser_v2": "parsing_failed",
    "no_keywords_browser": "parsing_failed",
    "has_keywords_needs_browser_or_click": "parsing_failed",
}


def normalize_detail(detail: str) -> Tuple[str, str | None]:
    if detail in ALLOWED_DETAIL:
        return detail, None
    mapped = DETAIL_MAP.get(detail)
    if mapped in ALLOWED_DETAIL:
        return mapped, f"legacy status_detail={detail}"
    return "parsing_failed", f"legacy status_detail={detail}"


def normalize_status(status: str, detail: str) -> Tuple[str, str | None]:
    if status in ALLOWED_STATUS:
        return status, None
    # Historic "red" is not allowed; map to gray when it's a hard failure, else yellow.
    if status == "red":
        if detail in ("unreachable",):
            return "gray", "legacy status=red"
        if detail in ("404", "expired"):
            return "gray", "legacy status=red"
        return "yellow", "legacy status=red"
    # Unknown -> conservative gray
    return "gray", f"legacy status={status}"


def merge_note(existing: str | None, extra: str) -> str:
    if not extra:
        return existing or ""
    if not existing:
        return extra
    if extra in existing:
        return existing
    return f"{existing}; {extra}"


def normalize_rule(rule: Dict[str, Any]) -> bool:
    health = rule.get("health") or {}
    changed = False

    orig_status = str(health.get("status") or "")
    orig_detail = str(health.get("status_detail") or "")

    detail, detail_note = normalize_detail(orig_detail)
    status, status_note = normalize_status(orig_status, detail)

    if health.get("status_detail") != detail:
        health["status_detail"] = detail
        changed = True
    if health.get("status") != status:
        health["status"] = status
        changed = True

    note = health.get("note")
    if detail_note:
        note = merge_note(note, detail_note)
    if status_note:
        note = merge_note(note, status_note)
    if note and note != health.get("note"):
        health["note"] = note
        changed = True

    rule["health"] = health
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", default="sources.json")
    parser.add_argument("--out", dest="out_path", default="sources.json")
    args = parser.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed_rules = 0
    total = 0
    for rs in data.get("rulesets", []):
        for r in rs.get("rules", []):
            total += 1
            if normalize_rule(r):
                changed_rules += 1

    data["generated_at"] = datetime.now(timezone.utc).isoformat()

    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Normalized rules: {changed_rules}/{total}")


if __name__ == "__main__":
    main()

