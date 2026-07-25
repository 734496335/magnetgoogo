"""Validate the sources.json health and quality contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

VALID_STATUS = {"green", "yellow", "gray"}
VALID_STATUS_DETAIL = {
    "ok",
    "healed",
    "waf",
    "404",
    "expired",
    "unreachable",
    "parsing_failed",
}


def validate_sources(path: str | Path) -> tuple[int, list[str]]:
    source_path = Path(path)
    try:
        payload: dict[str, Any] = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return 0, [f"sources.json unreadable: {exc}"]

    rulesets = payload.get("rulesets")
    if not isinstance(rulesets, list):
        return 0, ["rulesets must be a list"]

    rules: list[dict[str, Any]] = []
    errors: list[str] = []
    for ruleset_index, ruleset in enumerate(rulesets):
        if not isinstance(ruleset, dict) or not isinstance(ruleset.get("rules"), list):
            errors.append(f"rulesets[{ruleset_index}].rules must be a list")
            continue
        rules.extend(rule for rule in ruleset["rules"] if isinstance(rule, dict))

    seen_ids: set[str] = set()
    for index, rule in enumerate(rules):
        rule_id = str(rule.get("id") or f"index:{index}")
        if rule_id in seen_ids:
            errors.append(f"{rule_id}: duplicate rule id")
        seen_ids.add(rule_id)

        health = rule.get("health")
        if not isinstance(health, dict):
            errors.append(f"{rule_id}: health must be an object")
        else:
            status = health.get("status")
            detail = health.get("status_detail")
            if status not in VALID_STATUS:
                errors.append(f"{rule_id}: invalid health.status={status!r}")
            if detail not in VALID_STATUS_DETAIL:
                errors.append(f"{rule_id}: invalid health.status_detail={detail!r}")

        quality = rule.get("quality")
        if not isinstance(quality, dict):
            errors.append(f"{rule_id}: quality must be an object")
        else:
            score = quality.get("score")
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 100:
                errors.append(f"{rule_id}: quality.score must be between 0 and 100")

    meta = payload.get("meta")
    declared = meta.get("total_rules") if isinstance(meta, dict) else None
    if declared != len(rules):
        errors.append(
            f"meta.total_rules mismatch: declared={declared!r} actual={len(rules)}"
        )
    return len(rules), errors


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    default_path = Path(__file__).resolve().parents[1] / "sources.json"
    path = Path(args[0]) if args else default_path
    count, errors = validate_sources(path)
    if errors:
        for error in errors:
            print(f"INVALID {error}")
        return 1
    print(f"rules={count}")
    print("ALL VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
