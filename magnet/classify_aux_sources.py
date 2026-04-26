#!/usr/bin/env python3

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import List

import requests

from aux_site_registry import upsert_aux_site
from browser_green_push import classify_aux_site, normalize_origin_arg, parse_csv_args


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


def load_sources() -> dict:
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sources(data: dict) -> None:
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("meta", {})
    data["meta"]["total_rules"] = sum(len(rs.get("rules", [])) for rs in data.get("rulesets", []))
    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_html(origin: str, timeout: int) -> str:
    resp = requests.get(
        origin,
        timeout=timeout,
        allow_redirects=True,
        verify=False,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.encoding = "utf-8"
    return resp.text or ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify jump/navigation auxiliary sites and split them from magnet-source workflow")
    parser.add_argument("--origin", action="append", default=[], help="Origin(s) to classify, repeatable or comma-separated")
    parser.add_argument("--rule-id", action="append", default=[], help="Rule id(s) to classify, repeatable or comma-separated")
    parser.add_argument("--all-non-green", action="store_true", help="Classify all non-green sources")
    parser.add_argument("--timeout", type=int, default=18, help="HTTP timeout seconds")
    parser.add_argument("--update", action="store_true", help="Write classifications back to sources.json and aux registries")
    parser.add_argument("--out", default="", help="Output report path")
    args = parser.parse_args()

    target_origins = {normalize_origin_arg(v) for v in parse_csv_args(args.origin)}
    target_rule_ids = set(parse_csv_args(args.rule_id))

    data = load_sources()
    rules = data["rulesets"][0]["rules"]
    targets = []
    for idx, rule in enumerate(rules):
        origin = rule.get("site", {}).get("origin", "")
        norm_origin = normalize_origin_arg(origin)
        rule_id = rule.get("id", "")
        is_non_green = rule.get("health", {}).get("status") != "green"
        selected = args.all_non_green or rule_id in target_rule_ids or norm_origin in target_origins
        if selected and is_non_green:
            targets.append((idx, rule))

    log.info("=" * 60)
    log.info("  Auxiliary Site Classifier")
    log.info("=" * 60)
    log.info(f"Targets: {len(targets)}")

    report = {"started_at": datetime.now(timezone.utc).isoformat(), "results": []}
    updated = 0

    for idx, rule in targets:
        origin = rule["site"]["origin"]
        brand = rule["site"].get("brand", rule["site"].get("name", ""))
        log.info(f"[{len(report['results']) + 1}/{len(targets)}] {brand or origin}")
        result = {
            "rule_id": rule.get("id"),
            "origin": origin,
            "brand": brand,
            "status_before": rule.get("health", {}).get("status"),
            "classification": None,
        }
        try:
            html = fetch_html(origin, args.timeout)
            aux = classify_aux_site(html, origin)
            result["classification"] = aux
            if aux:
                log.info(f"  AUX-{aux['category'].upper()}: {aux['reason']}")
                if args.update:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    rule["health"]["status"] = "gray"
                    rule["health"]["status_detail"] = "expired"
                    rule["health"]["last_checked_at"] = now_iso
                    rule["health"]["note"] = f"aux_site:{aux['category']}:{aux['reason']}"
                    rule["health"]["diagnosis"] = f"classified as {aux['category']} site; use auxiliary discovery pipeline"
                    upsert_aux_site(
                        aux["category"],
                        {
                            "origin": origin,
                            "brand": brand,
                            "source_rule_id": rule.get("id"),
                            "source_name": rule.get("site", {}).get("name"),
                            "reason": aux["reason"],
                            "candidate_origins": aux.get("candidate_origins", []),
                            "last_checked_at": now_iso,
                        },
                    )
                    updated += 1
            else:
                log.info("  No aux classification")
        except Exception as e:
            result["error"] = str(e)
            log.info(f"  ERROR: {str(e)[:120]}")
        report["results"].append(result)

    report_path = args.out or os.path.join(ROOT_DIR, "aux_site_classifier_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if args.update:
        save_sources(data)
        try:
            import subprocess

            res = subprocess.run([sys.executable, os.path.join(ROOT_DIR, "validate_enum.py")], capture_output=True, text=True, timeout=30)
            log.info(res.stdout.strip())
        except Exception as e:
            log.info(f"validate_enum failed: {e}")

    log.info(f"Updated: {updated}")


if __name__ == "__main__":
    main()
