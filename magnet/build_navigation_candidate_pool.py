#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deduped candidate pool from navigation_real_candidates reports")
    parser.add_argument("--in", dest="in_path", default=os.path.join(ROOT_DIR, "navigation_real_candidates_round5.json"))
    parser.add_argument("--out", dest="out_path", default=os.path.join(ROOT_DIR, "navigation_candidate_pool.json"))
    parser.add_argument("--min-score", type=int, default=7)
    args = parser.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    grouped: Dict[str, Dict[str, Any]] = {}
    sources = defaultdict(list)
    for item in data.get("origins", []):
        origin = item.get("origin", "")
        if not origin or int(item.get("score", 0)) < args.min_score:
            continue
        current = grouped.get(origin)
        if current is None or int(item.get("score", 0)) > int(current.get("score", 0)):
            grouped[origin] = {
                "origin": origin,
                "name": item.get("title", ""),
                "score": int(item.get("score", 0)),
            }
        source_origin = item.get("source_origin", "")
        if source_origin and source_origin not in sources[origin]:
            sources[origin].append(source_origin)

    candidates: List[Dict[str, Any]] = []
    for origin, item in grouped.items():
        item["discovered_from"] = sources[origin]
        item["source_count"] = len(sources[origin])
        candidates.append(item)

    candidates.sort(key=lambda x: (-x["source_count"], -x["score"], x["origin"]))

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_score": args.min_score,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {args.out_path} candidates={len(candidates)}")


if __name__ == "__main__":
    main()
