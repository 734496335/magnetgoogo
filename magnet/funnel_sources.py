from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse


ALLOWED_STATUS = {"green", "yellow", "gray"}
ALLOWED_DETAIL = {"ok", "healed", "waf", "404", "expired", "unreachable", "parsing_failed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rule_id_for_origin(origin: str) -> str:
    return hashlib.md5(origin.encode("utf-8")).hexdigest()[:12]


def normalize_origin(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    p = urlparse(url)
    if not p.netloc:
        return ""
    scheme = p.scheme if p.scheme in ("http", "https") else "http"
    return f"{scheme}://{p.netloc}"


def ensure_health(health: Dict[str, Any]) -> Dict[str, Any]:
    st = str(health.get("status") or "yellow")
    sd = str(health.get("status_detail") or "parsing_failed")
    if st not in ALLOWED_STATUS:
        st = "yellow"
    if sd not in ALLOWED_DETAIL:
        sd = "parsing_failed"
    health["status"] = st
    health["status_detail"] = sd
    return health


def load_sources(path: str = "sources.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sources(data: Dict[str, Any], path: str = "sources.json") -> None:
    data["generated_at"] = _now_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_base_ruleset(data: Dict[str, Any]) -> Dict[str, Any]:
    for rs in data.get("rulesets", []):
        if rs.get("ruleset_id") == "base":
            return rs
    rs = {"ruleset_id": "base", "priority": 1, "max_sources_per_search": 10, "rules": []}
    data.setdefault("rulesets", []).append(rs)
    return rs


def upsert_rule_from_green_verdict(
    data: Dict[str, Any],
    origin: str,
    site_name: Optional[str],
    request_template: str,
    magnets_found: int,
    sample_title: str,
    note: str,
) -> Dict[str, Any]:
    origin = normalize_origin(origin)
    if not origin:
        raise ValueError("invalid origin")

    rs = find_base_ruleset(data)
    rules = rs.setdefault("rules", [])
    existing = None
    for r in rules:
        if normalize_origin(r.get("site", {}).get("origin", "")) == origin:
            existing = r
            break

    if not site_name:
        site_name = urlparse(origin).netloc

    rule = existing or {
        "id": rule_id_for_origin(origin),
        "site": {"name": site_name, "origin": origin, "countries": ["china"]},
        "capabilities": {"supports_search": True, "supports_detail": False},
        "search": {
            "request_template": request_template or "/search?q={query}",
            "timeout_ms": 8000,
            "retries": {"max_attempts": 2, "backoff_ms": 800},
            "requires_waf_bypass": False,
            "parse_metadata": {"selectors": {}},
        },
        "quality": {"score": 70, "tags": ["追新极客"]},
        "health": {"status": "green", "status_detail": "ok"},
    }

    rule["site"]["origin"] = origin
    rule["site"]["name"] = rule.get("site", {}).get("name") or site_name

    rule.setdefault("search", {})
    rule["search"]["request_template"] = request_template or rule["search"].get("request_template") or "/search?q={query}"

    rule.setdefault("health", {})
    rule["health"].update(
        {
            "status": "green",
            "status_detail": "ok",
            "last_checked_at": _now_iso(),
            "magnets_found": int(magnets_found or 0),
            "sample_title": (sample_title or "")[:80],
        }
    )
    if note:
        rule["health"]["note"] = note

    ensure_health(rule["health"])

    if existing is None:
        rules.append(rule)

    data.setdefault("meta", {})
    data["meta"]["total_rules"] = sum(len(r.get("rules", [])) for r in data.get("rulesets", []))
    return rule

