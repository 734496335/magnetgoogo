#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from aux_site_registry import normalize_origin, upsert_aux_site


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


HEADERS = {"User-Agent": "Mozilla/5.0"}
NAV_TOKENS = ("导航", "网址大全", "网站大全", "地址发布", "最新地址", "入口", "收藏", "推荐", "网址")
MAGNET_TOKENS = ("磁力", "bt", "torrent", "种子", "搜索", "xunlei", "迅雷", "cili", "kitty", "nyaa")
POSITIVE_HOST_TOKENS = (
    "1337x",
    "bt",
    "cili",
    "cldi",
    "clp",
    "eztv",
    "kickass",
    "kitty",
    "limetorrent",
    "mirror",
    "nyaa",
    "pirate",
    "proxy",
    "rarbg",
    "torrent",
    "unblock",
    "xunlei",
    "yts",
)
GENERIC_SEARCH_HOSTS = (
    "ask.com",
    "chinaso.com",
    "duckduckgo.com",
    "naver.com",
    "qwant.com",
    "search.yahoo.com",
    "sm.cn",
    "so.com",
    "sogou.com",
    "toutiao.com",
    "wuzhuiso.com",
    "yandex.com",
)
NEGATIVE_HOST_TOKENS = (
    "beian.miit.gov.cn",
    "github.com",
    "google.",
    "baidu.com",
    "parklogic.com",
    "pay.cilizhai.cn",
    "officezhushou.com",
    "stocksnap.io",
    "wpa.qq.com",
    "askyaya.cn",
    "bicaotv.net",
    "2k4k.sbs",
    "datatrack.cilizhai.cn",
)
GENERIC_TITLES = ("磁力搜索引擎", "bt搜索引擎", "磁力链接", "搜索引擎", "搜磁力", "最佳的磁力搜索引擎")
DETAIL_PATH_RE = re.compile(r"/?(detail|sites?)[_/\-]?\d+(\.html?)?$", re.I)
ABS_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.I)
PROXY_DIRECTORY_TOKENS = ("proxy", "proxies", "mirror", "unblock", "torrent proxy", "pirateproxy")
CORE_MAGNET_TOKENS = ("1337x", "bt4g", "btdig", "btsow", "cili", "magnet", "nyaa", "torrent", "xunlei", "磁力", "种子", "迅雷")


def parse_csv_args(values: List[str]) -> List[str]:
    items: List[str] = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part:
                items.append(part)
    return items


def normalize_origin_arg(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return normalize_origin(value)


def load_sources() -> Dict[str, Any]:
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sources(data: Dict[str, Any]) -> None:
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("meta", {})
    data["meta"]["total_rules"] = sum(len(rs.get("rules", [])) for rs in data.get("rulesets", []))
    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_html(url: str, timeout: int) -> Tuple[str, str]:
    resp = requests.get(url, timeout=timeout, allow_redirects=True, verify=False, headers=HEADERS)
    resp.encoding = resp.apparent_encoding or "utf-8"
    final_url = resp.url or url
    return final_url, resp.text or ""


def fetch_with_browser(url: str, timeout: int, wait_ms: int = 8000) -> Optional[Dict[str, str]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(wait_ms)
            data = {
                "final_url": page.url,
                "title": page.title(),
                "html": page.content(),
            }
            browser.close()
            return data
    except Exception:
        return None


def decode_security_gate_urls(html: str) -> List[str]:
    match = re.search(r'<meta name="rdata" content="([^"]+)"', html or "", re.I)
    if not match:
        return []
    encoded = match.group(1).strip()
    if not encoded:
        return []
    try:
        decoded = base64.b64decode(encoded[::-1] + "=" * (-len(encoded) % 4)).decode("utf-8", errors="replace")
        data = json.loads(decoded)
    except Exception:
        return []
    urls = data.get("urls", [])
    if not isinstance(urls, list):
        return []
    cleaned: List[str] = []
    for raw in urls:
        if not isinstance(raw, str):
            continue
        try:
            normalized = normalize_origin(raw)
        except ValueError:
            return
        if normalized:
            cleaned.append(normalized)
    return list(dict.fromkeys(cleaned))


def extract_address_publish_candidates(html: str) -> List[str]:
    soup = BeautifulSoup(html or "", "lxml")
    text = soup.get_text(" ", strip=True)
    haystack = f"{text}\n{html[:12000]}"
    lowered = haystack.lower()
    publish_tokens = ("发布页", "最新地址", "最新地址", "地址发布", "收藏本页", "备用地址", "入口")
    if not any(token in haystack for token in publish_tokens) and "redirecttorandomsubdomain" not in lowered:
        return []

    candidates: List[str] = []

    def push(raw: str) -> None:
        raw = (raw or "").strip().strip(".,;:，。；：'\"()[]{}<>")
        if not raw:
            return
        if not raw.startswith(("http://", "https://")):
            raw = "https://" + raw
        try:
            normalized = normalize_origin(raw)
        except ValueError:
            return
        host = (urlparse(normalized).hostname or "").lower()
        if not host:
            return
        if any(token in host for token in NEGATIVE_HOST_TOKENS):
            return
        if not any(token in host for token in POSITIVE_HOST_TOKENS):
            return
        candidates.append(normalized.replace("http://", "https://", 1))

    for raw in ABS_URL_RE.findall(html or ""):
        push(raw)
    for domain in re.findall(r"redirectToRandomSubdomain\(['\"]([^'\"]+)['\"]\)", html or "", re.I):
        push("www." + domain)
    for domain in DOMAIN_RE.findall(text):
        push(domain)

    return list(dict.fromkeys(candidates))


def classify_cross_host_landing(origin: str, final_url: str, title: str) -> Optional[Tuple[str, str]]:
    origin_host = (urlparse(origin).hostname or "").lower()
    final_host = (urlparse(final_url).hostname or "").lower()
    title_lower = (title or "").lower()
    if not origin_host or not final_host or origin_host == final_host:
        return None
    if any(token in title_lower for token in ("hugedomains", "parked", "parking", "forsale", "for sale")):
        return ("redirect", "parked_landing_page")
    return ("redirect", "cross_host_landing_page")


def is_magnetish(text: str) -> bool:
    lowered = (text or "").lower()
    return any(token.lower() in lowered for token in MAGNET_TOKENS)


def is_navigationish(text: str) -> bool:
    lowered = (text or "").lower()
    return any(token.lower() in lowered for token in NAV_TOKENS)


def extract_homepage_signals(origin: str, html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    meta_text = " ".join(
        tag.get("content", "").strip()
        for tag in soup.find_all("meta")
        if tag.get("content")
    )
    page_text = soup.get_text(" ", strip=True)
    base_host = (urlparse(origin).hostname or "").lower()

    internal_detail_links: List[Dict[str, str]] = []
    external_hosts: List[str] = []
    external_links: List[Dict[str, str]] = []
    magnet_anchor_count = 0
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        text = a.get_text(" ", strip=True)
        full_url = urljoin(origin, href)
        parsed = urlparse(full_url)
        host = (parsed.hostname or "").lower()
        if not host:
            continue
        if is_magnetish(text):
            magnet_anchor_count += 1
        if host != base_host:
            external_hosts.append(host)
            external_links.append({"url": normalize_origin(full_url), "title": text[:80]})
            continue
        if DETAIL_PATH_RE.search(parsed.path):
            internal_detail_links.append({"url": normalize_origin(full_url), "title": text[:80]})

    signals = {
        "title": title[:160],
        "meta": meta_text[:300],
        "text_len": len(page_text),
        "magnet_anchor_count": magnet_anchor_count,
        "internal_detail_links": list({item["url"]: item for item in internal_detail_links}.values()),
        "external_links": list({item["url"]: item for item in external_links}.values()),
        "unique_external_hosts": sorted(set(external_hosts)),
    }
    nav_score = 0
    if is_navigationish(title) or is_navigationish(meta_text):
        nav_score += 4
    if is_magnetish(title) or is_magnetish(meta_text):
        nav_score += 2
    if magnet_anchor_count >= 8:
        nav_score += 3
    if len(signals["internal_detail_links"]) >= 10:
        nav_score += 4
    elif len(signals["internal_detail_links"]) >= 5:
        nav_score += 2
    if len(signals["unique_external_hosts"]) >= 20 and any(
        token in " ".join([title, meta_text]).lower() for token in PROXY_DIRECTORY_TOKENS
    ):
        nav_score += 5
    if "just a moment" in title.lower() or "安全中心" in title:
        nav_score -= 4
    signals["nav_score"] = nav_score
    return signals


def score_candidate(url: str, title: str, description: str) -> int:
    try:
        parsed = urlparse(url)
    except ValueError:
        return -999
    host = (parsed.hostname or "").lower()
    if not host or any(token in host for token in NEGATIVE_HOST_TOKENS):
        return -999
    if host.startswith("www."):
        bare_host = host[4:]
    else:
        bare_host = host
    if bare_host in GENERIC_SEARCH_HOSTS and not any(token in host for token in POSITIVE_HOST_TOKENS):
        return -999
    if host.startswith(("static.", "img.", "cdn.", "assets.", "js.", "css.")):
        return -999
    path_lower = (parsed.path or "").lower()
    if any(token in path_lower for token in ("/api", "/point", "/track", "/tj", "/stat", "/report")):
        return -999

    title_lower = (title or "").strip().lower()
    desc_lower = (description or "").strip().lower()
    text_lower = f"{title_lower} {desc_lower}"
    has_positive_host = any(token in host for token in POSITIVE_HOST_TOKENS)
    if not has_positive_host:
        return -999
    score = 0
    if has_positive_host:
        score += 4
    if is_magnetish(title) and title_lower not in GENERIC_TITLES:
        score += 3
    if is_magnetish(description):
        score += 2
    if parsed.path in ("", "/"):
        score += 1
    if title_lower in GENERIC_TITLES and not any(token in host for token in POSITIVE_HOST_TOKENS):
        score -= 2
    if any(token in host for token in ("anime", "movie", "photo", "stock", "game")) and not any(
        token in host for token in POSITIVE_HOST_TOKENS
    ):
        score -= 2
    return score


def extract_external_directory_candidates(origin: str, signals: Dict[str, Any]) -> List[Dict[str, Any]]:
    title = signals.get("title", "")
    meta = signals.get("meta", "")
    candidates: Dict[str, Dict[str, Any]] = {}
    for item in signals.get("external_links", []):
        url = item.get("url", "")
        label = item.get("title", "")
        score = score_candidate(url, label or title, meta)
        if score < 4:
            continue
        normalized = normalize_origin(url).replace("http://", "https://", 1)
        existing = candidates.get(normalized)
        payload = {
            "origin": normalized,
            "title": (label or title)[:80],
            "description": meta[:200],
            "score": score,
            "source_detail": origin,
        }
        if existing is None or payload["score"] > existing["score"]:
            candidates[normalized] = payload
    return sorted(candidates.values(), key=lambda entry: (-entry["score"], entry["origin"]))


def extract_detail_target(detail_url: str, html: str, root_host: str) -> Optional[Dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    page_text = soup.get_text(" ", strip=True)
    candidates: Dict[str, Dict[str, Any]] = {}

    def push(url: str, label: str, description: str) -> None:
        try:
            parsed = urlparse(url)
        except ValueError:
            return
        if not parsed.scheme or not parsed.netloc:
            try:
                parsed = urlparse(urljoin(detail_url, url))
            except ValueError:
                return
        normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        host = (parsed.hostname or "").lower()
        if not host or host == root_host:
            return
        score = score_candidate(normalized, label, description)
        if score < 4:
            return
        existing = candidates.get(normalized)
        item = {
            "origin": normalized,
            "title": (label or title)[:80],
            "description": description[:200],
            "score": score,
            "source_detail": detail_url,
        }
        if existing is None or item["score"] > existing["score"]:
            candidates[normalized] = item

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        full = urljoin(detail_url, href)
        text = a.get_text(" ", strip=True)
        push(full, text or title, page_text[:240])

    urls = list(dict.fromkeys(ABS_URL_RE.findall(html)))
    for raw in urls:
        push(raw, title, page_text[:240])

    if not candidates:
        return None
    best = sorted(candidates.values(), key=lambda item: (-item["score"], item["origin"]))[0]
    return best


def analyze_navigation_site(origin: str, timeout: int, detail_limit: int) -> Dict[str, Any]:
    browser_data: Optional[Dict[str, str]] = None
    try:
        final_url, html = fetch_html(origin, timeout)
    except Exception:
        browser_data = fetch_with_browser(origin, timeout)
        if not browser_data:
            raise
        final_url = browser_data.get("final_url", origin)
        html = browser_data.get("html", "")
    signals = extract_homepage_signals(final_url, html)
    title_lower = signals["title"].lower()
    result: Dict[str, Any] = {
        "origin": normalize_origin(origin),
        "final_url": normalize_origin(final_url),
        "title": signals["title"],
        "nav_score": signals["nav_score"],
        "signal_summary": {
            "text_len": signals["text_len"],
            "magnet_anchor_count": signals["magnet_anchor_count"],
            "internal_detail_link_count": len(signals["internal_detail_links"]),
            "unique_external_hosts": signals["unique_external_hosts"][:20],
        },
        "classification": None,
        "reason": None,
        "detail_page_candidates": [item["url"] for item in signals["internal_detail_links"][:40]],
        "real_candidate_origins": [],
        "real_candidate_samples": [],
    }

    landing_classification = classify_cross_host_landing(origin, final_url, signals["title"])
    gate_urls = decode_security_gate_urls(html)
    if gate_urls:
        result["classification"] = "jump"
        result["reason"] = "security_center_rdata_gate"
        result["real_candidate_origins"] = gate_urls[:20]
        result["real_candidate_samples"] = [
            {
                "origin": item,
                "title": signals["title"][:80],
                "description": "decoded from security gate rdata",
                "score": 8,
                "source_detail": normalize_origin(final_url),
            }
            for item in gate_urls[:10]
        ]
        return result

    publish_urls = extract_address_publish_candidates(html)
    if publish_urls and signals["nav_score"] < 6:
        result["classification"] = "jump"
        result["reason"] = "address_publish_page"
        result["real_candidate_origins"] = publish_urls[:20]
        result["real_candidate_samples"] = [
            {
                "origin": item,
                "title": signals["title"][:80],
                "description": "extracted from address publish page",
                "score": 7,
                "source_detail": normalize_origin(final_url),
            }
            for item in publish_urls[:10]
        ]
        return result

    if landing_classification and signals["nav_score"] < 6:
        result["classification"], result["reason"] = landing_classification
        return result

    if "just a moment" in title_lower:
        if browser_data is None:
            browser_data = fetch_with_browser(origin, timeout)
        if browser_data:
            browser_final_url = normalize_origin(browser_data.get("final_url", ""))
            browser_html = browser_data.get("html", "")
            browser_signals = extract_homepage_signals(browser_final_url or final_url, browser_html)
            browser_title = browser_signals["title"]
            result["browser_final_url"] = browser_final_url
            result["browser_final_title"] = browser_title
            gate_urls = decode_security_gate_urls(browser_html)
            if gate_urls:
                result["classification"] = "jump"
                result["reason"] = "security_center_rdata_gate"
                result["real_candidate_origins"] = gate_urls[:20]
                result["real_candidate_samples"] = [
                    {
                        "origin": item,
                        "title": browser_title[:80],
                        "description": "decoded from browser-rendered security gate rdata",
                        "score": 8,
                        "source_detail": browser_final_url or normalize_origin(final_url),
                    }
                    for item in gate_urls[:10]
                ]
                return result
            browser_landing = classify_cross_host_landing(origin, browser_final_url, browser_title)
            if browser_landing:
                result["classification"], result["reason"] = browser_landing
                return result
            if "just a moment" not in browser_title.lower():
                final_url = browser_final_url or final_url
                html = browser_html
                signals = browser_signals
                title_lower = signals["title"].lower()
                result["final_url"] = normalize_origin(final_url)
                result["title"] = signals["title"]
                result["nav_score"] = signals["nav_score"]
                result["signal_summary"] = {
                    "text_len": signals["text_len"],
                    "magnet_anchor_count": signals["magnet_anchor_count"],
                    "internal_detail_link_count": len(signals["internal_detail_links"]),
                    "unique_external_hosts": signals["unique_external_hosts"][:20],
                }
                result["detail_page_candidates"] = [item["url"] for item in signals["internal_detail_links"][:40]]
            else:
                result["classification"] = "blocked"
                result["reason"] = "cloudflare_challenge"
                return result
        else:
            result["classification"] = "blocked"
            result["reason"] = "cloudflare_challenge"
            return result
    if "安全中心" in signals["title"]:
        gate_urls = decode_security_gate_urls(html)
        result["gate_candidate_origins"] = gate_urls
        if gate_urls:
            result["classification"] = "jump"
            result["reason"] = "security_center_rdata_gate"
            result["real_candidate_origins"] = gate_urls[:20]
            result["real_candidate_samples"] = [
                {
                    "origin": item,
                    "title": signals["title"][:80],
                    "description": "decoded from security gate rdata",
                    "score": 8,
                    "source_detail": normalize_origin(final_url),
                }
                for item in gate_urls[:10]
            ]
            return result
        result["classification"] = "blocked"
        result["reason"] = "security_center_gate"
        return result
    if "redirecting" in title_lower and len(signals["internal_detail_links"]) == 0:
        browser_data = fetch_with_browser(origin, timeout)
        if browser_data:
            browser_final = normalize_origin(browser_data.get("final_url", ""))
            browser_title = browser_data.get("title", "")
            result["browser_final_url"] = browser_final
            result["browser_final_title"] = browser_title
            result["browser_resolved"] = bool(browser_final and browser_final != result["final_url"])
            if result["browser_resolved"]:
                result["classification"] = "redirect"
                result["reason"] = "js_redirect_resolved"
                return result
        result["classification"] = "redirect"
        result["reason"] = "js_redirect_gate"
        return result

    external_directory_candidates = extract_external_directory_candidates(final_url, signals)
    if signals["nav_score"] >= 6 and len(signals["internal_detail_links"]) < 5 and len(external_directory_candidates) >= 8:
        result["classification"] = "navigation"
        result["reason"] = "nav_proxy_external_directory"
        ranked = external_directory_candidates[:30]
        result["real_candidate_origins"] = [item["origin"] for item in ranked[:20]]
        result["real_candidate_samples"] = ranked[:10]
        return result

    if signals["nav_score"] < 6 or len(signals["internal_detail_links"]) < 5:
        result["classification"] = "not_navigation"
        result["reason"] = "insufficient_navigation_signals"
        return result

    result["classification"] = "navigation"
    result["reason"] = "nav_directory_detail_pages"
    candidates: Dict[str, Dict[str, Any]] = {}
    root_host = (urlparse(final_url).hostname or "").lower()
    detail_links = signals["internal_detail_links"][:detail_limit]

    for item in detail_links:
        try:
            detail_final_url, detail_html = fetch_html(item["url"], timeout)
            candidate = extract_detail_target(detail_final_url, detail_html, root_host)
            if candidate:
                existing = candidates.get(candidate["origin"])
                if existing is None or candidate["score"] > existing["score"]:
                    candidates[candidate["origin"]] = candidate
        except Exception:
            continue

    ranked = sorted(candidates.values(), key=lambda entry: (-entry["score"], entry["origin"]))
    result["detail_pages_scanned"] = len(detail_links)
    if not ranked:
        result["classification"] = "not_navigation"
        result["reason"] = "no_magnet_candidate_evidence"
        return result
    result["real_candidate_origins"] = [item["origin"] for item in ranked[:20]]
    result["real_candidate_samples"] = ranked[:10]
    return result


def select_targets(data: Dict[str, Any], args: argparse.Namespace) -> List[Tuple[int, Dict[str, Any]]]:
    target_origins = {normalize_origin_arg(v) for v in parse_csv_args(args.origin)}
    direct_origins = [normalize_origin_arg(v) for v in parse_csv_args(args.direct_origin)]
    target_rule_ids = set(parse_csv_args(args.rule_id))
    rules = data["rulesets"][0]["rules"]
    targets: List[Tuple[int, Dict[str, Any]]] = []
    for idx, rule in enumerate(rules):
        health = rule.get("health", {})
        if not args.all_non_green and not target_origins and not target_rule_ids:
            continue
        if args.all_non_green and health.get("status") == "green":
            continue
        origin = normalize_origin_arg(rule.get("site", {}).get("origin", ""))
        rule_id = rule.get("id", "")
        if target_origins and origin not in target_origins:
            continue
        if target_rule_ids and rule_id not in target_rule_ids:
            continue
        targets.append((idx, rule))

    synthetic_index = -1
    known_rule_origins = {normalize_origin_arg(rule.get("site", {}).get("origin", "")) for rule in rules}
    for origin in direct_origins:
        if not origin or origin in known_rule_origins:
            continue
        synthetic_rule = {
            "id": f"direct:{origin}",
            "site": {
                "name": urlparse(origin).hostname or origin,
                "origin": origin,
                "brand": urlparse(origin).hostname or origin,
            },
            "health": {
                "status": "gray",
                "status_detail": "parsing_failed",
            },
        }
        targets.append((synthetic_index, synthetic_rule))
        synthetic_index -= 1
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze navigation-style sites and extract real magnet-source candidates")
    parser.add_argument("--origin", action="append", default=[], help="Origin(s) to analyze, repeatable or comma-separated")
    parser.add_argument("--direct-origin", action="append", default=[], help="Analyze arbitrary origins not yet present in sources.json")
    parser.add_argument("--rule-id", action="append", default=[], help="Rule id(s) to analyze, repeatable or comma-separated")
    parser.add_argument("--all-non-green", action="store_true", help="Analyze all non-green sources")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds")
    parser.add_argument("--detail-limit", type=int, default=16, help="Max internal detail pages to inspect per site")
    parser.add_argument("--update", action="store_true", help="Write confirmed navigation sites back into sources.json and auxiliary_sites.json")
    parser.add_argument("--out", default=os.path.join(ROOT_DIR, "navigation_site_analysis_report.json"), help="Output report path")
    args = parser.parse_args()

    data = load_sources()
    targets = select_targets(data, args)

    log.info("=" * 60)
    log.info("  Navigation Site Analyzer")
    log.info("=" * 60)
    log.info(f"Targets: {len(targets)}")

    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [],
        "summary": {},
    }
    updated = 0

    for pos, (idx, rule) in enumerate(targets, start=1):
        origin = rule.get("site", {}).get("origin", "")
        brand = rule.get("site", {}).get("brand", rule.get("site", {}).get("name", ""))
        log.info(f"[{pos}/{len(targets)}] {brand or origin}")
        result: Dict[str, Any] = {
            "rule_id": rule.get("id"),
            "origin": origin,
            "brand": brand,
        }
        try:
            analysis = analyze_navigation_site(origin, args.timeout, args.detail_limit)
            result.update(analysis)
            log.info(
                f"  classification={analysis['classification']} reason={analysis['reason']} "
                f"nav_score={analysis.get('nav_score', 0)} candidates={len(analysis.get('real_candidate_origins', []))}"
            )
            if args.update and analysis["classification"] in {"navigation", "jump"}:
                now_iso = datetime.now(timezone.utc).isoformat()
                category = analysis["classification"]
                if not str(rule.get("id", "")).startswith("direct:"):
                    rule["health"]["status"] = "gray"
                    rule["health"]["status_detail"] = "expired"
                    rule["health"]["last_checked_at"] = now_iso
                    rule["health"]["note"] = f"aux_site:{category}:{analysis['reason']}"
                    rule["health"]["diagnosis"] = f"classified as {category} site by navigation analyzer; use auxiliary discovery pipeline"
                upsert_aux_site(
                    category,
                    {
                        "origin": normalize_origin(origin),
                        "brand": brand,
                        "source_rule_id": rule.get("id"),
                        "source_name": rule.get("site", {}).get("name"),
                        "reason": analysis["reason"],
                        "candidate_origins": analysis.get("detail_page_candidates", [])[:40],
                        "real_candidate_origins": analysis.get("real_candidate_origins", []),
                        "real_candidate_samples": analysis.get("real_candidate_samples", []),
                        "last_checked_at": now_iso,
                        "last_extracted_at": now_iso,
                    },
                )
                updated += 1
        except Exception as e:
            result["classification"] = "error"
            result["error"] = str(e)
            log.info(f"  ERROR: {str(e)[:120]}")
        report["results"].append(result)

    if args.update:
        save_sources(data)

    report["summary"] = {
        "targets": len(targets),
        "classifications": Counter(item.get("classification", "unknown") for item in report["results"]),
        "updated_navigation_sites": updated,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    log.info(f"Wrote: {args.out}")
    log.info(f"Updated navigation sites: {updated}")


if __name__ == "__main__":
    main()
