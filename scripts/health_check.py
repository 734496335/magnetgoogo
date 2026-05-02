#!/usr/bin/env python3
"""
Source Health Check — 自动巡检所有 green/yellow 源的可达性和搜索能力。

用法:
  python scripts/health_check.py                  # 巡检 + 报告
  python scripts/health_check.py --update         # 巡检 + 更新 sources.json
  python scripts/health_check.py --deploy         # 巡检 + 更新 + 加密 + 推送

巡检策略:
  1. Homepage probe: GET origin → 200 + 非空?
  2. Search probe: GET search URL → 200 + list_item 选择器有命中?
  3. 特殊源跳过 search probe: custom handler / browser-required / CSRF
  4. 支持 referer 字段

降级保护机制 (2 层):
  Layer 1 — 单次巡检内重试: 探测失败后 retry MAX_RETRIES(3) 次，间隔递增
  Layer 2 — 跨巡检连续失败计数: health.fail_streak 记录连续失败次数，
           只有 fail_streak >= DEMOTE_THRESHOLD(3) 才实际降级。
           一次成功即清零。

状态转换规则:
  green + reachable                → green (ok),  fail_streak=0
  green + unreachable (streak<3)   → green (ok),  fail_streak++ [不降级]
  green + unreachable (streak>=3)  → yellow (unreachable) [降级]
  yellow + reachable               → green (healed),  fail_streak=0
  yellow + unreachable (streak<3)  → yellow,  fail_streak++
  yellow + unreachable (streak>=3) → gray (unreachable) [降级]
  gray 不巡检
"""

import json
import re
import sys
import time
import urllib3
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings()

# ── Config ──
SCRIPT_DIR = Path(__file__).parent
SOURCES_JSON = SCRIPT_DIR.parent / "sources.json"
REPORT_FILE = SCRIPT_DIR / "health_report.json"
TIMEOUT = 10
MAX_WORKERS = 12
TEST_QUERY = "spider"
MAX_RETRIES = 3          # Layer 1: retries within a single check
RETRY_BACKOFF = [2, 4]   # seconds between retries (len = MAX_RETRIES-1)
DEMOTE_THRESHOLD = 3     # Layer 2: consecutive failed checks before demotion

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}

# Custom handler 和 browser-required 源只检测首页可达性，不测搜索
SKIP_SEARCH = {"javbus", "6v520", "meijumi", "yhg", "rarbggo", "rrjav", "1337x"}


def probe_source(rule: dict) -> dict:
    """
    探测单个源，返回结果字典。
    """
    site = rule["site"]
    origin = site["origin"].rstrip("/")
    name = site["name"]
    search_cfg = rule.get("search", {})
    handler = search_cfg.get("handler", "")
    requires_browser = search_cfg.get("requires_browser", False)
    requires_csrf = search_cfg.get("requires_csrf", False)
    referer = search_cfg.get("referer", "")
    template = search_cfg.get("request_template", "")
    selectors = search_cfg.get("parse_metadata", {}).get("selectors", {})
    old_status = rule.get("health", {}).get("status", "gray")

    result = {
        "name": name,
        "origin": origin,
        "old_status": old_status,
        "homepage_ok": False,
        "homepage_status": 0,
        "homepage_time": 0,
        "search_ok": False,
        "search_results": 0,
        "search_time": 0,
        "search_skipped": False,
        "error": "",
        "new_status": old_status,
        "new_detail": rule.get("health", {}).get("status_detail", "ok"),
        "changed": False,
    }

    headers = {**HEADERS}
    if referer:
        headers["Referer"] = referer

    # ── Step 1: Homepage probe (with retries) ──
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            r = requests.get(origin, timeout=TIMEOUT, verify=False, headers=headers,
                             allow_redirects=True)
            dt = round(time.time() - t0, 2)
            result["homepage_status"] = r.status_code
            result["homepage_time"] = dt

            if r.status_code == 200 and len(r.text) > 200:
                result["homepage_ok"] = True
            elif r.status_code in (301, 302, 303, 307, 308):
                result["homepage_ok"] = r.status_code < 400
            elif r.status_code == 403:
                if "cloudflare" in r.text.lower() or "cf-" in r.text.lower():
                    result["homepage_ok"] = True
                    result["error"] = "cloudflare_protected"
        except requests.exceptions.Timeout:
            result["error"] = "timeout"
        except requests.exceptions.ConnectionError:
            result["error"] = "connection_error"
        except Exception as e:
            result["error"] = str(e)[:80]

        if result["homepage_ok"]:
            break  # success — no more retries
        if attempt < MAX_RETRIES - 1:
            wait = RETRY_BACKOFF[attempt] if attempt < len(RETRY_BACKOFF) else RETRY_BACKOFF[-1]
            time.sleep(wait)  # backoff before retry
            result["error"] = ""  # reset for next attempt

    # ── Step 2: Search probe (skip for special sources) ──
    skip_search = (
        handler in SKIP_SEARCH
        or requires_browser
        or requires_csrf
        or not template
    )

    if skip_search:
        result["search_skipped"] = True
        # If homepage is OK, search is assumed OK for special sources
        if result["homepage_ok"]:
            result["search_ok"] = True
    elif result["homepage_ok"]:
        try:
            from urllib.parse import quote
            search_url = origin + template.replace("{query}", quote(TEST_QUERY))
            search_url = search_url.replace("{query_b64}", "c3BpZGVy")  # base64("spider")

            t0 = time.time()
            r = requests.get(search_url, timeout=TIMEOUT, verify=False, headers=headers,
                             allow_redirects=True)
            dt = round(time.time() - t0, 2)
            result["search_time"] = dt

            if r.status_code == 200 and len(r.text) > 500:
                soup = BeautifulSoup(r.text, "lxml")
                list_sel = selectors.get("list_item", "")

                if list_sel:
                    items = soup.select(list_sel)
                    result["search_results"] = len(items)
                    result["search_ok"] = len(items) > 0
                else:
                    # No selector — just check for magnet hashes
                    hashes = re.findall(r'[a-fA-F0-9]{40}', r.text)
                    result["search_results"] = len(hashes)
                    result["search_ok"] = len(hashes) > 0

                if not result["search_ok"]:
                    # Fallback: check for any magnet links or btih patterns
                    magnets = re.findall(r'magnet:\?xt=urn:btih:', r.text)
                    if magnets:
                        result["search_ok"] = True
                        result["search_results"] = len(magnets)
            elif r.status_code == 403:
                # CF block on search — server is alive
                if "cloudflare" in r.text.lower():
                    result["search_ok"] = True
                    result["error"] = "cloudflare_search"
        except Exception as e:
            result["error"] = f"search_error: {str(e)[:60]}"

    # ── Step 3: Determine new status (with fail_streak protection) ──
    old_streak = rule.get("health", {}).get("fail_streak", 0)
    reachable = result["homepage_ok"] and (result["search_ok"] or result["search_skipped"])
    alive_no_search = result["homepage_ok"] and not result["search_ok"] and not result["search_skipped"]

    if reachable:
        # ✅ Healthy — reset fail streak
        result["fail_streak"] = 0
        if old_status == "green":
            result["new_status"] = "green"
            result["new_detail"] = "ok"
        elif old_status == "yellow":
            result["new_status"] = "green"
            result["new_detail"] = "healed"
            result["changed"] = True
        else:
            result["new_status"] = old_status
    elif alive_no_search:
        # ✅ Server alive, search failed (GFW / selector mismatch) — don't penalize
        result["fail_streak"] = 0
        if old_status == "green":
            result["new_status"] = "green"
            result["new_detail"] = "ok"
        elif old_status == "yellow":
            result["new_status"] = "yellow"
            result["new_detail"] = "parsing_failed"
    else:
        # ❌ Unreachable — increment fail streak
        new_streak = old_streak + 1
        result["fail_streak"] = new_streak

        if old_status == "green":
            if new_streak >= DEMOTE_THRESHOLD:
                result["new_status"] = "yellow"
                result["new_detail"] = "unreachable"
                result["changed"] = True
            else:
                # Hold green, just record the streak
                result["new_status"] = "green"
                result["new_detail"] = "ok"
                result["error"] = f"fail_streak={new_streak}/{DEMOTE_THRESHOLD} {result['error']}"
        elif old_status == "yellow":
            if new_streak >= DEMOTE_THRESHOLD:
                result["new_status"] = "gray"
                result["new_detail"] = "unreachable"
                result["changed"] = True
            else:
                result["new_status"] = "yellow"
                result["new_detail"] = "unreachable"
                result["error"] = f"fail_streak={new_streak}/{DEMOTE_THRESHOLD} {result['error']}"

    # Only flag as changed when the status field itself changes
    if result["new_status"] != old_status:
        result["changed"] = True

    return result


def run_health_check(sources_path: Path) -> list:
    """Run health check on all green/yellow sources."""
    data = json.loads(sources_path.read_text(encoding="utf-8"))
    rules = data["rulesets"][0]["rules"]

    # Filter to green and yellow
    targets = [
        r for r in rules
        if r.get("health", {}).get("status") in ("green", "yellow")
    ]

    print(f"Checking {len(targets)} sources ({MAX_WORKERS} workers)...")
    print(f"Test query: '{TEST_QUERY}'\n")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(probe_source, rule): rule
            for rule in targets
        }
        for i, future in enumerate(concurrent.futures.as_completed(future_map)):
            r = future.result()
            results.append(r)

            # Status indicator
            if r["changed"]:
                icon = "⚠️"
            elif r["homepage_ok"]:
                icon = "✅"
            else:
                icon = "❌"

            status_str = r["new_status"]
            if r["changed"]:
                status_str = f"{r['old_status']}→{r['new_status']}"

            search_str = ""
            if r["search_skipped"]:
                search_str = "search=skip"
            elif r["search_ok"]:
                search_str = f"results={r['search_results']}"
            else:
                search_str = "search=FAIL"

            streak_str = f"streak={r.get('fail_streak', 0)}" if r.get("fail_streak", 0) > 0 else ""
            print(f"  {icon} [{i+1:2d}/{len(targets)}] {r['name']:30s} {status_str:15s} "
                  f"home={r['homepage_status']:3d}/{r['homepage_time']:.1f}s "
                  f"{search_str:20s} {streak_str:10s} {r['error']}")

    return results


def apply_updates(sources_path: Path, results: list) -> int:
    """Apply health status updates to sources.json. Returns count of changes."""
    data = json.loads(sources_path.read_text(encoding="utf-8"))
    rules = data["rulesets"][0]["rules"]
    now = datetime.now(timezone.utc).isoformat()

    changes = 0
    result_map = {r["origin"]: r for r in results}

    for rule in rules:
        origin = rule.get("site", {}).get("origin", "").rstrip("/")
        if origin not in result_map:
            continue

        r = result_map[origin]
        old_health = rule.get("health", {})
        fail_streak = r.get("fail_streak", 0)

        if not r["changed"]:
            # No status change — still update last_checked_at + fail_streak
            old_health["last_checked_at"] = now
            old_health["fail_streak"] = fail_streak
            continue

        rule["health"] = {
            "status": r["new_status"],
            "status_detail": r["new_detail"],
            "last_checked_at": now,
            "fail_streak": fail_streak,
            "magnets_found": old_health.get("magnets_found", 0),
            "sample_title": old_health.get("sample_title", ""),
            "note": f"Auto health check: {r['old_status']}→{r['new_status']}. {r['error']}".strip(),
        }
        changes += 1

    if changes > 0:
        sources_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return changes


def print_summary(results: list):
    """Print summary report."""
    total = len(results)
    healthy = sum(1 for r in results if r["homepage_ok"])
    search_ok = sum(1 for r in results if r["search_ok"])
    changed = [r for r in results if r["changed"]]

    print(f"\n{'='*70}")
    print(f"  巡检完成: {total} 源检测, {healthy} 可达, {search_ok} 搜索正常")
    print(f"  状态变更: {len(changed)}")

    if changed:
        print(f"\n  变更详情:")
        for r in changed:
            print(f"    {r['name']:30s} {r['old_status']}→{r['new_status']} ({r['new_detail']}) {r['error']}")

    # Count by new status
    by_status = {}
    for r in results:
        s = r["new_status"]
        by_status[s] = by_status.get(s, 0) + 1
    print(f"\n  状态分布: {by_status}")
    print(f"{'='*70}")


def main():
    if not SOURCES_JSON.exists():
        print(f"✗ {SOURCES_JSON} not found")
        sys.exit(1)

    results = run_health_check(SOURCES_JSON)
    print_summary(results)

    # Save report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_query": TEST_QUERY,
        "total": len(results),
        "changes": [r for r in results if r["changed"]],
        "all_results": results,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告保存: {REPORT_FILE}")

    if "--update" in sys.argv or "--deploy" in sys.argv:
        changes = apply_updates(SOURCES_JSON, results)
        print(f"\n✓ sources.json 已更新 ({changes} 条变更)")

        if "--deploy" in sys.argv and changes > 0:
            print("\n加密并部署...")
            import subprocess
            subprocess.run(
                [sys.executable, str(SCRIPT_DIR.parent / "encrypt_sources.py"), "--deploy"],
                cwd=str(SCRIPT_DIR.parent),
                check=True,
            )


if __name__ == "__main__":
    main()
