#!/usr/bin/env python3
"""
Rebuild missing mirror rules that were lost in the git checkout incident.
This script adds CLB, SOBT, CLM, ZZB, CLTT, 52BT mirrors + 阿狸搜 + brand registry.
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

SOURCES_JSON = Path(__file__).parent.parent / "sources.json"

def gen_id(origin: str) -> str:
    return hashlib.md5(origin.encode()).hexdigest()[:12]

# ── Missing mirror definitions ──
# Each group: (template_name_in_sources, brand, new_mirrors)
MIRROR_GROUPS = [
    # CLB mirrors — clone from existing 磁力宝 (clb12.xyz)
    {
        "brand": "磁力宝",
        "template_origin": "https://clb12.xyz",
        "mirrors": [
            ("clb21.top", "磁力宝(clb21)"),
            ("clb22.top", "磁力宝(clb22)"),
            ("clb23.top", "磁力宝(clb23)"),
            ("clb24.top", "磁力宝(clb24)"),
            ("clb25.top", "磁力宝(clb25)"),
            ("clb26.top", "磁力宝(clb26)"),
        ],
    },
    # SOBT mirrors — same template as CLB (same codebase)
    {
        "brand": "SOBT",
        "template_origin": "https://clb12.xyz",
        "mirrors": [
            ("sobt19.top", "SOBT(sobt19)"),
            ("sobt22.top", "SOBT(sobt22)"),
            ("sobt23.top", "SOBT(sobt23)"),
            ("sobt24.top", "SOBT(sobt24)"),
        ],
    },
    # CLM mirrors
    {
        "brand": "磁力猫",
        "template_origin": "https://clb12.xyz",
        "mirrors": [
            ("clm50.top", "磁力猫(clm50)"),
            ("clm52.top", "磁力猫(clm52)"),
            ("clm58.top", "磁力猫(clm58)"),
            ("clm59.top", "磁力猫(clm59)"),
        ],
    },
    # ZZB mirrors — clone from existing 种子吧 template
    {
        "brand": "种子吧",
        "template_origin": None,  # will build from scratch
        "mirrors": [
            ("zzb04.top", "种子吧(zzb04)"),
            ("zzb05.top", "种子吧(zzb05)"),
            ("zzb06.top", "种子吧(zzb06)"),
            ("zzb07.top", "种子吧(zzb07)"),
            ("zhongziba.cc", "种子吧(zhongziba)"),
            ("seed8.org", "种子吧(seed8)"),
        ],
    },
    # CLTT mirror
    {
        "brand": "磁力天堂",
        "template_origin": None,
        "mirrors": [
            ("cltt03.sbs", "磁力天堂(cltt03)"),
        ],
    },
    # 老王磁力
    {
        "brand": "老王磁力",
        "template_origin": None,
        "mirrors": [
            ("laowangzo.top", "老王磁力(laowangzo)"),
            ("laowangcili.top", "老王磁力(laowangcili)"),
        ],
    },
    # BTSearch
    {
        "brand": "BTSearch",
        "template_origin": None,
        "mirrors": [
            ("btsearch.org", "BTSearch"),
        ],
    },
    # 磁力多
    {
        "brand": "磁力多",
        "template_origin": None,
        "mirrors": [
            ("btdo.top", "磁力多(btdo)"),
        ],
    },
]

# CLB/SOBT/CLM all use the same template
CLB_TEMPLATE = {
    "capabilities": {"supports_detail": True},
    "search": {
        "request_template": "/search?wd={query_b64}",
        "timeout_ms": 10000,
        "retries": {"max_attempts": 2, "backoff_ms": 1000},
        "requires_waf_bypass": False,
        "parse_metadata": {
            "selectors": {
                "list_item": "div.ssbox",
                "title": "h5 a",
                "magnet": "",
                "size": "span:nth-child(2)",
                "date": "span:nth-child(3)",
                "detail_link": "h5 a"
            }
        },
        "detail": {
            "selectors": {
                "magnet": "a[href^='magnet:']",
                "title": "h3",
                "size": ""
            }
        }
    },
    "quality": {"score": 50, "tags": ["chinese", "general"]},
    "health": {
        "status": "green",
        "status_detail": "ok",
        "fail_streak": 0,
    },
}

ZZB_TEMPLATE = {
    "capabilities": {"supports_detail": True},
    "search": {
        "request_template": "/search?wd={query_b64}",
        "timeout_ms": 10000,
        "retries": {"max_attempts": 2, "backoff_ms": 1000},
        "requires_waf_bypass": False,
        "parse_metadata": {
            "selectors": {
                "list_item": "div.media-body",
                "title": "a[href*='/seed/']",
                "magnet": "",
                "size": "span.label-warning",
                "date": "span.label-primary",
                "detail_link": "a[href*='/seed/']"
            }
        },
        "detail": {
            "selectors": {
                "magnet": "a[href^='magnet:']",
                "title": "h3",
                "size": "span.label-warning"
            }
        }
    },
    "quality": {"score": 55, "tags": ["chinese", "general"]},
    "health": {
        "status": "green",
        "status_detail": "ok",
        "fail_streak": 0,
    },
}

CLTT_TEMPLATE = {
    "capabilities": {"supports_detail": True},
    "search": {
        "request_template": "/search?wd={query_b64}",
        "timeout_ms": 10000,
        "retries": {"max_attempts": 2, "backoff_ms": 1000},
        "requires_waf_bypass": False,
        "parse_metadata": {
            "selectors": {
                "list_item": "div.ssbox",
                "title": "h5 a",
                "magnet": "",
                "size": "span:nth-child(2)",
                "date": "span:nth-child(3)",
                "detail_link": "h5 a"
            }
        },
        "detail": {
            "selectors": {
                "magnet": "a[href^='magnet:']",
                "title": "h3",
                "size": ""
            }
        }
    },
    "quality": {"score": 50, "tags": ["chinese", "general"]},
    "health": {
        "status": "green",
        "status_detail": "ok",
        "fail_streak": 0,
    },
}

LAOWANG_TEMPLATE = {
    "capabilities": {"supports_detail": False},
    "search": {
        "request_template": "/search?wd={query_b64}",
        "timeout_ms": 10000,
        "retries": {"max_attempts": 2, "backoff_ms": 1000},
        "requires_waf_bypass": False,
        "parse_metadata": {
            "selectors": {
                "list_item": "div.ssbox",
                "title": "h5 a",
                "magnet": "",
                "size": "span:nth-child(2)",
                "date": "span:nth-child(3)",
                "detail_link": "h5 a"
            }
        }
    },
    "quality": {"score": 40, "tags": ["chinese", "general"]},
    "health": {
        "status": "yellow",
        "status_detail": "parsing_failed",
        "fail_streak": 0,
    },
}

BTSEARCH_TEMPLATE = {
    "capabilities": {"supports_detail": False},
    "search": {
        "request_template": "/search/{query}",
        "handler": "",
        "timeout_ms": 10000,
        "retries": {"max_attempts": 2, "backoff_ms": 1000},
        "requires_waf_bypass": False,
        "requires_browser": True,
        "parse_metadata": {
            "selectors": {
                "list_item": "div.search-result",
                "title": "h5 a",
                "magnet": "a[href^='magnet:']",
                "size": "",
                "date": ""
            }
        }
    },
    "quality": {"score": 45, "tags": ["general"]},
    "health": {
        "status": "yellow",
        "status_detail": "waf",
        "fail_streak": 0,
    },
}

BTDO_TEMPLATE = {
    "capabilities": {"supports_detail": False},
    "search": {
        "request_template": "/search?keyword={query}",
        "handler": "",
        "timeout_ms": 10000,
        "retries": {"max_attempts": 2, "backoff_ms": 1000},
        "requires_waf_bypass": False,
        "requires_browser": True,
        "parse_metadata": {
            "selectors": {
                "list_item": "div.search-item",
                "title": "a.item-title",
                "magnet": "",
                "size": "span.item-size",
                "date": "span.item-date"
            }
        }
    },
    "quality": {"score": 45, "tags": ["chinese", "general"]},
    "health": {
        "status": "yellow",
        "status_detail": "waf",
        "fail_streak": 0,
    },
}

# 52BT → promote from gray to green (same CLB template)
FIXES_52BT = ["529072.xyz", "529073.xyz"]

# 阿狸搜 (cache.foxs.top) — completely new
ALISO_RULE = {
    "id": "f5b8d3e20a47",
    "site": {
        "name": "阿狸搜",
        "origin": "https://cache.foxs.top",
        "brand": "磁力狐/阿狸搜",
        "mirrors": ["https://s83.foxso.top"],
        "countries": ["china"]
    },
    "capabilities": {"supports_detail": True},
    "search": {
        "request_template": "/search?word={query}",
        "referer": "https://s83.foxso.top/",
        "timeout_ms": 10000,
        "retries": {"max_attempts": 2, "backoff_ms": 1000},
        "requires_waf_bypass": False,
        "parse_metadata": {
            "selectors": {
                "list_item": "div.layui-colla-item.search-box",
                "title": "a[href^=\"/doc/\"]",
                "magnet": "",
                "size": "",
                "date": "",
                "detail_link": "a[href^=\"/doc/\"]"
            },
            "notes": "SSR search engine. 15 results/page. Requires Referer: s83.foxso.top."
        },
        "detail": {
            "selectors": {
                "magnet": "a[href^=\"magnet:\"]",
                "title": "h1",
                "size": ""
            }
        }
    },
    "quality": {"score": 65, "tags": ["chinese", "general", "xhs-discovery"]},
    "health": {
        "status": "green",
        "status_detail": "ok",
        "fail_streak": 0,
        "last_checked_at": "2026-05-03T00:10:00+08:00",
        "magnets_found": 15,
        "sample_title": "Avengers",
        "note": "Real backend of 磁力狐. SSR HTML, detail-follow. Requires Referer header."
    }
}

# Brand registry entries to add/update
BRAND_REGISTRY = [
    {"brand": "磁力宝", "status": "green", "category": "china", "backend": "clb", "green_domains": ["clb12.xyz", "clb21.top", "clb22.top", "clb23.top", "clb24.top", "clb25.top", "clb26.top"]},
    {"brand": "SOBT", "status": "green", "category": "china", "backend": "sobt", "green_domains": ["sobt19.top", "sobt22.top", "sobt23.top", "sobt24.top"]},
    {"brand": "磁力猫", "status": "green", "category": "china", "backend": "clm", "green_domains": ["clm50.top", "clm52.top", "clm58.top", "clm59.top"], "yellow_domains": ["magnetcatcat.com"]},
    {"brand": "种子吧", "status": "green", "category": "china", "backend": "zzb", "green_domains": ["zzb01.top", "zzb04.top", "zzb05.top", "zzb06.top", "zzb07.top", "zhongziba.cc", "seed8.org"]},
    {"brand": "磁力天堂", "status": "green", "category": "china", "backend": "cltt", "green_domains": ["cltt03.sbs"]},
    {"brand": "52BT/磁力帝", "status": "green", "category": "china", "backend": "52bt", "green_domains": ["cld140.buzz", "529072.xyz", "529073.xyz"]},
    {"brand": "磁力狐/阿狸搜", "status": "green", "category": "china", "backend": "foxso", "green_domains": ["cache.foxs.top"], "yellow_domains": ["s83.foxso.top"], "note": "Requires Referer: s83.foxso.top"},
    {"brand": "老王磁力", "status": "yellow", "category": "china", "backend": "laowang", "yellow_domains": ["laowangzo.top", "laowangcili.top"]},
    {"brand": "BTSearch", "status": "yellow", "category": "international", "backend": "btsearch", "yellow_domains": ["btsearch.org"]},
    {"brand": "磁力多", "status": "yellow", "category": "china", "backend": "btdo", "yellow_domains": ["btdo.top"]},
]


def main():
    data = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))
    rules = data["rulesets"][0]["rules"]
    now = datetime.now(timezone.utc).isoformat()

    existing_origins = {r["site"]["origin"] for r in rules}
    added = 0

    # Template map
    TEMPLATE_MAP = {
        "磁力宝": CLB_TEMPLATE,
        "SOBT": CLB_TEMPLATE,
        "磁力猫": CLB_TEMPLATE,
        "种子吧": ZZB_TEMPLATE,
        "磁力天堂": CLTT_TEMPLATE,
        "老王磁力": LAOWANG_TEMPLATE,
        "BTSearch": BTSEARCH_TEMPLATE,
        "磁力多": BTDO_TEMPLATE,
    }

    for group in MIRROR_GROUPS:
        brand = group["brand"]
        template = TEMPLATE_MAP.get(brand, CLB_TEMPLATE)

        for domain, name in group["mirrors"]:
            origin = f"https://{domain}"
            if origin in existing_origins:
                print(f"  SKIP {name} ({domain}) — already exists")
                continue

            rule = {
                "id": gen_id(origin),
                "site": {
                    "name": name,
                    "origin": origin,
                    "brand": brand,
                    "countries": ["china"]
                },
                **json.loads(json.dumps(template)),  # deep copy
            }
            rule["health"]["last_checked_at"] = now
            rules.append(rule)
            existing_origins.add(origin)
            added += 1
            print(f"  + {name} ({domain}) [{rule['health']['status']}]")

    # Fix 52BT: promote gray→green
    for rule in rules:
        for domain in FIXES_52BT:
            if rule["site"]["origin"] == f"https://{domain}":
                if rule["health"]["status"] != "green":
                    rule["health"]["status"] = "green"
                    rule["health"]["status_detail"] = "healed"
                    rule["health"]["fail_streak"] = 0
                    rule["search"] = json.loads(json.dumps(CLB_TEMPLATE["search"]))
                    rule["capabilities"] = {"supports_detail": True}
                    rule["quality"]["score"] = 50
                    print(f"  ↑ {rule['site']['name']} gray→green")
                    added += 1

    # Add 阿狸搜
    if f"https://cache.foxs.top" not in existing_origins:
        rules.append(ALISO_RULE)
        added += 1
        print(f"  + 阿狸搜 (cache.foxs.top) [green]")

    # Add/update brand registry
    if "brand_registry" not in data:
        data["brand_registry"] = []

    existing_brands = {b["brand"] for b in data.get("brand_registry", [])}
    for entry in BRAND_REGISTRY:
        if entry["brand"] not in existing_brands:
            data["brand_registry"].append(entry)
            print(f"  + brand: {entry['brand']}")
        else:
            for b in data["brand_registry"]:
                if b["brand"] == entry["brand"]:
                    b.update(entry)
                    print(f"  ~ brand: {entry['brand']}")
                    break

    # Update meta
    data.setdefault("meta", {})["total_rules"] = len(rules)

    # Write
    SOURCES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    g = sum(1 for r in rules if r.get("health", {}).get("status") == "green")
    y = sum(1 for r in rules if r.get("health", {}).get("status") == "yellow")
    print(f"\n✓ Total={len(rules)}, Green={g}, Yellow={y}, Added={added}")


if __name__ == "__main__":
    main()
