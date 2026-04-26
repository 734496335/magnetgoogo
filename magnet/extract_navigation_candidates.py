#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from aux_site_registry import AUXILIARY_SITES_PATH, normalize_origin


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
LOG_PATH = os.path.join(BASE_DIR, "run.log")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


HEADERS = {"User-Agent": "Mozilla/5.0"}
POSITIVE_TOKENS = (
    "磁力",
    "bt",
    "torrent",
    "种子",
    "搜索",
    "cili",
    "btsow",
    "btdb",
    "kitty",
    "nyaa",
    "xunlei",
)
NEGATIVE_HOST_TOKENS = (
    "beian.miit.gov.cn",
    "baidu.com",
    "google.",
    "github.com",
    "aidh.me",
    "xuebapan.com",
    "gatherfind.com",
    "alookweb.com",
    "xbext.com",
)
NEGATIVE_TEXT_TOKENS = (
    "百度",
    "chrome",
    "浏览器",
    "ai导航",
    "github",
    "学霸盘",
    "gatherfind",
)


def load_auxiliary_sites(path: str = AUXILIARY_SITES_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_auxiliary_sites(data: Dict[str, Any], path: str = AUXILIARY_SITES_PATH) -> None:
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_html(origin: str, timeout: int) -> str:
    resp = requests.get(origin, timeout=timeout, allow_redirects=True, verify=False, headers=HEADERS)
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text or ""


def score_external_link(base_origin: str, text: str, href: str) -> Tuple[int, str]:
    full_url = urljoin(base_origin, href)
    parsed = urlparse(full_url)
    host = (parsed.hostname or "").lower()
    if not host:
        return (-999, "")
    base_host = (urlparse(base_origin).hostname or "").lower()
    if host == base_host:
        return (-999, "")
    if any(token in host for token in NEGATIVE_HOST_TOKENS):
        return (-999, "")

    norm_text = (text or "").strip().lower()
    if any(token.lower() in norm_text for token in NEGATIVE_TEXT_TOKENS):
        return (-999, "")

    score = 0
    if any(token in host for token in ("torrent", "cili", "bt", "xunlei", "nyaa", "kitty")):
        score += 3
    if any(token in norm_text for token in ("磁力", "bt", "种子", "torrent", "搜索", "迅雷")):
        score += 3
    if parsed.scheme == "https":
        score += 1
    if parsed.path in ("", "/"):
        score += 1
    return (score, normalize_origin(full_url))


def extract_candidates_from_nav(origin: str, html: str, excluded_origins: set[str]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    scored: List[Dict[str, Any]] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = a.get_text(" ", strip=True)
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        score, candidate_origin = score_external_link(origin, text, href)
        candidate_origin = candidate_origin.replace("http://", "https://", 1)
        candidate_host = (urlparse(candidate_origin).hostname or "").lower()
        if any(token in candidate_host for token in NEGATIVE_HOST_TOKENS):
            continue
        if score < 4 or not candidate_origin or candidate_origin in seen or candidate_origin in excluded_origins:
            continue
        seen.add(candidate_origin)
        scored.append(
            {
                "origin": candidate_origin,
                "title": text[:80],
                "score": score,
                "source_origin": origin,
            }
        )
    scored.sort(key=lambda item: (-item["score"], item["origin"]))
    return scored


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract real magnet-source candidates from navigation entries in auxiliary_sites.json")
    parser.add_argument("--limit", type=int, default=0, help="Limit navigation sites")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout")
    parser.add_argument("--update", action="store_true", help="Write candidate list back into auxiliary_sites.json navigation entries")
    parser.add_argument("--out", default=os.path.join(ROOT_DIR, "navigation_real_candidates.json"), help="Output report path")
    args = parser.parse_args()

    data = load_auxiliary_sites()
    sites = [site for site in data.get("sites", []) if site.get("category") == "navigation"]
    sites = [site for site in sites if not site.get("origin", "").startswith("https://example-nav.test")]
    excluded_origins = {
        normalize_origin(site.get("origin", "")).replace("http://", "https://", 1)
        for site in data.get("sites", [])
        if site.get("origin")
    }
    if args.limit > 0:
        sites = sites[: args.limit]

    log.info("=" * 60)
    log.info("  Navigation Candidate Extractor")
    log.info("=" * 60)
    log.info(f"Navigation sites: {len(sites)}")

    report_sites = []
    unique_candidates: Dict[str, Dict[str, Any]] = {}

    for idx, site in enumerate(sites):
        origin = site.get("origin", "")
        brand = site.get("brand", site.get("source_name", ""))
        log.info(f"[{idx + 1}/{len(sites)}] {brand or origin}")
        try:
            html = fetch_html(origin, args.timeout)
            candidates = extract_candidates_from_nav(origin, html, excluded_origins)
            log.info(f"  candidates={len(candidates)}")
            report_sites.append(
                {
                    "origin": origin,
                    "brand": brand,
                    "candidates": candidates[:20],
                }
            )
            for cand in candidates:
                existing = unique_candidates.get(cand["origin"])
                if existing is None or cand["score"] > existing["score"]:
                    unique_candidates[cand["origin"]] = cand
            if args.update:
                site["real_candidate_origins"] = [cand["origin"] for cand in candidates[:20]]
                site["real_candidate_samples"] = candidates[:10]
                site["last_extracted_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            log.info(f"  ERROR: {str(e)[:120]}")
            report_sites.append({"origin": origin, "brand": brand, "error": str(e)})

    if args.update:
        save_auxiliary_sites(data)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "navigation_sites": len(sites),
        "unique_candidate_origins": len(unique_candidates),
        "origins": sorted(unique_candidates.values(), key=lambda item: (-item["score"], item["origin"])),
        "sites": report_sites,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"Wrote: {args.out} (unique_candidate_origins={len(unique_candidates)})")


if __name__ == "__main__":
    main()
