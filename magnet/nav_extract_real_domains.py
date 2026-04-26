#!/usr/bin/env python3
"""
Batch extract real external domains from nav detail/interstitial pages.

Input JSON formats supported:
- list[str]: list of URLs (nav detail pages)
- dict with key in (urls, candidates, results): list of str or dicts with url field

Output:
- nav_real_domains.json: list of unique extracted external origins
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

from nav_real_domain import extract_real_external_urls


sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler("run.log", encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def load_urls(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [str(x) for x in data if str(x).strip()]
    if isinstance(data, dict):
        for key in ("urls", "candidates", "results"):
            if key in data and isinstance(data[key], list):
                out = []
                for it in data[key]:
                    if isinstance(it, str):
                        out.append(it)
                    elif isinstance(it, dict):
                        out.append(it.get("url") or it.get("detail_url") or it.get("page_url") or "")
                return [u for u in out if u]
    raise ValueError("unsupported json format")


def to_origin(url: str) -> str:
    p = urlparse(url)
    if not p.netloc:
        return ""
    scheme = p.scheme if p.scheme in ("http", "https") else "https"
    return f"{scheme}://{p.netloc}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="input json")
    ap.add_argument("--out", dest="out_path", default="nav_real_domains.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    urls = load_urls(args.in_path)
    if args.limit > 0:
        urls = urls[: args.limit]

    session = requests.Session()
    origins = {}
    details: List[Dict[str, Any]] = []

    log.info(f"Input pages: {len(urls)}")
    for i, page in enumerate(urls):
        log.info(f"[{i+1}/{len(urls)}] {page}")
        try:
            r = session.get(page, timeout=12, headers=HEADERS, allow_redirects=True)
        except requests.RequestException as e:
            details.append({"page": page, "error": str(e)[:120], "candidates": []})
            continue
        if r.status_code != 200:
            details.append({"page": page, "http_status": r.status_code, "candidates": []})
            continue

        cands = extract_real_external_urls(r.text, page_url=r.url, nav_origin=to_origin(page))
        details.append({"page": page, "http_status": r.status_code, "candidates": [asdict(c) for c in cands[:10]]})
        for c in cands:
            o = to_origin(c.url)
            if o and o not in origins:
                origins[o] = {"origin": o, "from_page": page, "reason": c.reason}

        time.sleep(args.sleep)

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_pages": len(urls),
        "unique_origins": len(origins),
        "origins": list(origins.values()),
        "samples": details[:50],
    }
    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    log.info(f"Wrote: {args.out_path} (unique_origins={len(origins)})")


if __name__ == "__main__":
    main()

