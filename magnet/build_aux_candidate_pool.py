#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse

from aux_site_registry import AUXILIARY_SITES_PATH, normalize_origin


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def host_token_score(origin: str) -> int:
    host = (urlparse(origin).hostname or "").lower()
    score = 0
    if any(token in host for token in ("cili", "bt", "torrent", "kitty", "nyaa", "xunlei", "sow", "db")):
        score += 3
    if any(token in host for token in ("gov.cn", "beian", "yhdm", "pansou", "movie", "dytt")):
        score -= 3
    return score


def iter_candidate_records(site: Dict[str, Any]) -> List[Dict[str, Any]]:
    category = site.get("category", "")
    samples = site.get("real_candidate_samples") or []
    origins = site.get("real_candidate_origins") or []
    output: List[Dict[str, Any]] = []

    if samples:
        for item in samples:
            origin = normalize_origin(item.get("origin", ""))
            if not origin:
                continue
            score = int(item.get("score", 0))
            if score <= 0:
                score = 8 if category == "jump" else 6
            output.append(
                {
                    "origin": origin,
                    "name": item.get("title", ""),
                    "desc": item.get("description", ""),
                    "raw_score": score,
                }
            )

    sample_origins = {item["origin"] for item in output}
    for origin in origins:
        normalized = normalize_origin(origin)
        if not normalized or normalized in sample_origins:
            continue
        output.append(
            {
                "origin": normalized,
                "name": "",
                "desc": "",
                "raw_score": 8 if category == "jump" else 6,
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deduped candidate pool from auxiliary_sites.json")
    parser.add_argument("--in", dest="in_path", default=AUXILIARY_SITES_PATH)
    parser.add_argument("--out", dest="out_path", default=os.path.join(ROOT_DIR, "aux_candidate_pool.json"))
    parser.add_argument("--min-score", type=int, default=7)
    parser.add_argument("--min-support", type=int, default=1)
    args = parser.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    grouped: Dict[str, Dict[str, Any]] = {}
    supporting_sites = defaultdict(list)
    supporting_categories = defaultdict(set)

    for site in data.get("sites", []):
        site_origin = normalize_origin(site.get("origin", ""))
        category = site.get("category", "")
        brand = site.get("brand") or site.get("source_name") or ""
        reason = site.get("reason", "")
        for record in iter_candidate_records(site):
            origin = record["origin"]
            host_score = host_token_score(origin)
            combined_score = int(record["raw_score"]) + host_score
            if combined_score < args.min_score:
                continue
            existing = grouped.get(origin)
            payload = {
                "origin": origin,
                "name": record["name"],
                "desc": record["desc"],
                "reason": f"aux:{category}:{reason}",
                "brand": brand,
                "score": combined_score,
            }
            if existing is None or payload["score"] > int(existing.get("score", 0)):
                grouped[origin] = payload
            if site_origin and site_origin not in supporting_sites[origin]:
                supporting_sites[origin].append(site_origin)
            if category:
                supporting_categories[origin].add(category)

    candidates: List[Dict[str, Any]] = []
    for origin, item in grouped.items():
        support_count = len(supporting_sites[origin])
        if support_count < args.min_support:
            continue
        item["discovered_from"] = supporting_sites[origin]
        item["support_count"] = support_count
        item["categories"] = sorted(supporting_categories[origin])
        candidates.append(item)

    candidates.sort(key=lambda x: (-x["support_count"], -int(x["score"]), x["origin"]))

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_score": args.min_score,
        "min_support": args.min_support,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {args.out_path} candidates={len(candidates)}")


if __name__ == "__main__":
    main()
