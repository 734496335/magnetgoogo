#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse


sys.stdout.reconfigure(encoding="utf-8", errors="replace")


POSITIVE_TERMS = (
    "磁力搜索引擎",
    "bt种子搜索",
    "磁力链接搜索",
    "dht",
    "索引",
    "种子搜索",
    "bt搜索",
    "torrent search",
    "磁力链",
)

NEGATIVE_TERMS = (
    "网址目录",
    "网址大全",
    "导航",
    "论坛",
    "社区平台",
    "电影下载",
    "迅雷电影",
    "动漫资源",
    "阅读",
    "图库",
    "影视下载",
    "发布页",
)


def normalize_origin(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    scheme = parsed.scheme if parsed.scheme in ("http", "https") else "https"
    return f"{scheme}://{parsed.netloc}"


def score_result(item: dict) -> int:
    desc = (item.get("desc") or "").lower()
    score = 0
    for term in POSITIVE_TERMS:
        if term.lower() in desc:
            score += 3
    for term in NEGATIVE_TERMS:
        if term.lower() in desc:
            score -= 4
    if "搜索引擎" in (item.get("desc") or ""):
        score += 2
    if "dht" in desc:
        score += 2
    return score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="btmayi_real_domains.json")
    parser.add_argument("--output", default="strong_candidates.json")
    parser.add_argument("--min-score", type=int, default=3)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    out = []
    seen = set()
    for item in data.get("results", []):
        origin = normalize_origin(item.get("real_url") or item.get("url") or "")
        if not origin or origin in seen:
            continue
        score = score_result(item)
        if score < args.min_score:
            continue
        seen.add(origin)
        out.append(
            {
                "origin": origin,
                "name": item.get("name") or urlparse(origin).netloc,
                "reason": "btmayi_strong_desc",
                "desc": item.get("desc") or "",
                "score": score,
            }
        )

    out.sort(key=lambda item: (-item["score"], item["origin"]))
    payload = {
        "generated_at": os.path.basename(args.input),
        "total": len(out),
        "candidates": out,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"wrote {args.output} total={len(out)}")
    for item in out[:20]:
        print(item["score"], item["origin"], item["name"])


if __name__ == "__main__":
    main()
