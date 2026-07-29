#!/usr/bin/env python3
"""
K30S Automated Search Test
===========================
Controls a K30S phone (serial a1ea223a) via ADB to perform searches on the
MagGoogo debug app, collect per-source results, and produce a summary report.

Usage:
    python scripts/test_k30s_search.py

Prerequisites:
    - ADB installed and on PATH
    - K30S connected and authorized
    - MagGoogo debug app installed (com.magnetgoogo.app.debug)
"""

import argparse
import atexit
import re
import shlex
import subprocess
import json
import time
import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
from datetime import datetime
from pathlib import Path

from audit_source_delivery import audit_static

# ── Configuration ────────────────────────────────────────────────────────
SERIAL = "a1ea223a"
PACKAGE = "com.magnetgoogo.app.debug"
ACTIVITY = "com.magnetgoogo.app.MainActivity"
SCHEME = "magnetgoogo"
REPORT_PATH = f"/data/data/{PACKAGE}/files/last-search-report.json"
# This DCloud test app on the dedicated K30S periodically steals foreground
# focus. It is only force-stopped during MagGoogo validation; it is never
# uninstalled or cleared.
FOREGROUND_INTERFERERS = ("uni.UNIB56C11F",)

# UX-path smoke queries keep routine K30S checks short.
UX_QUERIES = [
    ("EN movie", "Inception"),
    ("ZH movie", "流浪地球"),
    ("ZH anime", "海贼王"),
    ("EN series", "Breaking Bad"),
]

# Full initial-prior benchmark: broad languages/content types plus a
# code-like title. Run with --benchmark so every host loaded by the App runtime
# is tested. This may be a subset of the wider static sources.json inventory.
BENCHMARK_QUERIES = [
    ("EN movie", "Inception"),
    ("ZH movie", "流浪地球"),
    ("EN anime", "One Piece"),
    ("ZH anime", "海贼王"),
    ("EN series", "Breaking Bad"),
    ("ZH series", "权力的游戏"),
    ("Software", "Ubuntu"),
    ("Code title", "SSIS-001"),
]

VALIDATION_QUERIES = [
    ("EN movie popular", "Inception"),
    ("EN movie classic", "The Matrix"),
    ("EN movie niche", "The Lighthouse"),
    ("ZH movie popular", "流浪地球"),
    ("ZH movie action", "战狼"),
    ("ZH movie animation", "哪吒"),
    ("EN series crime", "Breaking Bad"),
    ("EN series fantasy", "Game of Thrones"),
    ("ZH series sci-fi", "三体"),
    ("ZH series costume", "庆余年"),
    ("KR series", "Squid Game"),
    ("JP series", "Alice in Borderland"),
    ("EN anime", "One Piece"),
    ("ZH anime One Piece", "海贼王"),
    ("JP anime", "進撃の巨人"),
    ("ZH anime Demon Slayer", "鬼灭之刃"),
    ("Game EN", "GTA V"),
    ("Game ZH", "原神"),
    ("Software Linux", "Ubuntu"),
    ("Software Windows", "Windows 11"),
    ("Software Office", "Office 2021"),
    ("Code JAV", "SSIS-001"),
    ("Code JAV alt", "MIDV-001"),
    ("Mixed quality", "三体 4K"),
]

QUERIES = UX_QUERIES
BENCHMARK_MODE = False
VALIDATION_MODE = False
COLD_START_MODE = False
APPEND_MODE = False
COMPACT_OUTPUT = False
OUTPUT_PATH: Path | None = None
PROJECT_ROOT = Path(__file__).resolve().parent.parent

POLL_INTERVAL = 3       # seconds between logcat checks
MAX_WAIT      = 120     # max seconds to wait for a search to finish
ADB_BASE      = ["adb", "-s", SERIAL]


# ── Helpers ──────────────────────────────────────────────────────────────

def adb(*args, timeout=30):
    """Run an ADB command and return stdout."""
    cmd = ADB_BASE + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        stdout = r.stdout.decode("utf-8", errors="ignore")
        return stdout.strip(), r.returncode
    except subprocess.TimeoutExpired as e:
        print(f"  [WARN] ADB command timed out: {cmd}")
        return "", -1
    except Exception as e:
        print(f"  [WARN] ADB command failed: {e}")
        return "", -2


def adb_shell(*args, timeout=30):
    """Run `adb shell <args>`."""
    return adb("shell", *args, timeout=timeout)


def check_device():
    """Verify the device is reachable."""
    out, rc = adb("devices")
    if SERIAL not in out:
        print(f"[ERROR] Device {SERIAL} not found. Is it connected and authorized?")
        print(f"  adb devices output:\n{out}")
        sys.exit(1)
    print(f"[OK] Device {SERIAL} is connected.")


def prepare_device_for_foreground_search():
    """Wake/unlock K30S and keep it awake so foreground validation does not
    accidentally hand off after the first pool stage."""
    for package in FOREGROUND_INTERFERERS:
        adb_shell("am", "force-stop", package)
    adb_shell("input", "keyevent", "224")  # KEYCODE_WAKEUP
    adb_shell("wm", "dismiss-keyguard")
    adb_shell("svc", "power", "stayon", "true")
    time.sleep(0.5)


def stop_task_pin():
    """Leave Android screen-pinning mode after a test run."""
    adb_shell("am", "task", "lock", "stop")


def pin_app_task() -> bool:
    """Pin the active MagGoogo task so repeated launcher taps on the dedicated
    K30S cannot send the foreground search into a background handoff."""
    # The external launcher tap can race the deep-link start. Stop the
    # interfering task once more and synchronously bring MagGoogo to front
    # immediately before resolving and pinning its task ID.
    for package in FOREGROUND_INTERFERERS:
        adb_shell("am", "force-stop", package)
    adb_shell("am", "start", "-n", f"{PACKAGE}/{ACTIVITY}")
    out, rc = adb_shell("dumpsys", "activity", "activities")
    match = re.search(
        rf"Task\{{[^\n]*#(\d+)[^\n]*{re.escape(PACKAGE)}",
        out,
    )
    if rc != 0 or not match:
        print("  [WARN] Could not resolve MagGoogo task for screen pinning.")
        return False
    adb_shell("am", "task", "lock", match.group(1))
    time.sleep(0.5)
    state, _ = adb_shell("dumpsys", "activity", "activities")
    pinned = "mLockTaskModeState=PINNED" in state
    active = PACKAGE in next((line for line in state.splitlines() if "mResumedActivity:" in line), "")
    if not pinned or not active:
        print(f"  [WARN] Foreground pin failed: pinned={pinned} active={active}")
        return False
    return True


def check_app():
    """Verify the debug app is installed."""
    out, rc = adb_shell("pm", "list", "packages", PACKAGE)
    if PACKAGE not in out:
        print(f"[ERROR] Package {PACKAGE} is not installed on the device.")
        sys.exit(1)
    print(f"[OK] App {PACKAGE} is installed.")


def force_stop():
    """Force stop the app."""
    adb_shell("am", "force-stop", PACKAGE)
    time.sleep(1)


def launch_with_deeplink(query: str) -> bool:
    """Try launching via deep link. Returns True on success."""
    import urllib.parse
    encoded = urllib.parse.quote(query)
    uri = f"{SCHEME}:///search?q={encoded}"
    if BENCHMARK_MODE:
        uri += "&benchmark=1"
    if COLD_START_MODE:
        uri += "&cold=1"
    # `adb shell` invokes a remote shell; quote the whole URI so `&benchmark`
    # remains part of the deep link instead of becoming a shell separator.
    quoted_uri = shlex.quote(uri)
    out, rc = adb_shell(
        "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", quoted_uri,
        f"{PACKAGE}/{ACTIVITY}",
        timeout=15,
    )
    # am start prints "Error:" if intent can't be resolved
    if "Error:" in out or "error" in out.lower():
        print(f"  [WARN] Deep link failed: {out}")
        return False
    return True


def launch_app():
    """Launch the app normally (cold start)."""
    adb_shell(
        "am", "start",
        "-n", f"{PACKAGE}/{ACTIVITY}",
        timeout=15,
    )
    time.sleep(3)


def type_in_search(query: str):
    """Tap the search input, clear, type the query, and press Enter.

    Falls back to ADB input if deep links don't work.
    This is a best-effort approach -- coordinates are approximate
    and may need tuning for the specific device/resolution.
    """
    print(f"  [INPUT] Using ADB input fallback for query: {query}")

    # Tap on the search area (approximate center-top of screen)
    # K30S is 1080x2400, search bar ~ y=150
    adb_shell("input", "tap", "540", "150")
    time.sleep(0.5)

    # Select all existing text and delete
    adb_shell("input", "keyevent", "29", "--longpress")  # KEYCODE_A (select all via Ctrl+A)
    time.sleep(0.2)
    adb_shell("input", "keyevent", "67")  # DEL
    time.sleep(0.3)

    # Type the query (URL-encode for ADB input)
    # ADB input text doesn't handle spaces or CJK well, so we broadcast
    # the text via a special intent or use am broadcast with IME
    # For simplicity: use ADBKeyboard or the base64 approach
    import base64
    b64 = base64.b64encode(query.encode("utf-8")).decode("ascii")
    # Try ADBKeyboard broadcast (common test setup)
    out, rc = adb_shell(
        "am", "broadcast",
        "-a", "ADB_INPUT_TEXT",
        "--es", "msg", b64,
        timeout=10,
    )
    if rc != 0 or "Broadcast completed" not in out:
        # Fallback: raw input text (works for ASCII only)
        safe = query.replace(" ", "%s").replace("&", "\\&")
        adb_shell("input", "text", safe, timeout=10)

    time.sleep(0.5)

    # Press Enter (KEYCODE_ENTER = 66)
    adb_shell("input", "keyevent", "66")


def delete_remote_report():
    """Delete the remote report file before starting a search."""
    try:
        adb_shell("run-as", PACKAGE, "rm", "files/last-search-report.json")
    except Exception as e:
        print(f"  [WARN] Failed to delete remote report: {e}")


def wait_for_search_complete(expected_query: str) -> bool:
    """Poll the device filesystem for the new search report JSON file.

    Returns True when found and parsed with matching query, False on timeout.
    """
    start = time.time()
    while time.time() - start < MAX_WAIT:
        try:
            # Check if file exists
            out, rc = adb_shell("run-as", PACKAGE, "ls", "files/last-search-report.json")
            if rc == 0 and "last-search-report.json" in out:
                # Try to read and parse the report
                report_data = pull_report()
                if (
                    report_data
                    and report_data.get("query") == expected_query
                    and report_data.get("completed") is True
                ):
                    return True
        except Exception as e:
            print(f"    [WARN] File check failed: {e}")
        elapsed = int(time.time() - start)
        print(f"    ... waiting ({elapsed}s / {MAX_WAIT}s)", end="\r")
        time.sleep(POLL_INTERVAL)
    print()
    return False


def pull_report() -> dict | None:
    """Pull the last-search-report.json from the device.

    Uses `run-as` to read from the app's private files directory.
    """
    out, rc = adb_shell(
        "run-as", PACKAGE, "cat", "files/last-search-report.json",
        timeout=15,
    )
    if rc != 0 or not out.strip():
        # Fallback: try via adb shell su
        out, rc = adb_shell("su", "-c", f"cat {REPORT_PATH}", timeout=10)
    if not out.strip():
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        print(f"  [WARN] Failed to parse report JSON: {e}")
        print(f"  Raw: {out[:500]}")
        return None


# ── Report formatting ────────────────────────────────────────────────────

def format_duration(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def relevant_count(source: dict) -> int:
    if isinstance(source.get("relevantResultCount"), int):
        return max(0, source["relevantResultCount"])
    return sum(1 for item in source.get("items", []) if item.get("relevance", 0) >= 30)


def unique_count(source: dict) -> int:
    if isinstance(source.get("uniqueResultCount"), int):
        return max(0, source["uniqueResultCount"])
    return max(0, source.get("resultCount", 0))


PURE_HASH_TITLE_RE = re.compile(r"^(?:[a-f0-9]{32,64}|[a-z2-7]{32})$", re.I)
HASH_LABEL_TITLE_RE = re.compile(
    r"^(?:hash|btih|info[-_\s]?hash)\s*[:：=]?\s*(?:[a-f0-9]{8,64}|[a-z2-7]{16,32})(?:\.{3}|…)?$",
    re.I,
)
BTIH_TITLE_RE = re.compile(r"^(?:magnet:\?\S*|urn:btih:|btih:)\s*[a-z0-9]+", re.I)


def is_hash_placeholder_title(title: str) -> bool:
    value = re.sub(r"\s+", " ", str(title or "")).strip()
    if not value:
        return False
    return bool(
        PURE_HASH_TITLE_RE.fullmatch(value)
        or HASH_LABEL_TITLE_RE.fullmatch(value)
        or BTIH_TITLE_RE.match(value)
    )


def hash_title_findings(report: dict) -> list[dict]:
    findings: list[dict] = []
    for source in report.get("sourceResults", []):
        titles = [str(item.get("title", "")) for item in source.get("items", [])]
        if not titles:
            titles = [str(title) for title in source.get("sampleTitles", [])]
        for title in titles:
            if is_hash_placeholder_title(title):
                findings.append({
                    "source": source.get("name", "?"),
                    "origin": source.get("origin", ""),
                    "title": title,
                })
    return findings


def print_single_report(report: dict, label: str):
    """Print a single search report summary."""
    print(f"\n{'='*60}")
    print(f"  [{label}] Query: \"{report.get('query', '?')}\"")
    print(f"  Duration: {format_duration(report.get('totalDurationMs', 0))}")
    print(f"  Status: {'completed' if report.get('completed') else 'PARTIAL'}")
    sources = report.get("sourceResults", [])
    relevant = sum(relevant_count(source) for source in sources)
    pools = {source.get("poolId") for source in sources if source.get("poolId")}
    inventory = report.get("inventory") or {}
    loaded_hosts = inventory.get("loadedHostCount", 0)
    loaded_pools = inventory.get("loadedPoolCount", 0)
    attempted_hosts = report.get("attemptedHostCount", len(sources))
    attempted_pools = report.get("attemptedPoolCount", len(pools))
    print(f"  Total magnets: {report.get('totalMagnets', 0)}")
    print(f"  High-relevance results: {relevant}")
    print(f"  Runtime loaded hosts / pools: {loaded_hosts} / {loaded_pools}")
    print(f"  Attempted hosts / pools: {attempted_hosts} / {attempted_pools}")
    print(f"  Source pack: {inventory.get('sourcePackOrigin', '-')}")
    print(f"  Sources: {report.get('resultCount', 0)} with results, "
          f"{report.get('emptyCount', 0)} empty, "
          f"{report.get('errorCount', 0)} errors, "
          f"{report.get('skippedCount', 0)} skipped")
    print(f"  Fastest: {report.get('fastestSource', '-')}")
    hash_findings = hash_title_findings(report)
    print(f"  Hash placeholder titles: {len(hash_findings)}")
    print(f"  Most results: {report.get('mostResultsSource', '-')}")
    print(f"{'='*60}")

    # Per-source breakdown. "Relevant" uses the same >=30 threshold as the App.
    if sources and not COMPACT_OUTPUT:
        print(f"  {'Source':<23} {'Status':<8} {'Raw':>4} {'Rel':>4} {'Prec':>5} {'Time':<7} {'Pool':<16} {'Sample'}")
        print(f"  {'-'*23} {'-'*8} {'-'*4} {'-'*4} {'-'*5} {'-'*7} {'-'*16} {'-'*32}")
        for s in sources:
            name = s.get("name", "?")[:23]
            status = s.get("status", "?")
            count = unique_count(s)
            relevant = relevant_count(s)
            precision = f"{(relevant / count * 100):.0f}%" if count else "--"
            dur = format_duration(s.get("durationMs", 0))
            pool = (s.get("poolId") or "-")[:16]
            sample = (s.get("sampleTitles") or [""])[0][:32]
            icon = {"ok": "Y", "empty": "O", "error": "X", "timeout": "T", "skipped": "-"}.get(status, "?")
            detail = sample if status == "ok" and count > 0 else (s.get("error") or "")[:32]
            print(f"  {icon} {name:<21} {status:<8} {count:>4} {relevant:>4} {precision:>5} {dur:<7} {pool:<16} {detail}")


def print_summary_table(all_reports: list[tuple[str, dict | None]]):
    """Print an aggregated summary table across all queries."""
    # Collect all source names that returned results
    print("\n")
    print("=" * 80)
    print("  AGGREGATED SEARCH TEST SUMMARY")
    print(f"  Device: {SERIAL}  |  App: {PACKAGE}")
    print(f"  Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Query-level summary
    print(f"\n  {'Label':<12} {'Query':<16} {'Raw':>6} {'Relevant':>8} {'Hosts':>6} {'Pools':>6} {'Errors':>6} {'Duration':>9} {'Status'}")
    print(f"  {'-'*12} {'-'*16} {'-'*6} {'-'*8} {'-'*6} {'-'*6} {'-'*6} {'-'*9} {'-'*8}")
    for label, report in all_reports:
        if report is None:
            print(f"  {label:<12} {'N/A':<16} {'--':>6} {'--':>8} {'--':>6} {'--':>6} {'--':>6} {'--':>9} FAILED")
            continue
        q = report.get("query", "?")[:16]
        sources = report.get("sourceResults", [])
        raw = report.get("totalMagnets", 0)
        relevant = sum(relevant_count(source) for source in sources)
        pools = len({source.get("poolId") for source in sources if source.get("poolId")})
        errs = report.get("errorCount", 0)
        dur = format_duration(report.get("totalDurationMs", 0))
        st = "OK" if report.get("completed") else "PARTIAL"
        print(f"  {label:<12} {q:<16} {raw:>6} {relevant:>8} {len(sources):>6} {pools:>6} {errs:>6} {dur:>9} {st}")

    # Source x Query matrix uses high-relevance unique counts, not raw volume.
    source_map: dict[str, dict[str, int]] = {}  # source -> {label: relevant count}
    for label, report in all_reports:
        if report is None:
            continue
        for s in report.get("sourceResults", []):
            name = s.get("name", "?")
            if name not in source_map:
                source_map[name] = {}
            relevant = relevant_count(s)
            if s.get("status") == "ok" and relevant > 0:
                source_map[name][label] = relevant

    if source_map and not COMPACT_OUTPUT:
        labels = [label for label, _ in all_reports]
        # Sort sources by total hits across all queries
        sorted_sources = sorted(
            source_map.items(),
            key=lambda kv: sum(kv[1].values()),
            reverse=True,
        )

        print(f"\n  Source x Query Matrix (high-relevance unique counts):")
        header = f"  {'Source':<25}"
        for label in labels:
            header += f" {label:>10}"
        header += f" {'TOTAL':>8}"
        print(header)
        print(f"  {'-'*25}" + f" {'-'*10}" * len(labels) + f" {'-'*8}")

        for name, hits in sorted_sources[:20]:  # top 20 sources
            row = f"  {name:<25}"
            total = 0
            for label in labels:
                c = hits.get(label, 0)
                total += c
                row += f" {c:>10}" if c > 0 else f" {'--':>10}"
            row += f" {total:>8}"
            print(row)

    # Cross-query source reliability
    reliable = [(n, h) for n, h in source_map.items() if len(h) >= len(all_reports) * 0.5]
    if reliable and not COMPACT_OUTPUT:
        print(f"\n  Reliable sources (returned results for >= 50% of queries):")
        for name, hits in sorted(reliable, key=lambda kv: len(kv[1]), reverse=True):
            print(f"    {name}: {len(hits)}/{len(all_reports)} queries")

    print("\n" + "=" * 80)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  K30S Automated Search Test")
    print(f"  Device: {SERIAL}")
    print(f"  Queries: {len(QUERIES)}")
    print("=" * 60)

    # Preflight checks
    check_device()
    check_app()
    atexit.register(stop_task_pin)
    stop_task_pin()
    prepare_device_for_foreground_search()

    all_reports: list[tuple[str, dict | None]] = []
    use_deeplink = True  # Will flip to False if deep links fail

    for i, (label, query) in enumerate(QUERIES, 1):
        print(f"\n{'─'*60}")
        print(f"  [{i}/{len(QUERIES)}] Testing: {label} — \"{query}\"")
        print(f"{'─'*60}")

        # Force stop between runs for a clean state. Wake again because long
        # exhaustive batches can otherwise let MIUI lock the screen.
        stop_task_pin()
        prepare_device_for_foreground_search()
        force_stop()
        delete_remote_report()
        time.sleep(1)

        launched = False
        if use_deeplink:
            print("  [LAUNCH] Trying deep link...")
            launched = launch_with_deeplink(query)
            if not launched:
                print("  [FALLBACK] Deep link failed. Switching to ADB input mode.")
                use_deeplink = False

        if not launched:
            # Fallback: launch app then type
            launch_app()
            time.sleep(2)  # Wait for app to load
            type_in_search(query)
            time.sleep(1)

        if not pin_app_task():
            print("  [ERROR] Cannot guarantee foreground execution; rejecting this run.")
            all_reports.append((label, None))
            continue

        # Wait for search to complete
        print("  [WAIT] Polling filesystem for search completion...")
        found = wait_for_search_complete(query)

        if found:
            print("  [OK] Search report found on device filesystem.")
        else:
            print(f"  [TIMEOUT] Search did not complete within {MAX_WAIT}s.")

        # Pull the report (even on timeout -- might be partial)
        time.sleep(2)  # Give report file time to flush
        print("  [PULL] Reading report from device...")
        report = pull_report()

        if report:
            all_reports.append((label, report))
            print_single_report(report, label)
        else:
            print("  [ERROR] Could not read search report from device.")
            all_reports.append((label, None))

    stop_task_pin()

    # Final aggregated report
    print_summary_table(all_reports)
    current_hash_findings = [
        {"label": label, **finding}
        for label, report in all_reports
        if isinstance(report, dict)
        for finding in hash_title_findings(report)
    ]
    if current_hash_findings:
        print(f"\n  [FAIL] Found {len(current_hash_findings)} Hash placeholder title(s):")
        for finding in current_hash_findings[:20]:
            print(
                f"    {finding['label']} | {finding['source']} | "
                f"{finding['origin']} | {finding['title']}"
            )
    else:
        print("\n  [OK] Hash placeholder title gate: 0")

    # Save raw reports to local file. Benchmark batches can be appended safely.
    out_path = OUTPUT_PATH or (Path(__file__).resolve().parent / "k30s_search_results.json")
    existing_reports: dict[str, dict | None] = {}
    if APPEND_MODE and out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(existing.get("reports"), dict):
                existing_reports.update(existing["reports"])
        except Exception as exc:
            print(f"  [WARN] Could not append existing report: {exc}")
    existing_reports.update({label: r for label, r in all_reports})
    ordered_suite = BENCHMARK_QUERIES if BENCHMARK_MODE else VALIDATION_QUERIES if VALIDATION_MODE else UX_QUERIES
    ordered_labels = [label for label, _ in ordered_suite]
    ordered_reports = {
        label: existing_reports[label]
        for label in ordered_labels
        if label in existing_reports
    }
    for label, report in existing_reports.items():
        if label not in ordered_reports:
            ordered_reports[label] = report

    static_inventory = audit_static(PROJECT_ROOT / "sources.json")
    runtime_inventories = [
        report.get("inventory")
        for report in ordered_reports.values()
        if isinstance(report, dict) and isinstance(report.get("inventory"), dict)
    ]
    payload = {
        "device": SERIAL,
        "run_at": datetime.now().isoformat(),
        "mode": "exhaustive-benchmark" if BENCHMARK_MODE else "cross-category-validation" if VALIDATION_MODE else "ux-path",
        "cold_start_mode": COLD_START_MODE,
        "inventory": {
            "static": static_inventory,
            "runtime_loaded_host_counts": sorted({item.get("loadedHostCount", 0) for item in runtime_inventories}),
            "runtime_loaded_pool_counts": sorted({item.get("loadedPoolCount", 0) for item in runtime_inventories}),
            "source_pack_origins": sorted({item.get("sourcePackOrigin", "") for item in runtime_inventories if item.get("sourcePackOrigin")}),
        },
        "quality_gates": {
            "hash_placeholder_title_count": len(current_hash_findings),
            "hash_placeholder_titles": current_hash_findings,
        },
        "reports": ordered_reports,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Raw results saved to: {out_path}")
    if current_hash_findings:
        raise SystemExit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run K30S search quality tests.")
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run the broad bait suite in exhaustive host mode for initial source ranking.",
    )
    parser.add_argument(
        "--validation",
        action="store_true",
        help="Run the 24-query cross-category cold-start validation suite.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Run only the named query label; repeat for multiple labels.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Merge this batch into an existing output report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "k30s_search_results.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--cold-start",
        action="store_true",
        help="Ignore persisted local source learning without deleting app data.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Keep console output concise while preserving full JSON reports.",
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=None,
        help="Per-query completion timeout in seconds.",
    )
    args = parser.parse_args()
    if args.benchmark and args.validation:
        parser.error("--benchmark and --validation are mutually exclusive")
    if args.benchmark:
        QUERIES = BENCHMARK_QUERIES
        BENCHMARK_MODE = True
        MAX_WAIT = max(MAX_WAIT, 180)
    elif args.validation:
        QUERIES = VALIDATION_QUERIES
        VALIDATION_MODE = True
        COLD_START_MODE = True
        MAX_WAIT = min(MAX_WAIT, 45)
    if args.only:
        wanted = set(args.only)
        unknown = wanted - {label for label, _ in QUERIES}
        if unknown:
            parser.error(f"unknown labels for selected mode: {sorted(unknown)}")
        QUERIES = [item for item in QUERIES if item[0] in wanted]
    if not QUERIES:
        parser.error("no queries selected")
    APPEND_MODE = args.append
    COLD_START_MODE = COLD_START_MODE or args.cold_start
    COMPACT_OUTPUT = args.compact
    OUTPUT_PATH = args.output
    if args.max_wait is not None:
        MAX_WAIT = max(1, args.max_wait)
    main()
