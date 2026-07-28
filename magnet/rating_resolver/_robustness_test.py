# -*- coding: utf-8 -*-
"""Robustness / stability suite for rating_resolver."""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from magnet.rating_resolver.normalize import normalize_title, strip_year_from_title
from magnet.rating_resolver.service import RatingResolver, self_check


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    failures: list[str] = []
    cache = ROOT / "data" / "rating_cache" / "robustness"
    cache.mkdir(parents=True, exist_ok=True)
    resolver = RatingResolver(cache_dir=cache)

    # 1) unit-ish normalize
    section("normalize")
    cases = [
        ("肖申克的救赎 1994 1080P 国语中字", "肖申克的救赎 1994"),
        ("Inception.2010.1080p.BluRay", "Inception.2010"),
        ("", ""),
    ]
    for raw, _ in cases:
        n = strip_year_from_title(raw) or normalize_title(raw)
        print(f"  {raw!r} -> {n!r}")
        if raw and not n and raw.strip():
            failures.append(f"normalize emptied non-empty: {raw}")

    # 2) empty / garbage must not crash
    section("edge queries no crash")
    edge = [
        {"title": "", "year": None},
        {"title": "   ", "year": None},
        {"title": "!!!@@@", "year": 1900},
        {"title": "a" * 300, "year": None},
        {"title": "不存在的电影XYZABC123", "year": 2099},
        {"title": "Inception", "year": 2010, "imdb_id": "tt1375666"},
        {"title": "垃圾标题", "year": None, "imdb_id": "not-an-id"},
    ]
    for q in edge:
        try:
            r = resolver.lookup(
                q["title"],
                year=q.get("year"),
                imdb_id=q.get("imdb_id"),
                use_cache=False,
                parallel=True,
            )
            assert isinstance(r.to_dict(), dict)
            assert "ratings" in r.to_dict()
            print(f"  OK edge {q['title'][:40]!r} ok_count={r.ok_count()}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"edge crash {q}: {exc}")
            traceback.print_exc()

    # 3) known goods
    section("known goods")
    goods = [
        ("The Shawshank Redemption", 1994, None),
        ("肖申克的救赎", 1994, None),
        ("Inception", 2010, "tt1375666"),
        ("盗梦空间", 2010, None),
    ]
    goods_ok = 0
    for title, year, iid in goods:
        r = resolver.lookup(title, year=year, imdb_id=iid, use_cache=True, parallel=True)
        d = r.to_dict()
        print(f"  {title}: display={d.get('display')} sources={[k for k,v in d['ratings'].items() if v.get('status')=='ok']}")
        if r.ok_count() > 0:
            goods_ok += 1
        else:
            failures.append(f"known good miss: {title}")
    if goods_ok < 3:
        failures.append(f"known goods only {goods_ok}/4")

    # 4) cache hit
    section("cache")
    t0 = time.monotonic()
    r1 = resolver.lookup("Inception", year=2010, imdb_id="tt1375666", use_cache=True)
    t1 = time.monotonic()
    r2 = resolver.lookup("Inception", year=2010, imdb_id="tt1375666", use_cache=True)
    t2 = time.monotonic()
    print(f"  first {int((t1-t0)*1000)}ms cache_hit={r1.cache_hit}")
    print(f"  second {int((t2-t1)*1000)}ms cache_hit={r2.cache_hit}")
    if not r2.cache_hit:
        failures.append("second lookup should be cache hit")
    if r2.ok_count() < 1:
        failures.append("cached result lost scores")

    # 5) single-source isolation
    section("per-source isolation")
    for src in ("douban", "imdb", "bangumi", "rotten_tomatoes"):
        rr = RatingResolver(cache_dir=cache / src, sources=[src])
        try:
            r = rr.lookup("Inception", year=2010, imdb_id="tt1375666", use_cache=False)
            st = list(r.ratings.values())[0]["status"] if r.ratings else "none"
            print(f"  {src}: status={st} score={list(r.ratings.values())[0].get('score') if r.ratings else None}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"source {src} crash: {exc}")

    # 6) serial vs parallel consistency for known id
    section("serial vs parallel")
    a = resolver.lookup("Inception", year=2010, imdb_id="tt1375666", use_cache=False, parallel=True)
    b = resolver.lookup("Inception", year=2010, imdb_id="tt1375666", use_cache=False, parallel=False)
    sa = {k: v.get("score") for k, v in a.ratings.items() if v.get("status") == "ok"}
    sb = {k: v.get("score") for k, v in b.ratings.items() if v.get("status") == "ok"}
    print(f"  parallel={sa}")
    print(f"  serial={sb}")
    # scores should agree when both ok
    for k in set(sa) & set(sb):
        if sa[k] != sb[k]:
            failures.append(f"score mismatch {k}: {sa[k]} vs {sb[k]}")

    # 7) self-check
    section("self-check")
    sc = self_check(cache_dir=cache / "self", use_cache=False)
    print(f"  GOAL_MATCHED={sc.get('GOAL_MATCHED')} STRONG={sc.get('GOAL_STRONG')}")
    print(f"  sources={sc.get('sources_with_ok')} samples_ok={sc.get('samples_ok')}")
    if not sc.get("GOAL_MATCHED"):
        failures.append("self-check GOAL_MATCHED false")

    # 8) score scale sanity for display fields
    section("scale sanity")
    r = resolver.lookup("Inception", year=2010, imdb_id="tt1375666", use_cache=True)
    for src, val in r.ratings.items():
        if val.get("status") != "ok":
            continue
        score = val.get("score")
        scale = val.get("scale") or 10
        if score is None:
            continue
        if scale == 10 and not (0 < float(score) <= 10):
            failures.append(f"{src} score {score} out of 0-10")
        if scale == 100 and not (0 < float(score) <= 100):
            failures.append(f"{src} score {score} out of 0-100")
        print(f"  {src}: {score}/{scale} via={val.get('via')}")

    section("SUMMARY")
    report = {
        "failures": failures,
        "pass": len(failures) == 0,
        "failure_count": len(failures),
    }
    out = cache / "robustness_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
