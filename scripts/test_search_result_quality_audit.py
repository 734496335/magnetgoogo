#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_search_result_quality import audit_payload  # noqa: E402
from audit_source_delivery import audit_static  # noqa: E402
from magnet.health_check import MAGNET_RE, build_search_url, select_targets, source_result_key  # noqa: E402
from magnet.crawler_v3.handlers.ssbc import format_ssbc_size  # noqa: E402
from magnet.crawler_v3.tiers.tier0_http import has_valid_btih_magnet  # noqa: E402


def item(
    title: str = "Inception.2010.1080p.BluRay",
    hash_value: str = "a" * 40,
    size: str = "8.4 GB",
    date: str = "2026-07-31",
    file_count: int | None = 12,
    relevance: int = 100,
):
    return {
        "title": title,
        "hash": hash_value,
        "size": size,
        "date": date,
        "fileCount": file_count,
        "relevance": relevance,
    }


def source(name: str, origin: str, items: list[dict], status: str = "ok"):
    return {
        "name": name,
        "origin": origin,
        "poolId": name.lower(),
        "status": status,
        "resultCount": len(items),
        "uniqueResultCount": len(items),
        "relevantResultCount": len(items),
        "relevancePrecision": 1,
        "durationMs": 100,
        "sampleTitles": [entry["title"] for entry in items[:3]],
        "sampleHashes": [entry["hash"][:12] for entry in items[:3]],
        "items": items,
        "requiresWaf": False,
        "requiresBrowser": False,
        "qualityScore": 90,
    }


def report(sources: list[dict], loaded: int | None = None):
    return {
        "query": "Inception",
        "completed": True,
        "sourceResults": sources,
        "attemptedHostCount": len(sources),
        "inventory": {
            "benchmarkMode": True,
            "loadedHostCount": loaded if loaded is not None else len(sources),
        },
    }


class SearchResultAuditTests(unittest.TestCase):
    def test_good_per_source_and_cross_source_results_pass(self):
        payload = {
            "reports": {
                "q": report([
                    source("A", "https://a.example", [item()]),
                    source("B", "https://b.example", [item(title="盗梦空间 Inception 2010")]),
                ])
            }
        }
        result = audit_payload(payload, require_complete=True)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["hardFindingCount"], 0)
        self.assertEqual(result["uniqueAttemptedSources"], 2)

    def test_bad_title_hash_size_date_file_count_and_relevance_fail(self):
        bad = item(
            title="magnet:?xt=urn:btih:" + "b" * 40,
            hash_value="not-a-hash",
            size="7 B",
            date="27801.01 GB",
            file_count=-1,
            relevance=101,
        )
        result = audit_payload({"reports": {"q": report([source("Bad", "https://bad.example", [bad])])}})
        codes = set(result["findingCounts"])
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue({
            "HASH_PLACEHOLDER_TITLE",
            "INVALID_INFO_HASH",
            "SUSPICIOUS_SUB_KIB_SIZE",
            "INVALID_DATE_LABEL",
            "INVALID_FILE_COUNT",
            "INVALID_RELEVANCE",
        }.issubset(codes))

    def test_replacement_character_html_and_generic_titles_fail(self):
        items = [
            item(title="<b>Inception</b>", hash_value="1" * 40),
            item(title="Inception�2010", hash_value="2" * 40),
            item(title="download", hash_value="3" * 40),
        ]
        result = audit_payload({"reports": {"q": report([source("Bad", "https://bad.example", items)])}})
        codes = set(result["findingCounts"])
        self.assertTrue({"HTML_IN_TITLE", "MOJIBAKE_REPLACEMENT_CHAR", "GENERIC_TITLE"}.issubset(codes))

    def test_cross_source_size_conflict_fails(self):
        hash_value = "c" * 40
        result = audit_payload({
            "reports": {
                "q": report([
                    source("Small", "https://small.example", [item(hash_value=hash_value, size="24.7 MB")]),
                    source("Large", "https://large.example", [item(hash_value=hash_value, size="23.5 GB")]),
                ])
            }
        })
        self.assertIn("CROSS_SOURCE_SIZE_CONFLICT", result["findingCounts"])
        self.assertEqual(result["status"], "FAIL")

    def test_same_source_duplicate_hash_metadata_conflict_fails(self):
        hash_value = "d" * 40
        values = [
            item(hash_value=hash_value, size="2 GB"),
            item(hash_value=hash_value, size="20 GB"),
        ]
        result = audit_payload({"reports": {"q": report([source("Dup", "https://dup.example", values)])}})
        self.assertIn("SAME_SOURCE_DUPLICATE_HASH_METADATA_CONFLICT", result["findingCounts"])

    def test_source_with_items_but_zero_relevant_results_fails(self):
        irrelevant = source("Spam", "https://spam.example", [item(title="Unrelated homepage item", relevance=0)])
        irrelevant["relevantResultCount"] = 0
        irrelevant["relevancePrecision"] = 0
        result = audit_payload({"reports": {"q": report([irrelevant])}})
        self.assertIn("ZERO_RELEVANT_SOURCE_RESULTS", result["findingCounts"])
        self.assertEqual(result["status"], "FAIL")

    def test_incomplete_exhaustive_coverage_fails_only_when_required(self):
        payload = {"reports": {"q": report([source("A", "https://a.example", [item()])], loaded=2)}}
        self.assertEqual(audit_payload(payload, require_complete=False)["status"], "PASS")
        result = audit_payload(payload, require_complete=True)
        self.assertIn("INCOMPLETE_BENCHMARK_HOST_COVERAGE", result["findingCounts"])

    def test_truncated_legacy_debug_hash_is_warning(self):
        value = item(hash_value="e" * 16)
        result = audit_payload({"reports": {"q": report([source("Legacy", "https://legacy.example", [value])])}})
        self.assertEqual(result["status"], "PASS")
        self.assertIn("TRUNCATED_DEBUG_HASH", result["findingCounts"])

    def test_health_check_defaults_to_green_and_supports_app_tokens(self):
        rules = [
            {"id": "g", "site": {"name": "G", "origin": "https://g.example"}, "health": {"status": "green"}},
            {"id": "y", "site": {"name": "Y", "origin": "https://y.example"}, "health": {"status": "yellow"}},
            {"id": "x", "site": {"name": "X", "origin": "https://x.example"}, "health": {"status": "gray"}},
        ]
        self.assertEqual([r["site"]["name"] for r in select_targets(rules)], ["G"])
        self.assertEqual(len(select_targets(rules, status_filter="all")), 3)
        self.assertEqual(
            [r["site"]["name"] for r in select_targets(rules, status_filter="yellow")],
            ["Y"],
        )
        duplicate_names = [
            {"id": "one", "site": {"name": "Same", "origin": "https://one.example"}},
            {"id": "two", "site": {"name": "Same", "origin": "https://two.example"}},
        ]
        self.assertEqual(len({source_result_key(rule) for rule in duplicate_names}), 2)
        source = {
            "site": {"origin": "https://example.com"},
            "search": {"request_template": "/q/{query_b64url}/{query_hex}"},
        }
        built = build_search_url(source, "流浪地球")
        self.assertNotIn("{query_b64url}", built)
        self.assertNotIn("{query_hex}", built)
        self.assertIsNotNone(MAGNET_RE.search("magnet:?xt=urn:btih:ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"))
        self.assertIsNone(MAGNET_RE.search("magnet:?xt=urn:btih:" + "0" * 32))

    def test_invalid_non_hash_btih_is_rejected(self):
        self.assertTrue(has_valid_btih_magnet("magnet:?xt=urn:btih:" + "a" * 40))
        self.assertTrue(has_valid_btih_magnet("magnet:?xt=urn:btih:ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"))
        self.assertFalse(has_valid_btih_magnet("magnet:?xt=urn:btih:一ヶ月間の禁欲の果てに彼女不在"))
        self.assertFalse(has_valid_btih_magnet("magnet:?xt=urn:btih:" + "a" * 39))

    def test_ssbc_desktop_handler_resolves_mixed_units(self):
        self.assertEqual(format_ssbc_size(24672993, "Movie.2160p"), "23.5 GB")
        self.assertEqual(format_ssbc_size(1556920320, "Inception.2010_HDRip.avi"), "1.45 GB")
        self.assertEqual(format_ssbc_size(14504761241, "Inception.2010.BDRip.1080p.mkv"), "13.5 GB")
        self.assertEqual(format_ssbc_size("1048576"), "")
        self.assertEqual(format_ssbc_size(0), "")

    def test_current_static_inventory_has_no_hard_contract_findings(self):
        result = audit_static(ROOT / "sources.json")
        self.assertEqual(result["allRules"], 357)
        self.assertEqual(result["greenRules"], 147)
        self.assertEqual(result["greenPools"], 51)
        self.assertEqual(result["hardFindingCount"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
