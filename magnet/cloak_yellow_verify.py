#!/usr/bin/env python3
"""
CloakBrowser Yellow Source Verifier
====================================
用 CloakBrowser (反检测 Chromium) 对 yellow 源执行真实搜索验证。

成功标准：
  1. 搜索结果标题含查询关键词（名称匹配）
  2. 搜索结果含 magnet 链接

用法:
  python magnet/cloak_yellow_verify.py "蜘蛛侠"
  python magnet/cloak_yellow_verify.py "Inception" --limit 5
  python magnet/cloak_yellow_verify.py "复仇者联盟" --origin wuqianso.org
  python magnet/cloak_yellow_verify.py "test" --update   # 验证 + 升级 green
"""

import sys
import os
import re
import json
import time
import argparse
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
SOURCES_FILE = os.path.join(ROOT_DIR, "sources.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "cloak_verify.log"), encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── CF Challenge detection ──
CF_MARKERS = ["请稍候", "Just a moment", "Checking your browser", "正在进行安全验证", "challenge-platform"]
MAX_CF_WAIT = 40

# ── Magnet extraction ──
MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:[A-Za-z0-9]{32,}", re.I)
BTIH_RE = re.compile(r"btih[:=]([A-Za-z2-7]{32}|[0-9A-Fa-f]{40})", re.I)


def safe_eval(page, expr, default=None):
    try:
        return page.evaluate(expr)
    except:
        return default


def wait_for_cf_pass(page, max_wait=MAX_CF_WAIT) -> bool:
    """Wait for CF Challenge to auto-resolve. Returns True if passed."""
    for i in range(max_wait):
        try:
            title = page.title()
            body_snippet = page.evaluate("document.body.innerText.substring(0, 300)")
            is_cf = any(m in (title + body_snippet) for m in CF_MARKERS)
            if not is_cf:
                return True
        except Exception as e:
            err = str(e)
            if "destroyed" in err or "navigation" in err.lower():
                # Page navigated — CF likely solved, wait for load
                time.sleep(2)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                    title = page.title()
                    if not any(m in title for m in CF_MARKERS):
                        return True
                except:
                    pass
        time.sleep(1)
    return False


def navigate_with_cf_bypass(page, url: str, timeout: int = 45) -> bool:
    """Navigate to URL, auto-bypass CF Challenge if present. Returns True if page loaded."""
    try:
        page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        time.sleep(2)
    except Exception as e:
        log.info(f"      goto error: {str(e)[:80]}")
        return False

    title = safe_eval(page, "document.title", "")
    if any(m in title for m in CF_MARKERS):
        log.info(f"      CF Challenge 检测到, 等待自动解决...")
        if not wait_for_cf_pass(page, MAX_CF_WAIT):
            log.info(f"      ❌ CF Challenge 未解决")
            return False
        log.info(f"      ✅ CF Challenge 已解决 ({safe_eval(page, 'document.title', '')})")
    return True


def extract_detail_links(page, base_url: str) -> List[str]:
    """Extract detail page links from search results."""
    try:
        return page.evaluate("""
            (baseUrl) => {
                const host = new URL(baseUrl).hostname;
                const basePath = new URL(baseUrl).pathname;
                const links = [];
                const seen = new Set();
                const detailRe = /\/(torrent|view|info|detail|show|hash|seed|doc|download|play|thread|resource)\//i;
                const hashRe = /\/[0-9A-Fa-f]{40}/;
                const shortIdRe = /^\/![A-Za-z0-9]{3,}/;
                const skipRe = /\/(search|page|tag|category|login|register|about|help|faq)/i;
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.href;
                    if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
                    try {
                        const u = new URL(href, baseUrl);
                        if (u.hostname !== host) return;
                        if (seen.has(u.pathname)) return;
                        if (u.pathname === '/' || u.pathname === basePath) return;
                        if (skipRe.test(u.pathname)) return;
                        seen.add(u.pathname);
                        if (detailRe.test(u.pathname) || hashRe.test(u.pathname) ||
                            shortIdRe.test(u.pathname) ||
                            (u.pathname.length > 10 && !u.pathname.endsWith('.html') && u.searchParams.size === 0)) {
                            links.push(href);
                        }
                    } catch(e) {}
                });
                return links.slice(0, 5);
            }
        """, base_url) or []
    except:
        return []


def extract_results_from_page(page, query: str) -> Dict[str, Any]:
    """Extract search results (titles + magnets) from current page."""
    html = safe_eval(page, "document.body.innerHTML", "")
    text = safe_eval(page, "document.body.innerText", "")
    if not html:
        return {"titles": [], "magnets": [], "html_len": 0, "detail_links": []}

    # Extract magnet links
    magnets = []
    seen_hashes = set()

    # Method 1: <a href="magnet:...">
    page_magnets = safe_eval(page, """
        () => {
            const links = document.querySelectorAll('a[href^="magnet:"]');
            return Array.from(links).map(a => ({
                magnet: a.href.substring(0, 200),
                title: (a.textContent || a.parentElement?.textContent || '').trim().substring(0, 100)
            }));
        }
    """, [])
    for m in (page_magnets or []):
        h = BTIH_RE.search(m.get("magnet", ""))
        if h and h.group(1) not in seen_hashes:
            seen_hashes.add(h.group(1))
            magnets.append(m)

    # Method 2: regex on full HTML
    for match in MAGNET_RE.finditer(html):
        h = BTIH_RE.search(match.group(0))
        if h and h.group(1) not in seen_hashes:
            seen_hashes.add(h.group(1))
            magnets.append({"magnet": match.group(0)[:200], "title": ""})

    # Method 3: btih hashes in text/links
    for match in BTIH_RE.finditer(html):
        hh = match.group(1).upper()
        if hh not in seen_hashes:
            seen_hashes.add(hh)
            magnets.append({"magnet": f"magnet:?xt=urn:btih:{hh}", "title": ""})

    # Extract titles that match query
    query_lower = query.lower()
    query_chars = set(query_lower)
    matching_titles = []

    # Get all text nodes that might be result titles
    candidate_titles = safe_eval(page, """
        () => {
            const sel = 'a[href], h3, h4, .item-title, .result-title, .torrent-title, .sbar a, div.item a, td a';
            const els = document.querySelectorAll(sel);
            return Array.from(els).map(e => e.textContent.trim()).filter(t => t.length > 3 && t.length < 200);
        }
    """, [])

    for t in (candidate_titles or []):
        t_lower = t.lower()
        if query_lower in t_lower or all(c in t_lower for c in query_chars if c.strip()):
            matching_titles.append(t[:100])

    detail_links = extract_detail_links(page, page.url)

    return {
        "titles": matching_titles[:20],
        "magnets": magnets[:30],
        "html_len": len(html),
        "detail_links": detail_links,
    }


def try_interactive_search(page, query: str) -> bool:
    """Try typing into search box and submitting."""
    input_sel = (
        'input[type="text"], input[type="search"], '
        'input[name*="search"], input[name*="query"], input[name*="kw"], '
        'input[name*="wd"], input[name*="word"], input[name*="q"], input[name*="keyword"], '
        'input[placeholder*="搜索"], input[placeholder*="search"], input[placeholder*="Search"]'
    )
    try:
        inputs = page.query_selector_all(input_sel)
        target_input = None
        for inp in inputs:
            if inp.is_visible():
                target_input = inp
                break
        if not target_input:
            return False

        target_input.click()
        time.sleep(0.3)
        target_input.fill(query)
        time.sleep(0.5)

        # Try button
        btn_sel = (
            'button[type="submit"], input[type="submit"], '
            'button:has-text("搜索"), button:has-text("Search"), '
            'a:has-text("搜索"), a.search-btn, .search-btn'
        )
        btn = page.query_selector(btn_sel)
        if btn and btn.is_visible():
            btn.click()
        else:
            page.keyboard.press("Enter")

        time.sleep(3)
        # Wait for potential CF on search results
        title = safe_eval(page, "document.title", "")
        if any(m in title for m in CF_MARKERS):
            log.info(f"      搜索触发 CF, 等待...")
            wait_for_cf_pass(page, MAX_CF_WAIT)
        time.sleep(2)
        return True
    except Exception as e:
        log.info(f"      interactive search err: {str(e)[:60]}")
        return False


def verify_source(page, source: dict, query: str) -> Dict[str, Any]:
    """Verify a single yellow source with CloakBrowser."""
    name = source["site"]["name"]
    origin = source["site"]["origin"].rstrip("/")
    # Remove ref params for cleaner origin
    parsed = urllib.parse.urlparse(origin)
    clean_origin = f"{parsed.scheme}://{parsed.netloc}"
    tmpl = source["search"].get("request_template", "")

    result = {
        "name": name,
        "origin": origin,
        "clean_origin": clean_origin,
        "query": query,
        "status": "fail",
        "method": None,
        "matching_titles": [],
        "magnets_found": 0,
        "sample_magnets": [],
        "elapsed": 0,
        "error": "",
    }

    t0 = time.time()

    # ── Strategy 1: Direct search URL ──
    if tmpl:
        encoded_query = urllib.parse.quote(query)
        search_url = clean_origin + tmpl.replace("{query}", encoded_query)
        log.info(f"    [Strategy 1] 直接搜索URL: {search_url}")

        if navigate_with_cf_bypass(page, search_url):
            time.sleep(2)
            final_url = page.url
            final_path = urllib.parse.urlparse(final_url).path.rstrip("/")
            origin_path = urllib.parse.urlparse(clean_origin).path.rstrip("/")
            # Check if redirected back to homepage
            is_homepage = (final_path == origin_path or final_path == "" or final_path == "/")
            if is_homepage and "search" not in final_url and "keyword" not in final_url and "wd" not in final_url:
                log.info(f"      被重定向到首页 ({final_url}), 尝试交互搜索...")
                # Fall through to Strategy 2
            else:
                data = extract_results_from_page(page, query)
                if data["magnets"]:
                    result["method"] = "direct_url"
                    result["matching_titles"] = data["titles"]
                    result["magnets_found"] = len(data["magnets"])
                    result["sample_magnets"] = data["magnets"][:5]
                    result["status"] = "pass" if data["titles"] else "magnets_only"
                    result["elapsed"] = round(time.time() - t0, 1)
                    return result
                # Detail-follow: search page has results but no magnet on page
                elif data["detail_links"] and data["html_len"] > 2000:
                    log.info(f"      搜索页无magnet, 尝试 detail-follow ({len(data['detail_links'])} links)...")
                    for dl in data["detail_links"][:3]:
                        log.info(f"        → {dl[:80]}")
                        if navigate_with_cf_bypass(page, dl, timeout=20):
                            time.sleep(2)
                            detail_data = extract_results_from_page(page, query)
                            if detail_data["magnets"]:
                                result["method"] = "direct_url+detail"
                                result["matching_titles"] = data["titles"] or detail_data["titles"]
                                result["magnets_found"] = len(detail_data["magnets"])
                                result["sample_magnets"] = detail_data["magnets"][:5]
                                result["status"] = "pass" if (data["titles"] or detail_data["titles"]) else "magnets_only"
                                result["elapsed"] = round(time.time() - t0, 1)
                                return result
                    log.info(f"      detail-follow 未找到 magnet")
                elif data["html_len"] > 3000:
                    body_text = safe_eval(page, "document.body.innerText.substring(0, 400)", "")
                    log.info(f"      页面有内容({data['html_len']}B)但无magnet且无detail链接")
                    log.info(f"      [DEBUG body]: {body_text[:200]}")

    # ── Strategy 2: Homepage + Interactive search ──
    log.info(f"    [Strategy 2] 首页+交互搜索")
    if navigate_with_cf_bypass(page, clean_origin):
        time.sleep(2)
        if try_interactive_search(page, query):
            time.sleep(2)
            data = extract_results_from_page(page, query)
            if data["magnets"]:
                result["method"] = "interactive"
                result["matching_titles"] = data["titles"]
                result["magnets_found"] = len(data["magnets"])
                result["sample_magnets"] = data["magnets"][:5]
                result["status"] = "pass" if data["titles"] else "magnets_only"
                result["elapsed"] = round(time.time() - t0, 1)
                return result
            # Detail-follow from interactive search
            elif data["detail_links"] and data["html_len"] > 2000:
                log.info(f"      交互搜索无magnet, detail-follow ({len(data['detail_links'])} links)...")
                for dl in data["detail_links"][:3]:
                    log.info(f"        → {dl[:80]}")
                    if navigate_with_cf_bypass(page, dl, timeout=20):
                        time.sleep(2)
                        detail_data = extract_results_from_page(page, query)
                        if detail_data["magnets"]:
                            result["method"] = "interactive+detail"
                            result["matching_titles"] = data["titles"] or detail_data["titles"]
                            result["magnets_found"] = len(detail_data["magnets"])
                            result["sample_magnets"] = detail_data["magnets"][:5]
                            result["status"] = "pass" if (data["titles"] or detail_data["titles"]) else "magnets_only"
                            result["elapsed"] = round(time.time() - t0, 1)
                            return result
            elif data["html_len"] > 3000:
                body_text = safe_eval(page, "document.body.innerText.substring(0, 400)", "")
                log.info(f"      交互搜索后有内容({data['html_len']}B)但无magnet")
                log.info(f"      [DEBUG body]: {body_text[:200]}")
                log.info(f"      [DEBUG url]: {page.url}")

        # ── Strategy 3: Navigate to search URL after homepage CF pass ──
        if tmpl:
            log.info(f"    [Strategy 3] CF后重试搜索URL")
            encoded_query = urllib.parse.quote(query)
            search_url = clean_origin + tmpl.replace("{query}", encoded_query)
            try:
                page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(3)
                title = safe_eval(page, "document.title", "")
                if any(m in title for m in CF_MARKERS):
                    log.info(f"      搜索页CF再次触发, 等待...")
                    wait_for_cf_pass(page, MAX_CF_WAIT)
                time.sleep(2)
                data = extract_results_from_page(page, query)
                if data["magnets"]:
                    result["method"] = "cf_bypass_then_url"
                    result["matching_titles"] = data["titles"]
                    result["magnets_found"] = len(data["magnets"])
                    result["sample_magnets"] = data["magnets"][:5]
                    result["status"] = "pass" if data["titles"] else "magnets_only"
                    result["elapsed"] = round(time.time() - t0, 1)
                    return result
            except Exception as e:
                log.info(f"      Strategy 3 error: {str(e)[:60]}")

    result["elapsed"] = round(time.time() - t0, 1)
    result["error"] = "no_magnets_found"
    return result


def main():
    parser = argparse.ArgumentParser(description="CloakBrowser Yellow Source Verifier")
    parser.add_argument("query", help="搜索关键词 (资源名称)")
    parser.add_argument("--limit", type=int, default=0, help="最多验证N个源 (0=全部)")
    parser.add_argument("--origin", default="", help="只验证指定origin (部分匹配)")
    parser.add_argument("--update", action="store_true", help="验证通过后更新sources.json为green")
    parser.add_argument("--headless", action="store_true", help="无头模式 (默认有头)")
    args = parser.parse_args()

    query = args.query.strip()
    if not query:
        print("请输入搜索关键词")
        sys.exit(1)

    # Load yellow sources
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        sources_data = json.load(f)
    rules = sources_data["rulesets"][0]["rules"]
    yellows = [r for r in rules if r.get("health", {}).get("status") == "yellow"]

    if args.origin:
        yellows = [r for r in yellows if args.origin.lower() in r["site"]["origin"].lower()
                   or args.origin.lower() in r["site"]["name"].lower()]

    if args.limit > 0:
        yellows = yellows[:args.limit]

    log.info("=" * 65)
    log.info(f"  CloakBrowser Yellow Source Verifier")
    log.info(f"  搜索关键词: {query}")
    log.info(f"  待验证源: {len(yellows)}")
    log.info("=" * 65)

    from cloakbrowser import launch

    results = []
    passed = 0

    for idx, source in enumerate(yellows):
        name = source["site"]["name"]
        origin = source["site"]["origin"]
        log.info(f"\n[{idx+1}/{len(yellows)}] {name} ({origin})")

        browser = None
        try:
            browser = launch(headless=args.headless, humanize=True)
            page = browser.new_page()
            r = verify_source(page, source, query)
            results.append(r)

            if r["status"] in ("pass", "magnets_only"):
                passed += 1
                icon = "✅" if r["status"] == "pass" else "⚠️"
                log.info(f"  {icon} {r['status'].upper()} | method={r['method']} | "
                         f"magnets={r['magnets_found']} | titles={len(r['matching_titles'])} | {r['elapsed']}s")
                for m in r["sample_magnets"][:3]:
                    title_str = m.get("title", "")[:50] or "(no title)"
                    magnet_str = m.get("magnet", "")[:60]
                    log.info(f"    📎 {title_str}")
                    log.info(f"       {magnet_str}...")
                if r["matching_titles"]:
                    log.info(f"    🔍 匹配标题: {r['matching_titles'][:3]}")
            else:
                log.info(f"  ❌ FAIL | {r['error']} | {r['elapsed']}s")

            page.close()
        except Exception as e:
            log.error(f"  ❌ 异常: {e}")
            results.append({
                "name": name, "origin": origin, "query": query,
                "status": "error", "error": str(e)[:100],
            })
        finally:
            if browser:
                try:
                    browser.close()
                except:
                    pass

    # ── Summary ──
    log.info(f"\n{'=' * 65}")
    log.info(f"  验证完成: {len(results)} 源, {passed} 通过")
    log.info(f"{'=' * 65}")

    for r in results:
        icon = "✅" if r["status"] == "pass" else "⚠️" if r["status"] == "magnets_only" else "❌"
        log.info(f"  {icon} {r['name']:30s} {r['status']:15s} magnets={r.get('magnets_found',0):3d} "
                 f"titles={len(r.get('matching_titles',[])):2d} {r.get('elapsed',0):.0f}s")

    # ── Update sources.json ──
    if args.update and passed > 0:
        now = datetime.now(timezone.utc).isoformat()
        updates = 0
        result_map = {}
        for r in results:
            if r["status"] in ("pass", "magnets_only"):
                # Map by cleaned origin
                parsed = urllib.parse.urlparse(r["origin"])
                clean = f"{parsed.scheme}://{parsed.netloc}"
                result_map[clean] = r
                result_map[r["origin"]] = r

        for rule in rules:
            origin = rule["site"]["origin"]
            parsed = urllib.parse.urlparse(origin)
            clean = f"{parsed.scheme}://{parsed.netloc}"

            r = result_map.get(origin) or result_map.get(clean)
            if not r:
                continue

            rule["health"]["status"] = "green"
            rule["health"]["status_detail"] = "healed"
            rule["health"]["last_checked_at"] = now
            rule["health"]["fail_streak"] = 0
            rule["health"]["magnets_found"] = r["magnets_found"]
            if r.get("sample_magnets"):
                rule["health"]["sample_title"] = r["sample_magnets"][0].get("title", "")[:80]
            rule["health"]["note"] = f"cloak_verify: {r['method']}, {r['magnets_found']} magnets, query={query}"
            rule["search"]["requires_browser"] = True
            updates += 1

        if updates > 0:
            with open(SOURCES_FILE, "w", encoding="utf-8") as f:
                json.dump(sources_data, f, indent=2, ensure_ascii=False)
            log.info(f"\n✓ sources.json 已更新: {updates} 源升级为 green")

    # Save report
    report_path = os.path.join(BASE_DIR, "cloak_verify_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "total": len(results),
            "passed": passed,
            "results": results,
        }, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"报告: {report_path}")


if __name__ == "__main__":
    main()
