#!/usr/bin/env python3
"""
Batch green-push: systematically try to convert yellow sources to green
and verify new candidates, using multi-path HTTP search with multiple
bait queries. Focuses on finding working search paths that yield
magnet links or 40-char btih hashes.
"""

import json
import os
import re
import sys
import time
import hashlib
import base64
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

MAGNET_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(MAGNET_DIR)
SOURCES_PATH = os.path.join(ROOT_DIR, "sources.json")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5,zh-CN;q=0.3",
})

# Multiple bait queries covering different content categories
BAIT_QUERIES = [
    "Inception", "Avatar", "Interstellar", "The Dark Knight",
    "Big Buck Bunny", "Sintel", "Tears of Steel",
    "One Piece", "Naruto",
    "Fedora", "Ubuntu",
    "Interstellar 2014",
]

# Extended search path templates to try for each domain
SEARCH_TEMPLATES = [
    "/search?q={query}",
    "/search/{query}",
    "/s/?q={query}",
    "/s/{query}",
    "/?q={query}",
    "/?s={query}",
    "/search?word={query}",
    "/search?query={query}",
    "/search?kw={query}",
    "/index.php?q={query}",
    "/index.php?search={query}",
    "/search/{query}/1.html",
    "/search/{query}/1/",
    "/so/{query}",
    "/find?kw={query}",
    "/list?keyword={query}",
    "/search.html?q={query}",
    "/api/search?q={query}",
    "/search/result?keyword={query}",
]

# Patterns that indicate magnet/hash evidence
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[a-zA-Z0-9]+', re.I)
HASH40_RE = re.compile(r'\b[a-fA-F0-9]{40}\b')
HASH32_RE = re.compile(r'\b[A-Z2-7]{32}\b')
BTIH_RE = re.compile(r'btih[:=]([A-Za-z2-7]{32}|[a-fA-F0-9]{40})', re.I)
BASE32_HASH_RE = re.compile(r'urn:btih:([A-Z2-7]{32})', re.I)

# Patterns indicating site is not a real search engine
PARKING_RE = re.compile(r'(domain.*for\s*sale|hugedomains|parked|buy\s*this\s*domain|godaddy|namecheap|sedo|afternic|lander)', re.I)
NAV_ONLY_RE = re.compile(r'(导航|nav|目录|收藏|友情链接|links|bookmarks)', re.I)
CLOUDFLARE_RE = re.compile(r'(just\s*a\s*moment|cloudflare|checking.your.browser|cf-browser)', re.I)


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


def extract_evidence(html: str, url: str) -> Dict[str, Any]:
    """Extract magnet links and hashes from HTML content."""
    magnets = set()
    hashes = set()

    def push_hash(raw: str) -> None:
        h = decode_btih_hash(raw)
        if not h:
            return
        # Filter out obvious non-hashes (CSS colors, etc.)
        if not all(c in '0123456789ABCDEF' for c in h):
            return
        # Skip if it looks like a CSS hex color (all same digit pairs)
        if len(set(h[i:i+2] for i in range(0, 40, 2))) < 4:
            return
        hashes.add(h)
        magnets.add(f"magnet:?xt=urn:btih:{h}")

    def push_magnet(raw: str) -> None:
        raw = urllib.parse.unquote((raw or "").strip())
        if not raw:
            return
        btih = BTIH_RE.search(raw)
        if btih:
            hh = decode_btih_hash(btih.group(1))
            if hh:
                hashes.add(hh)
                magnets.add(f"magnet:?xt=urn:btih:{hh}")
                return
        m = MAGNET_RE.search(raw)
        if m:
            magnets.add(m.group(0))

    for text_blob in (html, urllib.parse.unquote(html)):
        for m in MAGNET_RE.finditer(text_blob):
            push_magnet(m.group(0))
        for m in BTIH_RE.finditer(text_blob):
            push_hash(m.group(1))
        for m in HASH40_RE.finditer(text_blob):
            push_hash(m.group(0))

    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(True):
        for attr_value in tag.attrs.values():
            values = attr_value if isinstance(attr_value, list) else [attr_value]
            for value in values:
                if isinstance(value, str):
                    push_magnet(value)
                    for m in HASH32_RE.finditer(value.upper()):
                        push_hash(m.group(0))

    for script in soup.find_all("script"):
        script_text = script.string or script.get_text(" ", strip=True)
        if script_text:
            push_magnet(script_text)
            for m in HASH32_RE.finditer(script_text.upper()):
                push_hash(m.group(0))

    return {"magnets": sorted(magnets), "hashes": sorted(hashes), "count": len(magnets)}


def is_parking_or_nav(html: str) -> Optional[str]:
    """Check if page is parking/navigation, not a real search engine."""
    if PARKING_RE.search(html):
        return "parking"
    if CLOUDFLARE_RE.search(html):
        return "cloudflare"
    return None


def probe_search(domain: str, template: str, query: str, timeout: int = 15) -> Dict[str, Any]:
    """Try a single search path and return evidence."""
    url = f"https://{domain}{template.format(query=urllib.parse.quote(query))}"
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True, verify=False)
        if r.status_code != 200:
            return {"url": url, "status": r.status_code, "evidence": None, "error": f"HTTP {r.status_code}"}

        html = r.text
        park = is_parking_or_nav(html)
        if park:
            return {"url": url, "status": 200, "evidence": None, "error": f"parking/{park}"}

        evidence = extract_evidence(html, url)
        if evidence["count"] > 0:
            return {"url": url, "status": 200, "evidence": evidence, "error": None}

        return {"url": url, "status": 200, "evidence": None, "error": "no_evidence"}
    except requests.exceptions.Timeout:
        return {"url": url, "status": 0, "evidence": None, "error": "timeout"}
    except requests.exceptions.ConnectionError:
        return {"url": url, "status": 0, "evidence": None, "error": "connection_error"}
    except Exception as e:
        return {"url": url, "status": 0, "evidence": None, "error": str(e)[:80]}


def verify_source(domain: str, existing_template: str = None) -> Dict[str, Any]:
    """Verify a source domain by trying multiple search paths and queries."""
    result = {
        "domain": domain,
        "reachable": False,
        "best_path": None,
        "best_evidence": None,
        "best_count": 0,
        "tried": [],
    }

    # Step 1: Homepage probe
    try:
        r = SESSION.get(f"https://{domain}/", timeout=10, allow_redirects=True, verify=False)
        if r.status_code == 200:
            result["reachable"] = True
            result["homepage_size"] = len(r.text)
            result["homepage_title"] = BeautifulSoup(r.text, 'html.parser').title.string if BeautifulSoup(r.text, 'html.parser').title else ""
            park = is_parking_or_nav(r.text)
            if park:
                result["parking"] = park
        elif r.status_code in (301, 302, 303, 307, 308):
            result["reachable"] = True
            result["redirect"] = r.headers.get('Location', '')
        else:
            result["homepage_status"] = r.status_code
    except requests.exceptions.Timeout:
        result["reachable"] = False
        result["error"] = "timeout"
        return result
    except requests.exceptions.ConnectionError:
        result["reachable"] = False
        result["error"] = "connection_error"
        return result
    except Exception as e:
        result["reachable"] = False
        result["error"] = str(e)[:80]
        return result

    if result.get("parking"):
        return result

    # Step 2: Try existing template first, then all templates
    templates_to_try = []
    if existing_template:
        # Normalize existing template
        t = existing_template.replace("{query}", "{query}")
        if t not in SEARCH_TEMPLATES:
            templates_to_try.append(t)
    templates_to_try.extend(SEARCH_TEMPLATES)

    # Try with 3 bait queries, stop at first success
    queries_to_try = BAIT_QUERIES[:5]

    for template in templates_to_try:
        for query in queries_to_try:
            probe = probe_search(domain, template, query)
            result["tried"].append({
                "template": template,
                "query": query,
                "status": probe["status"],
                "error": probe.get("error"),
                "evidence_count": probe["evidence"]["count"] if probe["evidence"] else 0,
            })
            if probe["evidence"] and probe["evidence"]["count"] > result["best_count"]:
                result["best_path"] = template
                result["best_evidence"] = probe["evidence"]
                result["best_count"] = probe["evidence"]["count"]
                result["best_url"] = probe["url"]
                if result["best_count"] >= 3:
                    # Good enough, stop trying
                    return result

    return result


def generate_rule(domain: str, path: str, evidence: Dict[str, Any], brand: str = None) -> Dict[str, Any]:
    """Generate a sources.json rule from verification result."""
    rule_id = hashlib.md5(domain.encode()).hexdigest()[:12]
    rule = {
        "id": rule_id,
        "site": {
            "name": brand or domain,
            "origin": f"https://{domain}",
            "countries": ["china"],
        },
        "capabilities": {
            "supports_search": True,
            "supports_detail": False,
        },
        "search": {
            "request_template": path,
            "timeout_ms": 15000,
            "retries": {"max_attempts": 3, "backoff_ms": 1000},
            "requires_waf_bypass": False,
            "requires_browser": False,
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
        "quality": {"score": 60, "tags": ["追新极客"]},
        "health": {
            "status": "green",
            "status_detail": "ok",
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
            "magnets_found": evidence["count"],
            "sample_title": evidence["magnets"][0][:80] if evidence["magnets"] else "",
            "diagnosis": f"batch_green_push verified: {evidence['count']} magnets (path={path})",
        },
    }
    if brand:
        rule["site"]["brand"] = brand
    return rule


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch green-push: convert yellow→green and verify new candidates")
    parser.add_argument("--candidates", help="JSON file with candidate URLs to verify")
    parser.add_argument("--yellow-only", action="store_true", help="Only verify existing yellow sources")
    parser.add_argument("--max-concurrent", type=int, default=5, help="Max concurrent requests")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of sources to verify (0=all)")
    parser.add_argument("--update-sources", action="store_true", help="Update sources.json with new green sources")
    parser.add_argument("--out", default="", help="Output report JSON path")
    args = parser.parse_args()

    # Suppress HTTPS warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    targets = []  # list of (domain, existing_template_or_None, brand_or_None)

    # Load yellow sources from sources.json
    with open(SOURCES_PATH, "r", encoding="utf-8") as f:
        sources = json.load(f)

    yellow_domains = []
    for rule in sources["rulesets"][0]["rules"]:
        if rule["health"]["status"] == "yellow":
            domain = rule["site"]["name"]
            origin = rule["site"]["origin"]
            template = rule["search"].get("request_template")
            brand = rule["site"].get("brand")
            # Extract domain from origin
            parsed = urllib.parse.urlparse(origin)
            hostname = parsed.hostname or domain
            yellow_domains.append((hostname, template, brand, rule["id"]))

    if args.yellow_only or not args.candidates:
        for d, t, b, _ in yellow_domains:
            targets.append((d, t, b))

    # Load external candidates
    if args.candidates:
        with open(args.candidates, "r", encoding="utf-8") as f:
            cand_data = json.load(f)
        cands = cand_data if isinstance(cand_data, list) else cand_data.get("candidates", [])
        for c in cands:
            url = c.get("url", c.get("origin", ""))
            name = c.get("name", c.get("brand", ""))
            parsed = urllib.parse.urlparse(url)
            hostname = parsed.hostname or parsed.netloc or name
            if hostname and hostname not in [t[0] for t in targets]:
                targets.append((hostname, None, name))

    if args.limit > 0:
        targets = targets[:args.limit]

    print(f"=== Batch Green Push ===")
    print(f"Targets: {len(targets)} ({len(yellow_domains)} yellow + {len(targets) - len(yellow_domains)} candidates)")

    report = {"started_at": datetime.now(timezone.utc).isoformat(), "results": []}
    new_green_rules = []
    upgraded_ids = set()

    with ThreadPoolExecutor(max_workers=args.max_concurrent) as pool:
        futures = {}
        for domain, template, brand in targets:
            f = pool.submit(verify_source, domain, template)
            futures[f] = (domain, template, brand)

        for f in as_completed(futures):
            domain, template, brand = futures[f]
            try:
                result = f.result()
            except Exception as e:
                result = {"domain": domain, "error": str(e)}

            best_count = result.get("best_count") or 0
            best_path = result.get("best_path") or "-"
            status = "GREEN" if best_count > 0 else ("PARKING" if result.get("parking") else ("UNREACHABLE" if not result.get("reachable") else "NO_EVIDENCE"))
            print(f"  {status:12s} {domain:30s} magnets={best_count:3d} path={best_path:30s}")

            report["results"].append(result)

            if result.get("best_count", 0) > 0 and result.get("best_path"):
                # Found evidence!
                rule = generate_rule(domain, result["best_path"], result["best_evidence"], brand)
                new_green_rules.append(rule)

                # Check if this is an upgrade of an existing yellow source
                for d2, _, _, rule_id in yellow_domains:
                    if d2 == domain:
                        upgraded_ids.add(rule_id)
                        break

    # Summary
    green_count = len(new_green_rules)
    print(f"\n=== Summary ===")
    print(f"Verified: {len(targets)}")
    print(f"New green: {green_count}")
    print(f"Upgraded yellow→green: {len(upgraded_ids)}")

    # Save report
    report_path = args.out or os.path.join(ROOT_DIR, "batch_green_push_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"Report: {report_path}")

    # Update sources.json if requested
    if args.update_sources and new_green_rules:
        rules = sources["rulesets"][0]["rules"]
        domains_in_sources = set()
        for r in rules:
            o = r["site"].get("origin", "")
            p = urllib.parse.urlparse(o)
            domains_in_sources.add(p.hostname or r["site"]["name"])

        added = 0
        upgraded = 0
        for new_rule in new_green_rules:
            nd = urllib.parse.urlparse(new_rule["site"]["origin"]).hostname or new_rule["site"]["name"]

            # Check if upgrading existing
            found_existing = False
            for i, r in enumerate(rules):
                o = r["site"].get("origin", "")
                rd = urllib.parse.urlparse(o).hostname or r["site"]["name"]
                if rd == nd:
                    # Upgrade existing rule
                    r["health"]["status"] = "green"
                    r["health"]["status_detail"] = "ok"
                    r["health"]["magnets_found"] = new_rule["health"]["magnets_found"]
                    r["health"]["last_checked_at"] = new_rule["health"]["last_checked_at"]
                    r["health"]["diagnosis"] = new_rule["health"]["diagnosis"]
                    if new_rule["search"]["request_template"] != r["search"].get("request_template"):
                        r["search"]["request_template"] = new_rule["search"]["request_template"]
                    r["quality"]["score"] = max(r["quality"].get("score", 50), 60)
                    upgraded += 1
                    found_existing = True
                    break

            if not found_existing and nd not in domains_in_sources:
                rules.append(new_rule)
                domains_in_sources.add(nd)
                added += 1

        sources["meta"]["total_rules"] = len(rules)
        with open(SOURCES_PATH, "w", encoding="utf-8") as f:
            json.dump(sources, f, ensure_ascii=False, indent=2)
        print(f"Updated sources.json: {upgraded} upgraded, {added} added, total={len(rules)}")

        # Run validate_enum.py
        try:
            import subprocess
            r = subprocess.run([sys.executable, os.path.join(ROOT_DIR, "validate_enum.py")], capture_output=True, text=True, timeout=30)
            print(f"validate_enum: {r.stdout.strip()}")
            if r.returncode != 0:
                print(f"validate_enum stderr: {r.stderr.strip()}")
        except Exception as e:
            print(f"validate_enum failed: {e}")


if __name__ == "__main__":
    main()
