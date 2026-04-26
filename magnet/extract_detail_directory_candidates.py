#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

from aux_site_registry import AUXILIARY_SITES_PATH, load_aux_sites, normalize_origin, save_aux_sites


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
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
ABS_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
POSITIVE_HOST_TOKENS = (
    "1337x",
    "bt",
    "btdig",
    "bt4g",
    "btsow",
    "cili",
    "limetorrent",
    "magnet",
    "nyaa",
    "pirate",
    "solidtorrent",
    "torrent",
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
POSITIVE_TEXT_TOKENS = (
    "bt",
    "download",
    "magnet",
    "search",
    "torrent",
    "下载",
    "搜索",
    "磁力",
    "种子",
)
NEGATIVE_HOST_TOKENS = (
    "alicdn.com",
    "baidu.com",
    "beian.miit.gov.cn",
    "cloudflare.com",
    "gstatic.cn",
    "gstatic.com",
    "google.",
    "googax.com",
    "pay.cilizhai.cn",
    "schema.org",
    "wpa.qq.com",
    "w.org",
)
QUERY_URL_KEYS = ("url", "u", "target", "site", "redirect", "redirect_to")
CORE_MAGNET_TOKENS = ("1337x", "bt4g", "btdig", "btsow", "cili", "magnet", "nyaa", "torrent", "xunlei", "磁力", "种子", "迅雷")


def parse_csv_args(values: List[str]) -> List[str]:
    items: List[str] = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part:
                items.append(part)
    return items


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_http(url: str, timeout: int) -> Tuple[str, str, str]:
    resp = requests.get(url, timeout=timeout, allow_redirects=True, verify=False, headers=HEADERS)
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.url or url, resp.text or "", resp.reason or ""


def fetch_browser_many(urls: List[str], timeout: int, wait_ms: int) -> Dict[str, Tuple[str, str, str]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {}

    out: Dict[str, Tuple[str, str, str]] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    page.wait_for_timeout(wait_ms)
                    out[url] = (page.url, page.content(), page.title())
                except Exception as exc:
                    out[url] = (url, "", f"browser_error:{str(exc)[:120]}")
            browser.close()
    except Exception:
        return out
    return out


def looks_blocked(html: str, title: str = "") -> bool:
    haystack = f"{title}\n{html[:2000]}".lower()
    return "just a moment" in haystack or "cf-browser-verification" in haystack or "cloudflare" in haystack


def extract_url_param(raw_url: str) -> List[str]:
    parsed = urlparse(raw_url)
    values: List[str] = []
    for key, raw_values in parse_qs(parsed.query).items():
        if key.lower() not in QUERY_URL_KEYS:
            continue
        for value in raw_values:
            decoded = unquote(value).strip()
            if decoded.startswith(("http://", "https://")):
                values.append(decoded)
    return values


def canonical_origin(raw_url: str, detail_url: str) -> str:
    full_url = urljoin(detail_url, raw_url.strip())
    parsed = urlparse(full_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return normalize_origin(f"{parsed.scheme}://{parsed.netloc}").replace("http://", "https://", 1)


def score_candidate(origin: str, title: str, description: str) -> int:
    host = (urlparse(origin).hostname or "").lower()
    if not host or any(token in host for token in NEGATIVE_HOST_TOKENS):
        return -999
    bare_host = host[4:] if host.startswith("www.") else host
    if bare_host in GENERIC_SEARCH_HOSTS and not any(token in host for token in POSITIVE_HOST_TOKENS):
        return -999

    text = f"{title} {description}".lower()
    has_positive_host = any(token in host for token in POSITIVE_HOST_TOKENS)
    if not has_positive_host:
        return -999
    score = 0
    if has_positive_host:
        score += 4
    if any(token in text for token in POSITIVE_TEXT_TOKENS):
        score += 4
    if origin.startswith("https://"):
        score += 1
    if host.startswith(("www.", "search.")):
        score += 1
    if any(token in host for token in ("photo", "stock", "theme", "wordpress")):
        score -= 3
    return score


def iter_raw_candidate_urls(detail_url: str, soup: BeautifulSoup, html: str) -> Iterable[Tuple[str, str, str]]:
    for meta in soup.find_all("meta"):
        content = (meta.get("content") or "").strip()
        label = meta.get("name") or meta.get("property") or "meta"
        if content.startswith(("http://", "https://")):
            yield content, label, "meta"
            for nested in extract_url_param(content):
                yield nested, f"{label}:query", "meta_query"

    for link in soup.find_all("link"):
        href = (link.get("href") or "").strip()
        if href.startswith(("http://", "https://")):
            yield href, link.get("rel", ["link"])[0] if link.get("rel") else "link", "link"
            for nested in extract_url_param(href):
                yield nested, "link:query", "link_query"

    for tag in soup.find_all(attrs=True):
        for attr_name, attr_value in tag.attrs.items():
            if attr_name.lower() not in {"data-url", "data-href", "data-link", "onclick"}:
                continue
            value = " ".join(attr_value) if isinstance(attr_value, list) else str(attr_value)
            for raw in ABS_URL_RE.findall(value):
                yield raw, attr_name, "attribute"
                for nested in extract_url_param(raw):
                    yield nested, f"{attr_name}:query", "attribute_query"

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if href and not href.startswith(("javascript:", "mailto:", "#")):
            yield urljoin(detail_url, href), a.get_text(" ", strip=True)[:80] or "anchor", "anchor"
            for nested in extract_url_param(href):
                yield nested, "anchor:query", "anchor_query"

    for raw in ABS_URL_RE.findall(html):
        yield raw, "html", "html"
        for nested in extract_url_param(raw):
            yield nested, "html:query", "html_query"


def extract_detail_candidates(detail_url: str, html: str, root_host: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html or "", "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    description = ""
    desc_meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if desc_meta:
        description = (desc_meta.get("content") or "").strip()

    candidates: Dict[str, Dict[str, Any]] = {}
    for raw_url, evidence, evidence_kind in iter_raw_candidate_urls(detail_url, soup, html):
        origin = canonical_origin(raw_url, detail_url)
        host = (urlparse(origin).hostname or "").lower()
        if not origin or not host or host == root_host:
            continue
        score = score_candidate(origin, title, description)
        if evidence_kind in {"meta_query", "link_query"}:
            score += 3
        elif evidence_kind in {"attribute", "attribute_query", "html", "html_query"}:
            score -= 2
        if score < 4:
            continue
        item = {
            "origin": origin,
            "title": title[:80],
            "description": description[:200],
            "score": score,
            "source_detail": detail_url,
            "evidence": evidence,
        }
        existing = candidates.get(origin)
        if existing is None or item["score"] > existing["score"]:
            candidates[origin] = item

    return sorted(candidates.values(), key=lambda item: (-item["score"], item["origin"]))


def select_navigation_sites(data: Dict[str, Any], origins: List[str]) -> List[Dict[str, Any]]:
    wanted = {normalize_origin(origin) for origin in origins}
    sites = []
    for site in data.get("sites", []):
        if site.get("category") != "navigation":
            continue
        origin = normalize_origin(site.get("origin", ""))
        if wanted and origin not in wanted:
            continue
        if site.get("candidate_origins"):
            sites.append(site)
    return sites


def merge_candidates(existing: List[Dict[str, Any]], new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for item in existing + new_items:
        origin = normalize_origin(item.get("origin", ""))
        if not origin:
            continue
        payload = dict(item)
        payload["origin"] = origin
        old = merged.get(origin)
        if old is None or int(payload.get("score", 0)) > int(old.get("score", 0)):
            merged[origin] = payload
    return sorted(merged.values(), key=lambda item: (-int(item.get("score", 0)), item["origin"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract real candidate origins from navigation detail-page samples")
    parser.add_argument("--origin", action="append", default=[], help="Navigation origin to process, comma-separated allowed")
    parser.add_argument("--limit-sites", type=int, default=0)
    parser.add_argument("--limit-details", type=int, default=40)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--browser-wait-ms", type=int, default=2500)
    parser.add_argument("--no-browser", action="store_true", help="Disable Playwright fallback for 403/Cloudflare detail pages")
    parser.add_argument("--update", action="store_true", help="Write extracted real candidates back to auxiliary_sites.json")
    parser.add_argument("--out", default=os.path.join(ROOT_DIR, "detail_directory_candidates.json"))
    args = parser.parse_args()

    data = load_aux_sites()
    origins = parse_csv_args(args.origin)
    sites = select_navigation_sites(data, origins)
    if args.limit_sites > 0:
        sites = sites[: args.limit_sites]

    log.info("=" * 60)
    log.info("  Detail Directory Candidate Extractor")
    log.info("=" * 60)
    log.info(f"Navigation sites: {len(sites)}")

    report_sites: List[Dict[str, Any]] = []
    unique: Dict[str, Dict[str, Any]] = {}

    for site_idx, site in enumerate(sites):
        site_origin = normalize_origin(site.get("origin", ""))
        root_host = (urlparse(site_origin).hostname or "").lower()
        detail_urls = [normalize_origin(url) for url in site.get("candidate_origins", []) if normalize_origin(url)]
        detail_urls = detail_urls[: args.limit_details]
        log.info(f"[{site_idx + 1}/{len(sites)}] {site_origin} detail_urls={len(detail_urls)}")

        pending_browser: List[str] = []
        detail_html: Dict[str, Tuple[str, str, str]] = {}
        detail_errors: List[Dict[str, str]] = []

        for detail_url in detail_urls:
            try:
                final_url, html, reason = fetch_http(detail_url, args.timeout)
                title = BeautifulSoup(html or "", "lxml").title
                title_text = title.get_text(" ", strip=True) if title else reason
                if looks_blocked(html, title_text):
                    pending_browser.append(detail_url)
                else:
                    detail_html[detail_url] = (final_url, html, title_text)
            except Exception as exc:
                if args.no_browser:
                    detail_errors.append({"url": detail_url, "error": str(exc)[:160]})
                else:
                    pending_browser.append(detail_url)

        if pending_browser and not args.no_browser:
            log.info(f"  browser_fallback={len(pending_browser)}")
            detail_html.update(fetch_browser_many(pending_browser, args.timeout, args.browser_wait_ms))

        site_candidates: List[Dict[str, Any]] = []
        for detail_url, (final_url, html, title) in detail_html.items():
            if not html:
                detail_errors.append({"url": detail_url, "error": title or "empty_html"})
                continue
            if looks_blocked(html, title):
                detail_errors.append({"url": detail_url, "error": "blocked_or_challenge"})
                continue
            extracted = extract_detail_candidates(final_url or detail_url, html, root_host)
            site_candidates.extend(extracted[:3])

        site_candidates = merge_candidates([], site_candidates)
        for item in site_candidates:
            existing = unique.get(item["origin"])
            if existing is None or int(item["score"]) > int(existing["score"]):
                unique[item["origin"]] = item

        log.info(f"  real_candidates={len(site_candidates)} errors={len(detail_errors)}")
        if args.update:
            merged_samples = merge_candidates(site.get("real_candidate_samples") or [], site_candidates)
            site["real_candidate_samples"] = merged_samples[:20]
            site["real_candidate_origins"] = [item["origin"] for item in merged_samples[:40]]
            site["last_detail_extracted_at"] = now_iso()

        report_sites.append(
            {
                "origin": site_origin,
                "brand": site.get("brand") or site.get("source_name") or "",
                "detail_urls": len(detail_urls),
                "real_candidate_origins": [item["origin"] for item in site_candidates],
                "real_candidate_samples": site_candidates[:20],
                "errors": detail_errors[:20],
            }
        )

    if args.update:
        save_aux_sites(data)

    report = {
        "generated_at": now_iso(),
        "site_count": len(sites),
        "unique_candidate_origins": len(unique),
        "origins": sorted(unique.values(), key=lambda item: (-int(item.get("score", 0)), item["origin"])),
        "sites": report_sites,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"Wrote: {args.out} (unique_candidate_origins={len(unique)})")


if __name__ == "__main__":
    main()
