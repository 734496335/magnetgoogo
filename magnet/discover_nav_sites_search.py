#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from analyze_navigation_sites import analyze_navigation_site
from aux_site_registry import load_aux_sites, normalize_origin, upsert_aux_site


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
SOURCES_FILE = os.path.join(ROOT_DIR, "sources.json")
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


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SEARCH_ENGINES = ("google", "ddg", "bing")
DEFAULT_QUERIES = [
    "magnet search directory",
    "torrent search engine directory",
    "best magnet search engine sites",
    "torrent site list magnet search",
    "磁力搜索 导航站",
    "磁力搜索 网站 大全",
]
ARTICLE_HINTS = (
    "best torrent",
    "torrent search engine",
    "magnet search engine",
    "torrent site list",
    "top torrent",
    "best magnet",
    "torrenting",
)
ARTICLE_SOURCE_SKIP_TOKENS = (
    "facebook.com",
    "twitter.com",
    "linkedin.com",
    "youtube.com",
    "reddit.com",
    "wikipedia.org",
)
ARTICLE_CANDIDATE_HINTS = (
    "torrent",
    "magnet",
    "btdig",
    "btdigg",
    "torrentz",
    "torrentseeker",
    "solidtorrents",
    "snowfl",
    "academictorrents",
    "rarbg",
    "eztv",
    "1337x",
    "pirate",
    "bt4g",
    "yts",
    "torlock",
    "glodls",
    "nyaa",
    "kitty",
    "bitsearch",
)
NAV_HINTS = (
    "磁力",
    "bt",
    "torrent",
    "种子",
    "搜索",
    "导航",
    "大全",
    "网址",
    "入口",
    "地址",
    "cili",
    "cili",
    "skrbt",
    "seedhub",
)
SKIP_HOST_TOKENS = (
    "bing.com",
    "microsoft.com",
    "baidu.com",
    "google.",
    "github.com",
    "zhihu.com",
    "weibo.com",
    "wikipedia.org",
    "yiove.com",
    "litxdh.com",
    "coolexplore.com",
    "onehaoka.com",
    "hao123.com",
)


def load_known_origins() -> Set[str]:
    known: Set[str] = set()
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        sources = json.load(f)
    for rule in sources.get("rulesets", [{}])[0].get("rules", []):
        origin = normalize_origin(rule.get("site", {}).get("origin", ""))
        if origin:
            known.add(origin)
    aux = load_aux_sites()
    for site in aux.get("sites", []):
        origin = normalize_origin(site.get("origin", ""))
        if origin:
            known.add(origin)
    return known


PATH_SEED_TOKENS = ("/proxy", "/sites/", "/site/", "torrent-proxy", "proxy-list", "alternatives", "unblock")


def normalize_candidate_url(url: str, keep_path: bool = False) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    if keep_path and parsed.path and parsed.path != "/":
        return normalize_origin(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def should_keep_result_path(url: str) -> bool:
    parsed = urlparse(url or "")
    haystack = " ".join([parsed.netloc.lower(), parsed.path.lower()])
    return any(token in haystack for token in PATH_SEED_TOKENS)


def has_nav_hint(text: str) -> bool:
    lowered = (text or "").lower()
    return any(token.lower() in lowered for token in NAV_HINTS)


def search_bing(query: str, timeout: int) -> List[Dict[str, str]]:
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count=20"
    resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text or "", "lxml")
    items: List[Dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href.startswith("http"):
            continue
        host = (urlparse(href).hostname or "").lower()
        if any(token in host for token in SKIP_HOST_TOKENS):
            continue
        title = a.get_text(" ", strip=True)[:120]
        if not has_nav_hint(" ".join([href, title, query])):
            continue
        items.append({"engine": "bing", "query": query, "url": href, "title": title})
    return items


def search_google(query: str, timeout: int) -> List[Dict[str, str]]:
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num=20&hl=en"
    resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
    resp.encoding = resp.apparent_encoding or "utf-8"
    items: List[Dict[str, str]] = []
    soup = BeautifulSoup(resp.text or "", "lxml")
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href.startswith("/url?q="):
            continue
        href = urllib.parse.unquote(href.split("/url?q=", 1)[1].split("&", 1)[0])
        title = a.get_text(" ", strip=True)[:120]
        if not href.startswith("http"):
            continue
        host = (urlparse(href).hostname or "").lower()
        if any(token in host for token in SKIP_HOST_TOKENS):
            continue
        if not has_nav_hint(" ".join([href, title, query])):
            continue
        items.append({"engine": "google", "query": query, "url": href, "title": title})
    return items


def search_ddg(query: str, timeout: int) -> List[Dict[str, str]]:
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text or "", "lxml")
    items: List[Dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        title = a.get_text(" ", strip=True)[:120]
        if not href or not title:
            continue
        if href.startswith("//duckduckgo.com/l/?uddg="):
            href = href.split("uddg=", 1)[1].split("&", 1)[0]
            href = urllib.parse.unquote(href)
        if not href.startswith("http"):
            continue
        host = (urlparse(href).hostname or "").lower()
        if any(token in host for token in SKIP_HOST_TOKENS):
            continue
        if not has_nav_hint(" ".join([href, title, query])):
            continue
        items.append({"engine": "ddg", "query": query, "url": href, "title": title})
    return items


def discover_candidates(queries: List[str], timeout: int) -> List[Dict[str, Any]]:
    grouped: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for query in queries:
        for engine in SEARCH_ENGINES:
            try:
                if engine == "google":
                    results = search_google(query, timeout)
                elif engine == "ddg":
                    results = search_ddg(query, timeout)
                else:
                    results = search_bing(query, timeout)
                log.info(f"[search] {engine} query={query} hits={len(results)}")
            except Exception as e:
                log.info(f"[search] {engine} query={query} error={str(e)[:120]}")
                continue
            for item in results:
                origin = normalize_candidate_url(item["url"], keep_path=should_keep_result_path(item["url"]))
                if not origin:
                    continue
                current = grouped.get(origin)
                payload = {
                    "origin": origin,
                    "title": item["title"],
                    "discovered_by": [f"{item['engine']}:{item['query']}"],
                    "hit_count": 1,
                }
                if current is None:
                    grouped[origin] = payload
                else:
                    key = f"{item['engine']}:{item['query']}"
                    if key not in current["discovered_by"]:
                        current["discovered_by"].append(key)
                    current["hit_count"] += 1
    return list(grouped.values())


def derive_brand(origin: str, title: str) -> str:
    text = (title or "").strip()
    if text:
        text = re.split(r"[-|_｜]", text)[0].strip()
    return text[:80] or (urlparse(origin).hostname or "")


def looks_like_article_seed(origin: str, title: str) -> bool:
    haystack = " ".join([(origin or "").lower(), (title or "").lower()])
    return any(token in haystack for token in ARTICLE_HINTS)


def extract_article_candidates(origin: str, timeout: int) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(origin, timeout=timeout, headers=HEADERS, allow_redirects=True)
    except Exception:
        return []
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text or "", "lxml")
    base_host = (urlparse(resp.url or origin).hostname or "").lower()
    grouped: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(resp.url or origin, a.get("href", "").strip())
        title = a.get_text(" ", strip=True)[:120]
        normalized = normalize_candidate_url(href)
        if not normalized:
            continue
        host = (urlparse(normalized).hostname or "").lower()
        if not host or host == base_host:
            continue
        if any(token in host for token in SKIP_HOST_TOKENS) or any(token in host for token in ARTICLE_SOURCE_SKIP_TOKENS):
            continue
        hint_text = " ".join([host, href.lower(), title.lower()])
        if not any(token in hint_text for token in ARTICLE_CANDIDATE_HINTS):
            continue
        existing = grouped.get(normalized)
        if existing is None:
            grouped[normalized] = {
                "origin": normalized,
                "title": title,
                "discovered_by": [f"article:{normalize_origin(origin)}"],
                "hit_count": 1,
            }
        else:
            existing["hit_count"] += 1
    return list(grouped.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover new magnet navigation/jump sites from search engines")
    parser.add_argument("--query", action="append", default=[], help="Search query, repeatable or comma-separated")
    parser.add_argument("--seed-origin", action="append", default=[], help="Direct candidate origins from manual/search-engine review")
    parser.add_argument("--seed-only", action="store_true", help="Only analyze --seed-origin values and skip live search engines")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--detail-limit", type=int, default=16)
    parser.add_argument("--min-hit-count", type=int, default=1)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--update", action="store_true", help="Write confirmed navigation/jump sites to auxiliary_sites.json")
    parser.add_argument("--out", default=os.path.join(ROOT_DIR, "nav_search_discovery_report.json"))
    args = parser.parse_args()

    queries: List[str] = []
    for value in args.query or []:
        queries.extend([part.strip() for part in value.split(",") if part.strip()])
    if args.seed_only:
        queries = []
    elif not queries:
        queries = DEFAULT_QUERIES

    known_origins = load_known_origins()
    discovered = [] if args.seed_only else discover_candidates(queries, args.timeout)
    for value in args.seed_origin or []:
        for raw in value.split(","):
            origin = normalize_candidate_url(raw, keep_path=True)
            if not origin:
                continue
            existing = next((item for item in discovered if item["origin"] == origin), None)
            if existing is None:
                discovered.append(
                    {
                        "origin": origin,
                        "title": "",
                        "discovered_by": ["seed_origin"],
                        "hit_count": 1,
                    }
                )
            else:
                if "seed_origin" not in existing["discovered_by"]:
                    existing["discovered_by"].append("seed_origin")
                existing["hit_count"] += 1

    article_expanded: List[Dict[str, Any]] = []
    for item in list(discovered):
        if not looks_like_article_seed(item.get("origin", ""), item.get("title", "")):
            continue
        expansions = extract_article_candidates(item["origin"], args.timeout)
        if expansions:
            log.info(f"[expand] article={item['origin']} extracted={len(expansions)}")
            article_expanded.extend(expansions)

    for item in article_expanded:
        existing = next((entry for entry in discovered if entry["origin"] == item["origin"]), None)
        if existing is None:
            discovered.append(item)
        else:
            for marker in item.get("discovered_by", []):
                if marker not in existing["discovered_by"]:
                    existing["discovered_by"].append(marker)
            existing["hit_count"] += int(item.get("hit_count", 1))

    candidates = [
        item
        for item in discovered
        if item["hit_count"] >= args.min_hit_count and normalize_origin(item["origin"]) not in known_origins
    ]
    candidates.sort(key=lambda item: (-item["hit_count"], item["origin"]))
    candidates = candidates[: args.top]

    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queries": queries,
        "known_origin_count": len(known_origins),
        "discovered_count": len(discovered),
        "new_candidate_count": len(candidates),
        "results": [],
    }

    updated = 0
    for idx, item in enumerate(candidates, start=1):
        origin = item["origin"]
        log.info(f"[analyze {idx}/{len(candidates)}] {origin}")
        result: Dict[str, Any] = dict(item)
        try:
            analysis = analyze_navigation_site(origin, args.timeout, args.detail_limit)
            result.update(analysis)
            result["brand"] = derive_brand(origin, result.get("title", ""))
            log.info(
                f"  classification={analysis['classification']} reason={analysis['reason']} "
                f"hit_count={item['hit_count']} candidates={len(analysis.get('real_candidate_origins', []))}"
            )
            if args.update and analysis["classification"] in {"navigation", "jump"}:
                upsert_aux_site(
                    analysis["classification"],
                    {
                        "origin": normalize_origin(origin),
                        "brand": result["brand"],
                        "reason": analysis["reason"],
                        "candidate_origins": analysis.get("detail_page_candidates", [])[:40],
                        "real_candidate_origins": analysis.get("real_candidate_origins", []),
                        "real_candidate_samples": analysis.get("real_candidate_samples", []),
                        "discovered_by": item["discovered_by"],
                        "last_checked_at": datetime.now(timezone.utc).isoformat(),
                        "last_extracted_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                updated += 1
        except Exception as e:
            result["classification"] = "error"
            result["error"] = str(e)
            log.info(f"  ERROR: {str(e)[:120]}")
        report["results"].append(result)
        time.sleep(1)

    report["summary"] = {
        "targets": len(candidates),
        "updated_aux_sites": updated,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
