#!/usr/bin/env python3
"""Static source inventory and delivery-contract audit."""

from __future__ import annotations

import argparse
import collections
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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

VALID_HEALTH = {"green", "yellow", "gray"}
VALID_HEALTH_DETAIL = {"ok", "healed", "waf", "404", "expired", "unreachable", "parsing_failed"}
QUERY_TOKENS = ("{query}", "{query_b64}", "{query_b64url}")
TEMPLATE_TOKEN_RE = re.compile(r"\{[a-zA-Z0-9_]+\}")
SPECIALIZED_HANDLERS = {
    "1337x",
    "6v520",
    "btsow",
    "cilimo",
    "clkd",
    "javbus",
    "lulutang",
    "meijumi",
    "rarbggo",
    "rrjav",
    "ssbc",
    "thatcdn",
    "wuji",
    "yhg",
    "yts",
    "zhongzidi",
}


def _rules(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rules: list[dict[str, Any]] = []
    for ruleset in payload.get("rulesets") or []:
        if not isinstance(ruleset, dict):
            continue
        for rule in ruleset.get("rules") or []:
            if isinstance(rule, dict):
                rules.append(rule)
    return rules


def _finding(code: str, severity: str, rule: dict[str, Any] | None, detail: str) -> dict[str, Any]:
    site = (rule or {}).get("site") or {}
    return {
        "code": code,
        "severity": severity,
        "rule_id": (rule or {}).get("id", ""),
        "name": site.get("name", ""),
        "origin": site.get("origin", ""),
        "detail": detail,
    }


def audit_static(source_path: Path) -> dict[str, Any]:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    rules = _rules(payload)
    findings: list[dict[str, Any]] = []
    health_counts: collections.Counter[str] = collections.Counter()
    handler_counts: collections.Counter[str] = collections.Counter()
    ids: collections.defaultdict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    origins: collections.defaultdict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    pools: set[str] = set()
    green_pools: set[str] = set()
    executable = 0
    browser = 0

    if not rules:
        findings.append(_finding("NO_RULES", "error", None, "sources.json has no rules"))

    for rule in rules:
        rule_id = str(rule.get("id") or "").strip()
        site = rule.get("site") if isinstance(rule.get("site"), dict) else {}
        origin = str(site.get("origin") or "").strip().rstrip("/")
        search = rule.get("search") if isinstance(rule.get("search"), dict) else {}
        health = rule.get("health") if isinstance(rule.get("health"), dict) else {}
        quality = rule.get("quality") if isinstance(rule.get("quality"), dict) else {}
        capabilities = rule.get("capabilities") if isinstance(rule.get("capabilities"), dict) else {}
        status = str(health.get("status") or "")
        status_detail = str(health.get("status_detail") or "")
        handler = str(search.get("handler") or "generic")
        template = str(search.get("request_template") or "")
        pool_id = str(quality.get("pool_id") or "").strip()
        supports_search = capabilities.get("supports_search") is not False
        has_search = bool(template or search.get("handler"))

        health_counts[status] += 1
        handler_counts[handler] += 1
        if rule_id:
            ids[rule_id].append(rule)
        if origin:
            origins[origin.lower()].append(rule)
        if pool_id:
            pools.add(pool_id)
            if status == "green":
                green_pools.add(pool_id)
        if search.get("requires_browser") is True:
            browser += 1
        if supports_search and has_search:
            executable += 1

        if not rule_id:
            findings.append(_finding("MISSING_RULE_ID", "error", rule, "rule id is empty"))
        if not origin:
            findings.append(_finding("MISSING_ORIGIN", "error", rule, "site.origin is empty"))
        else:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                findings.append(_finding("INVALID_ORIGIN", "error", rule, origin))
        if status not in VALID_HEALTH:
            findings.append(_finding("INVALID_HEALTH", "error", rule, status))
        if status_detail not in VALID_HEALTH_DETAIL:
            findings.append(_finding("INVALID_HEALTH_DETAIL", "error", rule, status_detail))
        score = quality.get("score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 100:
            findings.append(_finding("INVALID_QUALITY_SCORE", "error", rule, repr(score)))
        if status == "green" and not pool_id:
            findings.append(_finding("GREEN_WITHOUT_POOL", "error", rule, "green rule has no quality.pool_id"))
        if status == "green" and not has_search:
            findings.append(_finding("GREEN_WITHOUT_SEARCH", "error", rule, "green rule has no request template or handler"))
        if supports_search and not has_search:
            findings.append(_finding("SEARCH_CAPABILITY_WITHOUT_EXECUTOR", "warning", rule, "supports_search but no search executor"))
        template_tokens = set(TEMPLATE_TOKEN_RE.findall(template))
        unsupported_tokens = sorted(template_tokens - set(QUERY_TOKENS))
        if unsupported_tokens:
            severity = "error" if status == "green" else "warning"
            findings.append(_finding("UNSUPPORTED_TEMPLATE_TOKEN", severity, rule, ",".join(unsupported_tokens)))
        if handler == "generic" and template and not any(token in template for token in QUERY_TOKENS):
            severity = "error" if status == "green" else "warning"
            findings.append(_finding("GENERIC_TEMPLATE_WITHOUT_QUERY", severity, rule, template))
        if handler not in {"generic", ""} and handler not in SPECIALIZED_HANDLERS:
            findings.append(_finding("UNKNOWN_SPECIALIZED_HANDLER", "warning", rule, handler))
        if handler == "generic" and template:
            selectors = ((search.get("parse_metadata") or {}).get("selectors") or {})
            if not isinstance(selectors, dict) or not str(selectors.get("title") or "").strip():
                findings.append(_finding("GENERIC_WITHOUT_TITLE_SELECTOR", "warning", rule, "generic rule has no title selector"))
            if not isinstance(selectors, dict) or not str(selectors.get("magnet") or "").strip():
                findings.append(_finding("GENERIC_WITHOUT_MAGNET_SELECTOR", "warning", rule, "generic rule has no magnet selector"))

    for rule_id, duplicates in ids.items():
        if len(duplicates) > 1:
            findings.append(_finding("DUPLICATE_RULE_ID", "error", duplicates[0], f"count={len(duplicates)} id={rule_id}"))
    for origin, duplicates in origins.items():
        if len(duplicates) > 1:
            signatures = {
                (
                    str((item.get("search") or {}).get("handler") or "generic"),
                    str((item.get("search") or {}).get("request_template") or ""),
                )
                for item in duplicates
            }
            pool_ids = {
                str((item.get("quality") or {}).get("pool_id") or "")
                for item in duplicates
            }
            active = [item for item in duplicates if (item.get("health") or {}).get("status") == "green"]
            severity = "error" if len(active) > 1 and len(pool_ids) > 1 else "warning"
            findings.append(_finding(
                "DUPLICATE_ORIGIN",
                severity,
                duplicates[0],
                f"count={len(duplicates)} signatures={len(signatures)} pools={sorted(pool_ids)} origin={origin}",
            ))

    errors = [item for item in findings if item["severity"] == "error"]
    warnings = [item for item in findings if item["severity"] == "warning"]
    return {
        "schema_version": payload.get("schema_version"),
        "allRules": len(rules),
        "greenRules": health_counts.get("green", 0),
        "yellowRules": health_counts.get("yellow", 0),
        "grayRules": health_counts.get("gray", 0),
        "allPools": len(pools),
        "greenPools": len(green_pools),
        "executableRules": executable,
        "browserRules": browser,
        "handlerCounts": dict(sorted(handler_counts.items())),
        "hardFindingCount": len(errors),
        "warningCount": len(warnings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit sources.json delivery contract")
    parser.add_argument("source", nargs="?", type=Path, default=Path("sources.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_static(args.source)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    log.info(rendered)
    return 2 if result["hardFindingCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
