#!/usr/bin/env python3
"""
Summarize funnel_report.json for fast iteration.

Outputs:
- prints high-signal summary to stdout
- writes funnel_summary.json with aggregates
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_summary(rep: Dict[str, Any], top: int) -> Dict[str, Any]:
    green: List[Dict[str, Any]] = rep.get("green", [])
    yellow: List[Dict[str, Any]] = rep.get("yellow", [])
    gray: List[Dict[str, Any]] = rep.get("gray", [])
    debug: Dict[str, Any] = rep.get("debug", {})

    note_counter = Counter()
    detail_counter = Counter()
    stage_counter = Counter()
    attempts_dt = []

    for bucket in (green, yellow, gray):
        for r in bucket:
            note_counter[str(r.get("note", ""))] += 1
            detail_counter[str(r.get("status_detail", ""))] += 1

    for _, meta in debug.items():
        stage_counter[str(meta.get("stage", ""))] += 1
        dbg = meta.get("debug") or {}
        for a in dbg.get("attempts", [])[:]:
            dt = a.get("dt_s")
            if isinstance(dt, (int, float)):
                attempts_dt.append(float(dt))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_total": rep.get("total_candidates", 0),
        "counts": {"green": len(green), "yellow": len(yellow), "gray": len(gray)},
        "status_detail_top": detail_counter.most_common(top),
        "note_top": note_counter.most_common(top),
        "stage_top": stage_counter.most_common(),
        "http_attempt_dt_s": {
            "n": len(attempts_dt),
            "p50": statistics.median(attempts_dt) if attempts_dt else 0,
            "p90": statistics.quantiles(attempts_dt, n=10)[8] if len(attempts_dt) >= 20 else 0,
            "max": max(attempts_dt) if attempts_dt else 0,
        },
        "green_list": [
            {
                "origin": g.get("origin"),
                "magnets_found": g.get("magnets_found"),
                "template": g.get("chosen_template"),
                "q": g.get("chosen_query"),
            }
            for g in green[:top]
        ],
        "yellow_high_potential": [
            {
                "origin": y.get("origin"),
                "detail": y.get("status_detail"),
                "note": y.get("note"),
            }
            for y in yellow[:top]
        ],
    }


def write_summary(in_path: str, out_path: str, top: int = 30) -> Dict[str, Any]:
    rep: Dict[str, Any] = load_json(in_path)
    summary = build_summary(rep, top)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return summary


def print_summary(summary: Dict[str, Any], out_path: str, top: int = 30) -> None:
    counts = summary["counts"]
    print("=" * 60)
    print("Funnel summary")
    print("=" * 60)
    print(f"input_total: {summary['input_total']}")
    print(f"green/yellow/gray: {counts['green']}/{counts['yellow']}/{counts['gray']}")
    print("\nTop status_detail:")
    for k, v in summary["status_detail_top"][:10]:
        if k:
            print(f"  {k:14s} {v}")
    print("\nTop note:")
    for k, v in summary["note_top"][:10]:
        if k:
            print(f"  {k:38s} {v}")
    print("\nGreen samples:")
    for g in summary["green_list"][: min(10, top)]:
        print(f"  + {g['origin']}  n={g.get('magnets_found')}  {g.get('template')}  q={g.get('q')}")
    print(f"\nWrote: {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", default="funnel_report.json")
    ap.add_argument("--out", dest="out_path", default="funnel_summary.json")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    summary = write_summary(args.in_path, args.out_path, args.top)
    print_summary(summary, args.out_path, args.top)


if __name__ == "__main__":
    main()

