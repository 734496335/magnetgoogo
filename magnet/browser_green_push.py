#!/usr/bin/env python3
"""
Browser Green Push v2 — 用真实浏览器对 yellow 源做深度验证
=========================================================
增强能力（相比 playwright_verify.py）：
  1. 交互式搜索：首页找到搜索框 → 输入诱饵词 → 点击搜索按钮/回车
  2. 详情页二跳：搜索结果页无 magnet 时，点击结果链接进入详情页提取
  3. DOM 稳定等待：MutationObserver 等待内容渲染完成
  4. 更多搜索路径变体：覆盖中文影视站常见路径
  5. Hash-in-URL 提取：从链接路径中提取 40 位 hex hash
  6. 多种诱饵词：覆盖电影/动漫/游戏/中文

用法：
  python magnet/browser_green_push.py                # 验证全部 yellow
  python magnet/browser_green_push.py --limit 10     # 只验证前10个
  python magnet/browser_green_push.py --start 5      # 从第6个开始
  python magnet/browser_green_push.py --candidates candidates.json  # 验证候选池
  python magnet/browser_green_push.py --update       # 更新 sources.json
"""

import sys
import os
import re
import json
import time
import hashlib
import base64
import urllib.parse
import argparse
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from aux_site_registry import upsert_aux_site

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "run.log"), encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
SOURCES_FILE = os.path.join(ROOT_DIR, "sources.json")

# ── Evidence extraction ──────────────────────────────────────────

MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:[A-Za-z0-9]{32,40}", re.I)
HASH40_RE = re.compile(r"\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b")
BTIH_RE = re.compile(r"btih[:=]([A-Za-z2-7]{32}|[0-9A-Fa-f]{40})", re.I)
HASH32_RE = re.compile(r"\b[A-Z2-7]{32}\b")

# Bait queries: cover movies, anime, games, Chinese
BAIT_QUERIES = [
    "Inception",
    "Big Buck Bunny",
    "Avatar",
    "One Piece",
    "Interstellar",
    "The Dark Knight",
    "Sintel",
    "Fedora",
    "mp4",
]

# Extended search path templates (includes Chinese site patterns)
SEARCH_TEMPLATES = [
    "/search?q={q}",
    "/search/{q}",
    "/search?word={q}",
    "/search?query={q}",
    "/search?kw={q}",
    "/search?keyword={q}",
    "/?q={q}",
    "/?s={q}",
    "/s/?q={q}",
    "/s/{q}",
    "/so/{q}",
    "/so/{q}.html",
    "/index.php?q={q}",
    "/index.php?search={q}",
    "/search/{q}/1.html",
    "/search/{q}/1/",
    "/search/{q}/1/0/0.html",
    "/vodsearch/{q}/",
    "/s?wd={q}",
    "/list.html?key={q}",
    "/search?q={q}&page=1",
    "/search?word={q}&page=1",
    # Chinese movie site patterns
    "/e/search/index.php",
    "/so.html?wd={q}",
    "/vodsearch/-------------.html?wd={q}",
    "/index.php/vod/search.html?wd={q}",
    "/search/index.html?keyword={q}",
    "/index.php?m=vod-search&wd={q}",
    # API patterns
    "/api/search?q={q}",
    "/api/v1/search?q={q}",
]


def decode_btih_hash(raw: str) -> Optional[str]:
    raw = (raw or "").strip().upper()
    if not raw:
        return None
    if re.fullmatch(r"[0-9A-F]{40}", raw):
        return raw
    if re.fullmatch(r"[A-Z2-7]{32}", raw):
        try:
            return base64.b32decode(raw).hex().upper()
        except Exception:
            return None
    return None


def extract_magnets(html: str) -> List[Dict[str, str]]:
    """Extract magnet links and hashes from HTML content."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    magnets, seen = [], set()

    def push_hash(raw: str, title: str = "") -> None:
        hh = decode_btih_hash(raw)
        if not hh or hh in seen:
            return
        seen.add(hh)
        magnets.append({"title": (title or f"Hash {hh[:8]}...")[:80], "magnet": f"magnet:?xt=urn:btih:{hh}"})

    def push_magnet(raw: str, title: str = "") -> None:
        raw = urllib.parse.unquote((raw or "").strip())
        if not raw:
            return
        ih = BTIH_RE.search(raw)
        if ih:
            hh = decode_btih_hash(ih.group(1))
            if hh and hh not in seen:
                seen.add(hh)
                magnets.append({"title": title[:80], "magnet": f"magnet:?xt=urn:btih:{hh}"})
            return
        match = MAGNET_RE.search(raw)
        if match:
            magnet = match.group(0)[:150]
            magnets.append({"title": title[:80], "magnet": magnet})

    for a in soup.find_all("a", href=lambda h: h and "magnet:" in h):
        push_magnet(a.get("href", ""), a.get_text(strip=True))

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        push_magnet(href, a.get_text(strip=True))
        for m in HASH40_RE.finditer(href):
            push_hash(m.group(0), a.get_text(strip=True))
        for m in HASH32_RE.finditer(href.upper()):
            push_hash(m.group(0), a.get_text(strip=True))

    decoded_text = urllib.parse.unquote(soup.get_text(" ", strip=True))
    for m in HASH40_RE.finditer(decoded_text):
        push_hash(m.group(0))
    for m in BTIH_RE.finditer(decoded_text):
        push_hash(m.group(1))

    for tag in soup.find_all(True):
        title = tag.get_text(" ", strip=True)
        for attr_value in tag.attrs.values():
            values = attr_value if isinstance(attr_value, list) else [attr_value]
            for value in values:
                if not isinstance(value, str):
                    continue
                push_magnet(value, title)
                for m in HASH40_RE.finditer(value):
                    push_hash(m.group(0), title)
                for m in HASH32_RE.finditer(value.upper()):
                    push_hash(m.group(0), title)

    for script in soup.find_all("script"):
        script_text = script.string or script.get_text(" ", strip=True)
        if not script_text:
            continue
        push_magnet(script_text)
        for m in BTIH_RE.finditer(script_text):
            push_hash(m.group(1))
        for m in HASH40_RE.finditer(script_text):
            push_hash(m.group(0))

    return magnets


def find_detail_links(html: str, base_url: str) -> List[str]:
    """Find detail page links from search results."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    links = []
    base_host = urllib.parse.urlparse(base_url).hostname or ""
    skip_patterns = re.compile(
        r"/(favorites|tags?|category|categories|nav|sites?|about|contact|help|policy|terms|login|register|user|forum|topics?|comment|share)",
        re.I,
    )
    detail_patterns = re.compile(
        r"/(torrent|view|info|detail|show|movie|resource|hash|files?|article|post|thread|dy|download|play|video|torrents)/",
        re.I,
    )

    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(full_url)

        # Skip navigation links
        if skip_patterns.search(parsed.path):
            continue
        # Skip external links
        if parsed.hostname and parsed.hostname != base_host:
            continue
        # Skip anchors and javascript
        if href.startswith("#") or href.startswith("javascript:"):
            continue

        # Look for detail-like paths
        if detail_patterns.search(parsed.path):
            links.append(full_url)

        # Also consider links with long hex paths (hash-based URLs like btsow)
        hex_path = re.search(r"/([0-9A-Fa-f]{40})", parsed.path)
        if hex_path:
            links.append(full_url)

    return list(dict.fromkeys(links))[:5]  # dedupe, max 5


def extract_handoff_links(html: str, base_url: str) -> List[str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    base_host = urllib.parse.urlparse(base_url).hostname or ""
    scored = []
    seen = set()
    skip_hosts = ("google.cn", "alookweb.com", "xbext.com")

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        full_url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(full_url)
        host = parsed.hostname or ""
        if not host or host == base_host:
            continue
        if any(host.endswith(skip) for skip in skip_hosts):
            continue
        if full_url in seen:
            continue
        text = a.get_text(" ", strip=True)
        score = 0
        if any(token in host.lower() for token in ("cili", "bt", "torrent", "so", "xingqiu", "kitty")):
            score += 3
        if any(token in text.lower() for token in ("镜像", "搜索", "磁力", "种子", "bt")):
            score += 2
        if score <= 0:
            continue
        seen.add(full_url)
        scored.append((score, full_url))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _, url in scored[:3]]


def is_thin_handoff_page(html: str, base_url: str) -> bool:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    if len(text) > 400:
        return False
    if soup.find("form") or soup.find("input"):
        return False
    handoffs = extract_handoff_links(html, base_url)
    return len(handoffs) >= 1


def classify_aux_site(html: str, base_url: str) -> Optional[Dict[str, Any]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    handoff_links = extract_handoff_links(html, base_url)
    if is_thin_handoff_page(html, base_url):
        return {
            "category": "jump",
            "reason": "thin_handoff_page",
            "candidate_origins": handoff_links,
            "text_len": len(text),
        }

    base_host = urllib.parse.urlparse(base_url).hostname or ""
    external_links = []
    internal_links = []
    hash_links = []
    javascript_links = []
    for a in soup.find_all("a", href=True):
        raw_href = a.get("href", "").strip()
        if raw_href.startswith("#"):
            hash_links.append(raw_href)
        if raw_href.startswith("javascript:"):
            javascript_links.append(raw_href)
        full_url = urllib.parse.urljoin(base_url, raw_href)
        parsed = urllib.parse.urlparse(full_url)
        if not parsed.hostname:
            continue
        if parsed.hostname == base_host:
            internal_links.append(full_url)
        else:
            external_links.append(full_url)

    title = (soup.title.get_text(" ", strip=True) if soup.title else "").lower()
    text_lower = text.lower()
    nav_tokens = ("导航", "网站", "发布页", "最新地址", "收藏", "推荐", "网址大全", "入口", "镜像")
    if (
        any(token in title or token in text_lower for token in ("导航", "导航网站", "网址导航"))
        and (len(hash_links) >= 8 or len(javascript_links) >= 3)
        and len(internal_links) >= 20
    ):
        return {
            "category": "navigation",
            "reason": "nav_portal_internal_catalog",
            "candidate_origins": list(dict.fromkeys(internal_links))[:20],
            "text_len": len(text),
        }

    if (
        not soup.find("form")
        and not soup.find("input")
        and len(set(external_links)) >= 8
        and len(set(internal_links)) <= 3
        and any(token in title or token in text_lower for token in nav_tokens)
    ):
        return {
            "category": "navigation",
            "reason": "nav_hub_external_links",
            "candidate_origins": list(dict.fromkeys(external_links))[:12],
            "text_len": len(text),
        }

    return None


def classify_aux_site_via_http(origin: str, timeout: int = 12) -> Optional[Dict[str, Any]]:
    try:
        resp = requests.get(
            origin,
            timeout=timeout,
            allow_redirects=True,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.encoding = "utf-8"
        return classify_aux_site(resp.text or "", origin)
    except Exception:
        return None


def wait_for_dom_stable(page, timeout_ms=3000):
    """Wait for DOM to be stable (no new nodes for timeout_ms)."""
    try:
        page.evaluate("""(timeout) => {
            return new Promise(resolve => {
                let timer = setTimeout(resolve, timeout);
                const observer = new MutationObserver(() => {
                    clearTimeout(timer);
                    timer = setTimeout(resolve, timeout);
                });
                observer.observe(document.body, { childList: true, subtree: true });
                setTimeout(() => { observer.disconnect(); resolve(); }, timeout * 3);
            });
        }""", timeout_ms)
    except Exception:
        page.wait_for_timeout(timeout_ms)


def try_interactive_search(page, origin: str, query: str, timeout: int = 15) -> Optional[str]:
    """Try interactive search: find input, type query, click button/Enter."""
    try:
        page.goto(origin, wait_until="domcontentloaded", timeout=timeout * 1000)
        wait_for_dom_stable(page, 2000)

        # Find search input
        input_sel = 'input[type="text"], input[type="search"], input[name*="search"], input[name*="query"], input[name*="kw"], input[name*="wd"], input[name*="word"], input[name*="q"], input[placeholder*="搜索"], input[placeholder*="search"]'
        inputs = page.query_selector_all(input_sel)

        if not inputs:
            return None

        # Type query into first visible input
        for inp in inputs:
            if inp.is_visible():
                inp.click()
                inp.fill(query)
                break
        else:
            return None

        # Try clicking search button
        btn_sel = 'button[type="submit"], input[type="submit"], button:has-text("搜索"), button:has-text("Search"), button:has-text("搜"), a:has-text("搜索"), a:has-text("Search")'
        btn = page.query_selector(btn_sel)
        if btn and btn.is_visible():
            btn.click()
        else:
            submitted = False
            try:
                submitted = inp.evaluate("""el => {
                    if (el.form) {
                        if (typeof el.form.requestSubmit === "function") {
                            el.form.requestSubmit();
                        } else {
                            el.form.submit();
                        }
                        return true;
                    }
                    return false;
                }""")
            except Exception:
                submitted = False
            if not submitted:
                page.keyboard.press("Enter")

        # Wait for results
        wait_for_dom_stable(page, 3000)
        page.wait_for_timeout(1000)

        return page.content()

    except Exception as e:
        log.info(f"    interactive_search err: {str(e)[:60]}")
        return None


def try_url_search(page, origin: str, template: str, query: str, timeout: int = 15) -> Optional[str]:
    """Try loading a search URL directly."""
    url = origin.rstrip("/") + template.replace("{q}", urllib.parse.quote(query))
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        page.wait_for_timeout(1500)
        return page.content()
    except Exception:
        # Retry with domcontentloaded
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            wait_for_dom_stable(page, 2000)
            return page.content()
        except Exception as e:
            return None


def try_detail_follow(page, detail_url: str, timeout: int = 10) -> Optional[str]:
    """Visit a detail page and extract content."""
    try:
        page.goto(detail_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        wait_for_dom_stable(page, 2000)
        page.wait_for_timeout(1000)
        return page.content()
    except Exception:
        return None


def verify_source_with_browser(page, origin: str, brand: str = "", timeout: int = 15) -> Dict[str, Any]:
    """Verify a single source using browser — optimized for speed.

    Strategy order (fastest first):
      1. Load homepage, interactive search (fill input + submit)
      2. If no search box found, try top 3 URL templates with 1 query
      3. Detail page follow if search results have no magnet but have detail links
    """
    result = {
        "origin": origin,
        "brand": brand,
        "magnets": [],
        "best_path": None,
        "best_method": None,
        "tried": [],
        "thin_handoff": False,
        "handoff_links": [],
        "aux_classification": None,
    }
    origins_to_try = [origin]

    try:
        page.goto(origin, wait_until="domcontentloaded", timeout=timeout * 1000)
        wait_for_dom_stable(page, 2000)
        home_html = page.content()
        result["aux_classification"] = classify_aux_site(home_html, origin)
        if not result["aux_classification"]:
            result["aux_classification"] = classify_aux_site_via_http(origin, timeout=timeout)
        if is_thin_handoff_page(home_html, origin):
            handoff_links = extract_handoff_links(home_html, origin)
            if handoff_links:
                result["thin_handoff"] = True
                result["handoff_links"] = handoff_links
                result["tried"].append({"method": "handoff", "origin": origin, "links": handoff_links})
                for handoff in handoff_links:
                    if handoff not in origins_to_try:
                        origins_to_try.append(handoff)
    except Exception as e:
        result["tried"].append({"method": "home_probe_error", "origin": origin, "error": str(e)[:80]})

    # ── Strategy 1: Interactive search (prioritize for JS sites) ──
    for active_origin in origins_to_try:
        for query in BAIT_QUERIES[:2]:  # just 2 queries
            if result["magnets"]:
                break
            html = try_interactive_search(page, active_origin, query, timeout=12)
            if html:
                magnets = extract_magnets(html)
                result["tried"].append({"method": "interactive", "origin": active_origin, "query": query, "found": len(magnets)})
                if magnets:
                    result["magnets"] = magnets
                    result["best_path"] = "interactive"
                    result["best_method"] = "interactive_search"
                    break

                # Detail page follow from interactive results
                detail_links = find_detail_links(html, active_origin)
                for dl in detail_links[:2]:
                    detail_html = try_detail_follow(page, dl, timeout=8)
                    if detail_html:
                        dm = extract_magnets(detail_html)
                        if dm:
                            result["magnets"] = dm
                            result["best_path"] = "interactive"
                            result["best_method"] = "interactive+detail"
                            break
        if result["magnets"]:
            break

    # ── Strategy 2: URL-based search (fallback, only top 3 templates) ──
    if not result["magnets"]:
        # Pick top templates based on site type
        top_templates = ["/search?q={q}", "/search/{q}", "/?q={q}"]
        # If Chinese brand, add Chinese patterns
        if brand and re.search(r'[一-鿿]', brand):
            top_templates = ["/search?word={q}", "/?q={q}", "/s?wd={q}"]

        for active_origin in origins_to_try:
            for query in BAIT_QUERIES[:2]:
                if result["magnets"]:
                    break
                for template in top_templates:
                    if result["magnets"]:
                        break
                    html = try_url_search(page, active_origin, template, query, timeout=10)
                    if html:
                        magnets = extract_magnets(html)
                        result["tried"].append({"method": "url", "origin": active_origin, "template": template, "query": query, "found": len(magnets)})
                        if magnets:
                            result["magnets"] = magnets
                            result["best_path"] = template
                            result["best_method"] = "url_search"
                            break

                        # Detail page follow
                        detail_links = find_detail_links(html, active_origin)
                        for dl in detail_links[:2]:
                            detail_html = try_detail_follow(page, dl, timeout=8)
                            if detail_html:
                                dm = extract_magnets(detail_html)
                                if dm:
                                    result["magnets"] = dm
                                    result["best_path"] = template
                                    result["best_method"] = "url+detail"
                                    break
                if result["magnets"]:
                    break
            if result["magnets"]:
                break

    return result


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
        value = f"https://{value}"
    parsed = urllib.parse.urlparse(value)
    if not parsed.netloc:
        return value.rstrip("/")
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return normalized


def main():
    parser = argparse.ArgumentParser(description="Browser Green Push v2 - deep verify yellow sources")
    parser.add_argument("--start", type=int, default=0, help="Start index")
    parser.add_argument("--limit", type=int, default=0, help="Max sources to verify (0=all)")
    parser.add_argument("--timeout", type=int, default=20, help="Per-page timeout (seconds)")
    parser.add_argument("--update", action="store_true", help="Update sources.json")
    parser.add_argument("--candidates", default="", help="Verify candidate JSON instead of yellow sources")
    parser.add_argument("--origin", action="append", default=[], help="Only verify specific origin(s), repeatable or comma-separated")
    parser.add_argument("--rule-id", action="append", default=[], help="Only verify specific rule id(s), repeatable or comma-separated")
    parser.add_argument("--out", default="", help="Output report path")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    log.info("=" * 60)
    log.info("  Browser Green Push v2 — 深度浏览器验证")
    log.info("=" * 60)

    # Load targets
    targets = []  # list of (origin, brand, rule_index_or_None)

    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        sources_data = json.load(f)

    target_origins = {normalize_origin_arg(v) for v in parse_csv_args(args.origin)}
    target_rule_ids = set(parse_csv_args(args.rule_id))

    if args.candidates:
        with open(args.candidates, "r", encoding="utf-8") as f:
            cand_data = json.load(f)
        cands = cand_data if isinstance(cand_data, list) else cand_data.get("candidates", [])
        for c in cands:
            url = c.get("url", c.get("origin", ""))
            name = c.get("name", c.get("brand", ""))
            if url:
                origin = url.rstrip("/") if url.startswith("http") else f"https://{url}"
                norm_origin = normalize_origin_arg(origin)
                if target_origins and norm_origin not in target_origins:
                    continue
                targets.append((origin, name, None))
    else:
        # Load yellow sources
        rules = sources_data["rulesets"][0]["rules"]
        for i, r in enumerate(rules):
            if r["health"]["status"] == "yellow":
                origin = r["site"]["origin"]
                rule_id = r.get("id", "")
                norm_origin = normalize_origin_arg(origin)
                if target_rule_ids and rule_id not in target_rule_ids:
                    continue
                if target_origins and norm_origin not in target_origins:
                    continue
                brand = r["site"].get("brand", r["site"].get("name", ""))
                targets.append((origin, brand, i))

    if args.start > 0:
        targets = targets[args.start:]
    if args.limit > 0:
        targets = targets[:args.limit]

    log.info(f"Targets: {len(targets)}")
    if target_rule_ids:
        log.info(f"Rule filter: {sorted(target_rule_ids)}")
    if target_origins:
        log.info(f"Origin filter: {sorted(target_origins)}")

    report = {"started_at": datetime.now(timezone.utc).isoformat(), "results": []}
    promoted = 0
    new_rules = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()

        for idx, (origin, brand, rule_idx) in enumerate(targets):
            log.info(f"[{idx + 1}/{len(targets)}] {brand or origin}")

            result = verify_source_with_browser(page, origin, brand, args.timeout)
            report["results"].append(result)

            if result["magnets"]:
                count = len(result["magnets"])
                log.info(f"  GREEN! {count} magnets (method={result['best_method']} path={result['best_path']})")
                for m in result["magnets"][:3]:
                    log.info(f"    {m['title'][:60]}")

                if rule_idx is not None:
                    # Update existing rule
                    rule = sources_data["rulesets"][0]["rules"][rule_idx]
                    rule["health"]["status"] = "green"
                    rule["health"]["status_detail"] = "ok"
                    rule["health"]["magnets_found"] = count
                    rule["health"]["sample_title"] = result["magnets"][0].get("title", "")[:80]
                    rule["health"]["last_checked_at"] = datetime.now(timezone.utc).isoformat()
                    rule["health"]["diagnosis"] = f"browser_green_push verified: {count} magnets (method={result['best_method']}, path={result['best_path']})"
                    if result["best_path"] and result["best_path"] != "interactive":
                        rule["search"]["request_template"] = result["best_path"]
                    rule["search"]["requires_browser"] = True
                    rule["quality"]["score"] = max(rule["quality"].get("score", 50), 65)
                    promoted += 1
                else:
                    # New rule
                    domain = urllib.parse.urlparse(origin).hostname or brand
                    rule_id = hashlib.md5(domain.encode()).hexdigest()[:12]
                    new_rule = {
                        "id": rule_id,
                        "site": {
                            "name": brand or domain,
                            "origin": origin,
                            "countries": ["china"],
                        },
                        "capabilities": {"supports_search": True, "supports_detail": False},
                        "search": {
                            "request_template": result["best_path"] if result["best_path"] != "interactive" else "/search?q={query}",
                            "timeout_ms": 20000,
                            "retries": {"max_attempts": 3, "backoff_ms": 1000},
                            "requires_waf_bypass": False,
                            "requires_browser": True,
                            "extraction_method": "selenium" if result["best_method"] and "interactive" in result["best_method"] else "browser-hash",
                            "parse_metadata": {
                                "selectors": {
                                    "list_item": "div.item",
                                    "title": "a[href]",
                                    "magnet": "a[href^=\"magnet:\"]",
                                    "size": "span.size",
                                    "date": "span.date",
                                }
                            },
                        },
                        "quality": {"score": 65, "tags": ["追新极客"]},
                        "health": {
                            "status": "green",
                            "status_detail": "ok",
                            "last_checked_at": datetime.now(timezone.utc).isoformat(),
                            "magnets_found": count,
                            "sample_title": result["magnets"][0].get("title", "")[:80],
                            "diagnosis": f"browser_green_push verified: {count} magnets (method={result['best_method']}, path={result['best_path']})",
                        },
                    }
                    if brand:
                        new_rule["site"]["brand"] = brand
                    new_rules.append(new_rule)
                    promoted += 1
            else:
                # Check homepage for keywords
                try:
                    page.goto(origin, wait_until="domcontentloaded", timeout=10000)
                    page.wait_for_timeout(1500)
                    html = page.content()
                    lower = html[:10000].lower()
                    has_kw = any(kw in lower for kw in ["magnet:", "torrent", "种子", "磁力", "btih"])
                    tries_info = f"tried={len(result['tried'])} paths"
                    aux = result.get("aux_classification")
                    if aux:
                        category = aux.get("category", "jump")
                        reason = aux.get("reason", "aux_site")
                        log.info(f"  AUX-{category.upper()}: {reason}. {tries_info}")
                        if rule_idx is not None:
                            rule = sources_data["rulesets"][0]["rules"][rule_idx]
                            now_iso = datetime.now(timezone.utc).isoformat()
                            rule["health"]["status"] = "gray"
                            rule["health"]["status_detail"] = "expired"
                            rule["health"]["note"] = f"aux_site:{category}:{reason}"
                            rule["health"]["last_checked_at"] = now_iso
                            rule["health"]["diagnosis"] = f"classified as {category} site; use auxiliary discovery pipeline"
                            upsert_aux_site(
                                category,
                                {
                                    "origin": origin,
                                    "brand": brand,
                                    "source_rule_id": rule.get("id"),
                                    "source_name": rule.get("site", {}).get("name"),
                                    "reason": reason,
                                    "candidate_origins": aux.get("candidate_origins", []),
                                    "last_checked_at": now_iso,
                                },
                            )
                    elif has_kw:
                        log.info(f"  No magnets but has keywords. {tries_info}")
                        if rule_idx is not None:
                            rule = sources_data["rulesets"][0]["rules"][rule_idx]
                            rule["health"]["status_detail"] = "parsing_failed"
                            rule["health"]["note"] = "browser_verified_has_keywords_but_no_magnet_extracted"
                            rule["health"]["last_checked_at"] = datetime.now(timezone.utc).isoformat()
                    else:
                        log.info(f"  No magnets, no keywords. {tries_info}")
                        if rule_idx is not None:
                            rule = sources_data["rulesets"][0]["rules"][rule_idx]
                            rule["health"]["status"] = "gray"
                            rule["health"]["status_detail"] = "expired"
                            rule["health"]["last_checked_at"] = datetime.now(timezone.utc).isoformat()
                except Exception as e:
                    estr = str(e)[:60]
                    if "ERR_CONNECTION" in estr or "ERR_NAME" in estr or "Timeout" in estr:
                        log.info(f"  UNREACHABLE: {estr}")
                        if rule_idx is not None:
                            rule = sources_data["rulesets"][0]["rules"][rule_idx]
                            rule["health"]["status"] = "gray"
                            rule["health"]["status_detail"] = "unreachable"
                            rule["health"]["last_checked_at"] = datetime.now(timezone.utc).isoformat()

            time.sleep(0.3)

        browser.close()

    # Save report
    report_path = args.out or os.path.join(ROOT_DIR, "browser_green_push_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    # Update sources.json
    if args.update:
        rules = sources_data["rulesets"][0]["rules"]
        domains_in_sources = set()
        for r in rules:
            o = r["site"].get("origin", "")
            p = urllib.parse.urlparse(o)
            domains_in_sources.add(p.hostname or r["site"]["name"])

        added = 0
        for nr in new_rules:
            nd = urllib.parse.urlparse(nr["site"]["origin"]).hostname or nr["site"]["name"]
            if nd not in domains_in_sources:
                rules.append(nr)
                domains_in_sources.add(nd)
                added += 1

        sources_data["meta"]["total_rules"] = len(rules)
        sources_data["generated_at"] = datetime.now(timezone.utc).isoformat()
        with open(SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(sources_data, f, indent=2, ensure_ascii=False)

        log.info(f"Updated sources.json: {promoted} promoted, {added} new added")

        # Validate
        try:
            import subprocess
            r = subprocess.run([sys.executable, os.path.join(ROOT_DIR, "validate_enum.py")], capture_output=True, text=True, timeout=30)
            log.info(f"validate_enum: {r.stdout.strip()}")
        except Exception as e:
            log.info(f"validate_enum failed: {e}")

    # Summary
    green = sum(1 for rs in sources_data.get("rulesets", []) for r in rs.get("rules", [])
                if r.get("health", {}).get("status") == "green")
    yellow = sum(1 for rs in sources_data.get("rulesets", []) for r in rs.get("rules", [])
                 if r.get("health", {}).get("status") == "yellow")
    gray = sum(1 for rs in sources_data.get("rulesets", []) for r in rs.get("rules", [])
               if r.get("health", {}).get("status") == "gray")

    log.info(f"\n{'=' * 60}")
    log.info(f"  Promoted to green: {promoted}")
    log.info(f"  Status: green={green} yellow={yellow} gray={gray} total={green + yellow + gray}")
    log.info(f"  Target: 38+ green (need {max(0, 38 - green)} more)")
    log.info(f"{'=' * 60}")


if __name__ == "__main__":
    main()
