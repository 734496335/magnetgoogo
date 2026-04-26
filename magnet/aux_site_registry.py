from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AUXILIARY_SITES_PATH = os.path.join(ROOT_DIR, "auxiliary_sites.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_origin(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return url.rstrip("/")
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return normalized


def _validate_category(category: str) -> str:
    if category not in {"jump", "navigation"}:
        raise ValueError(f"unsupported category: {category}")
    return category


def load_aux_sites(path: str = AUXILIARY_SITES_PATH) -> Dict[str, Any]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("generated_at", _now_iso())
        data.setdefault("sites", [])
        return data
    return {"generated_at": _now_iso(), "sites": []}


def save_aux_sites(data: Dict[str, Any], path: str = AUXILIARY_SITES_PATH) -> None:
    data["generated_at"] = _now_iso()
    data.setdefault("sites", [])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_aux_sites_by_category(category: str, path: str = AUXILIARY_SITES_PATH) -> List[Dict[str, Any]]:
    category = _validate_category(category)
    data = load_aux_sites(path)
    return [site for site in data.get("sites", []) if site.get("category") == category]


def upsert_aux_site(category: str, record: Dict[str, Any]) -> Dict[str, Any]:
    category = _validate_category(category)
    data = load_aux_sites()
    sites = data.setdefault("sites", [])
    origin = normalize_origin(record.get("origin", ""))
    record["origin"] = origin
    if not origin:
        raise ValueError("aux site origin is required")

    existing = None
    source_rule_id = record.get("source_rule_id", "")
    for site in sites:
        same_origin = normalize_origin(site.get("origin", "")) == origin
        same_rule = bool(source_rule_id and site.get("source_rule_id") == source_rule_id and site.get("category") == category)
        if same_origin or same_rule:
            existing = site
            break

    target = existing or {"origin": origin}
    for key, value in record.items():
        if value not in (None, "", [], {}):
            target[key] = value
    target["category"] = category
    target["last_checked_at"] = record.get("last_checked_at") or _now_iso()

    if existing is None:
        sites.append(target)

    data["generated_at"] = _now_iso()
    save_aux_sites(data)
    return target
