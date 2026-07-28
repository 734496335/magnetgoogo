# -*- coding: utf-8 -*-
"""Enrich offline movie/series feeds with douban/imdb ratings and write back."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from magnet.rating_resolver.service import RatingResolver

ROOT = Path(__file__).resolve().parents[2]

# Offline feed fields: douban/imdb (0–10), rotten_tomatoes (0–100), bangumi (0–10).
WRITEBACK_SOURCES = ("douban", "imdb", "rotten_tomatoes", "bangumi")

# Ensure these keys exist on every item after writeback.
RATING_KEYS = (
    "imdb_id",
    "imdb_rating",
    "imdb_rating_text",
    "douban_rating",
    "douban_rating_text",
    "douban_url",
    "rotten_tomatoes_rating",
    "rotten_tomatoes_rating_text",
    "rotten_tomatoes_url",
    "bangumi_rating",
    "bangumi_rating_text",
    "bangumi_subject_id",
    "bangumi_url",
)

# Primary offline artifacts consumed by app / deploy.
DEFAULT_TARGETS = [
    # Movies
    "data/resource_index/sixv_app_bundle/feed.json",
    "data/resource_index/sixv_latest_50_feed.json",
    "data/resource_index/sixv_latest_100_feed.json",
    "data/resource_index/movies_latest_100_feed.json",
    "data/resource_index/movie_app_bundle/feed.json",
    "magnetgoogo-app/android/app/src/main/assets/resource-index/sixv/feed.json",
    # Series
    "data/resource_index/series_latest_100_feed.json",
    "data/resource_index/series_app_bundle/feed.json",
    "data/resource_index/meijumi_latest_100_feed.json",
    "data/resource_index/meijumi_latest_50_feed.json",
    "data/resource_index/sixv-series_latest_50_feed.json",
    "magnetgoogo-app/android/app/src/main/assets/resource-index/series/feed.json",
    # Combined media feeds
    "data/resource_index/media_latest_200_feed.json",
    "data/resource_index/media_latest_feed.json",
]

_SEASON_TAIL = re.compile(
    r"\s*(第\s*[0-9一二三四五六七八九十百]+\s*季|Season\s*\d+|S\d{1,2}).*$",
    re.I,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _valid_10(score: Any) -> float | None:
    try:
        v = float(score)
    except (TypeError, ValueError):
        return None
    if not (0 < v <= 10):
        return None
    return v


def _valid_100(score: Any) -> float | None:
    """Rotten Tomatoes tomatometer / audience percent."""
    try:
        v = float(score)
    except (TypeError, ValueError):
        return None
    if not (0 < v <= 100):
        return None
    return v


def _ensure_rating_keys(item: dict[str, Any]) -> None:
    for key in RATING_KEYS:
        if key not in item:
            item[key] = None


def _rt_looks_bogus(item: dict[str, Any]) -> bool:
    """Previous RT scrape bug pinned many titles to Odyssey 2026 @ 94%."""
    url = str(item.get("rotten_tomatoes_url") or "")
    if "the_odyssey_2026" in url:
        return True
    return False


def _item_ratings_complete(item: dict[str, Any]) -> bool:
    if _rt_looks_bogus(item):
        return False
    return (
        _valid_10(item.get("douban_rating")) is not None
        and _valid_10(item.get("imdb_rating")) is not None
        and _valid_100(item.get("rotten_tomatoes_rating")) is not None
        and _valid_10(item.get("bangumi_rating")) is not None
    )


def _lookup_title_for_item(item: dict[str, Any]) -> str:
    # Prefer series root name for TV; then original_title; then title.
    for key in ("series_title", "original_title", "title", "listing_title"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            t = val.strip()
            # strip season suffix for cleaner search
            t2 = _SEASON_TAIL.sub("", t).strip()
            return t2 or t
    return ""


def _apply_ratings_to_item(
    item: dict[str, Any],
    ratings: dict[str, dict[str, Any]],
    *,
    overwrite: bool = False,
) -> dict[str, str]:
    """Mutate item in place. Return map of fields changed."""
    changed: dict[str, str] = {}
    _ensure_rating_keys(item)

    douban = ratings.get("douban") or {}
    imdb = ratings.get("imdb") or {}
    rt = ratings.get("rotten_tomatoes") or {}
    bangumi = ratings.get("bangumi") or {}

    # imdb_id
    new_id = imdb.get("external_id") if imdb.get("status") == "ok" else None
    if isinstance(new_id, str) and new_id.startswith("tt"):
        old = item.get("imdb_id")
        if overwrite or not old:
            if old != new_id:
                item["imdb_id"] = new_id
                changed["imdb_id"] = new_id

    # imdb_rating 0–10
    imdb_score = _valid_10(imdb.get("score")) if imdb.get("status") == "ok" else None
    if imdb_score is not None:
        old = _valid_10(item.get("imdb_rating"))
        if overwrite or old is None:
            item["imdb_rating"] = imdb_score
            item["imdb_rating_text"] = imdb.get("score_text") or f"{imdb_score}/10"
            changed["imdb_rating"] = str(imdb_score)

    # douban 0–10
    douban_score = _valid_10(douban.get("score")) if douban.get("status") == "ok" else None
    if douban_score is not None:
        old = _valid_10(item.get("douban_rating"))
        if overwrite or old is None:
            item["douban_rating"] = douban_score
            item["douban_rating_text"] = douban.get("score_text") or f"{douban_score}/10"
            if douban.get("url"):
                item["douban_url"] = douban["url"]
            changed["douban_rating"] = str(douban_score)

    # rotten tomatoes 0–100 (percent)
    rt_url = str(rt.get("url") or "")
    rt_score = _valid_100(rt.get("score")) if rt.get("status") == "ok" else None
    # Reject known-bad / low-confidence RT hits (stale cache or weak scrape)
    if rt_score is not None and (
        "the_odyssey_2026" in rt_url
        or float(rt.get("confidence") or 0) < 0.5
        or (rt.get("via") or "") in {"rt_scrape", "rt_scrape_audience"}
    ):
        # Only accept scorecard / omdb after the parser fix
        if (rt.get("via") or "") not in {"rt_scorecard", "omdb"}:
            rt_score = None
        if "the_odyssey_2026" in rt_url:
            rt_score = None

    if rt_score is not None:
        old = _valid_100(item.get("rotten_tomatoes_rating"))
        if overwrite or old is None or _rt_looks_bogus(item):
            item["rotten_tomatoes_rating"] = rt_score
            text = rt.get("score_text") or f"{int(rt_score)}%"
            item["rotten_tomatoes_rating_text"] = text
            if rt.get("url"):
                item["rotten_tomatoes_url"] = rt["url"]
            changed["rotten_tomatoes_rating"] = str(rt_score)
    elif _rt_looks_bogus(item) or _valid_100(item.get("rotten_tomatoes_rating")) is not None:
        # Prefer clearing untrusted/old RT rather than keeping Odyssey 94% spam.
        # Only clear when we attempted a lookup that did not yield a trusted score.
        if _rt_looks_bogus(item) or overwrite:
            item["rotten_tomatoes_rating"] = None
            item["rotten_tomatoes_rating_text"] = None
            item["rotten_tomatoes_url"] = None
            changed["rotten_tomatoes_rating"] = "cleared_bogus"

    # bangumi 0–10
    bg_score = _valid_10(bangumi.get("score")) if bangumi.get("status") == "ok" else None
    if bg_score is not None:
        old = _valid_10(item.get("bangumi_rating"))
        if overwrite or old is None:
            item["bangumi_rating"] = bg_score
            item["bangumi_rating_text"] = bangumi.get("score_text") or f"{bg_score}/10"
            if bangumi.get("external_id"):
                item["bangumi_subject_id"] = str(bangumi["external_id"])
            if bangumi.get("url"):
                item["bangumi_url"] = bangumi["url"]
            changed["bangumi_rating"] = str(bg_score)

    return changed


def enrich_feed_file(
    path: Path,
    resolver: RatingResolver,
    *,
    overwrite: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing"}

    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list):
        return {"path": str(path), "status": "invalid", "error": "no items array"}

    work = items if limit is None else items[:limit]
    stats = {
        "path": str(path),
        "total": len(work),
        "looked_up": 0,
        "changed_items": 0,
        "filled_douban": 0,
        "filled_imdb": 0,
        "filled_rotten_tomatoes": 0,
        "filled_bangumi": 0,
        "unchanged": 0,
        "errors": 0,
        "samples": [],
    }

    for item in work:
        if not isinstance(item, dict):
            continue
        _ensure_rating_keys(item)
        title = _lookup_title_for_item(item)
        year = item.get("year")
        try:
            year_i = int(year) if year is not None else None
        except (TypeError, ValueError):
            year_i = None
        imdb_id = item.get("imdb_id") if isinstance(item.get("imdb_id"), str) else None
        original_title = (
            item.get("original_title")
            if isinstance(item.get("original_title"), str)
            else None
        )

        # Skip if all four sources already filled and not overwriting
        if not overwrite and _item_ratings_complete(item):
            stats["unchanged"] += 1
            continue

        try:
            report = resolver.lookup(
                title or (item.get("title") or ""),
                year=year_i,
                imdb_id=imdb_id,
                original_title=original_title,
                use_cache=True,
                parallel=True,
            )
            stats["looked_up"] += 1
            changed = _apply_ratings_to_item(item, report.ratings, overwrite=overwrite)
            if changed:
                stats["changed_items"] += 1
                if "douban_rating" in changed:
                    stats["filled_douban"] += 1
                if "imdb_rating" in changed:
                    stats["filled_imdb"] += 1
                if "rotten_tomatoes_rating" in changed:
                    stats["filled_rotten_tomatoes"] += 1
                if "bangumi_rating" in changed:
                    stats["filled_bangumi"] += 1
                if len(stats["samples"]) < 8:
                    stats["samples"].append(
                        {
                            "title": item.get("title"),
                            "lookup_title": title,
                            "changed": changed,
                            "display": report.display,
                        }
                    )
            else:
                stats["unchanged"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["errors"] += 1
            if len(stats["samples"]) < 12:
                stats["samples"].append(
                    {"title": item.get("title"), "error": f"{type(exc).__name__}: {exc}"}
                )

    if not dry_run:
        backup = path.with_suffix(path.suffix + f".bak-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(path, backup)
        stats["backup"] = str(backup)
        # bump generated_at if present
        if isinstance(data.get("generated_at"), str):
            data["generated_at"] = _utc_now()
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        stats["status"] = "written"
    else:
        stats["status"] = "dry_run"

    return stats


def enrich_sqlite_movie_items(
    db_path: Path,
    resolver: RatingResolver,
    *,
    overwrite: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Update douban_rating / imdb_id on movie_items (no imdb_rating column)."""
    if not db_path.exists():
        return {"path": str(db_path), "status": "missing"}
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "movie_items" not in tables:
            return {"path": str(db_path), "status": "no_movie_items"}
        sql = "SELECT movie_id, title, original_title, year, imdb_id, douban_rating FROM movie_items"
        rows = list(con.execute(sql))
        if limit is not None:
            rows = rows[:limit]
        updated = 0
        for row in rows:
            has_d = _valid_10(row["douban_rating"]) is not None
            has_id = bool(row["imdb_id"])
            if not overwrite and has_d and has_id:
                continue
            title = row["original_title"] or row["title"] or ""
            year = row["year"]
            try:
                year_i = int(year) if year is not None else None
            except (TypeError, ValueError):
                year_i = None
            report = resolver.lookup(
                title,
                year=year_i,
                imdb_id=row["imdb_id"],
                use_cache=True,
            )
            douban = report.ratings.get("douban") or {}
            imdb = report.ratings.get("imdb") or {}
            new_d = _valid_10(douban.get("score")) if douban.get("status") == "ok" else None
            new_id = imdb.get("external_id") if imdb.get("status") == "ok" else None
            sets = []
            vals: list[Any] = []
            if new_d is not None and (overwrite or not has_d):
                sets.append("douban_rating = ?")
                vals.append(new_d)
                sets.append("douban_rating_text = ?")
                vals.append(douban.get("score_text") or f"{new_d}/10")
                if douban.get("url"):
                    sets.append("douban_url = ?")
                    vals.append(douban["url"])
            if isinstance(new_id, str) and new_id.startswith("tt") and (overwrite or not has_id):
                sets.append("imdb_id = ?")
                vals.append(new_id)
            if sets:
                sets.append("updated_at = ?")
                vals.append(_utc_now())
                vals.append(row["movie_id"])
                con.execute(
                    f"UPDATE movie_items SET {', '.join(sets)} WHERE movie_id = ?",
                    vals,
                )
                updated += 1
        con.commit()
        return {"path": str(db_path), "status": "written", "updated": updated, "total": len(rows)}
    finally:
        con.close()


def run_writeback(
    *,
    root: Path = ROOT,
    targets: list[str] | None = None,
    overwrite: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
    include_sqlite: bool = True,
    cache_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolver = RatingResolver(
        cache_dir=cache_dir or (root / "data" / "rating_cache" / "writeback"),
        sources=WRITEBACK_SOURCES,
        max_workers=3,
    )
    results = []
    for rel in targets or DEFAULT_TARGETS:
        path = root / rel if not Path(rel).is_absolute() else Path(rel)
        print(f"[feed] {path}", flush=True)
        stats = enrich_feed_file(
            path,
            resolver,
            overwrite=overwrite,
            limit=limit,
            dry_run=dry_run,
        )
        print(
            f"  -> {stats.get('status')} looked_up={stats.get('looked_up')} "
            f"changed={stats.get('changed_items')} "
            f"douban={stats.get('filled_douban')} imdb={stats.get('filled_imdb')} "
            f"rt={stats.get('filled_rotten_tomatoes')} bangumi={stats.get('filled_bangumi')} "
            f"errors={stats.get('errors')}",
            flush=True,
        )
        results.append(stats)

    db_results = []
    if include_sqlite and not dry_run:
        for rel in (
            "data/resource_index/sixv_latest_50.db",
            "data/resource_index/meijumi_latest_50.db",
            "data/resource_index/sixv-series_latest_50.db",
            "data/resource_index/dytt8899_latest_25.db",
        ):
            dbp = root / rel
            print(f"[db] {dbp}", flush=True)
            r = enrich_sqlite_movie_items(dbp, resolver, overwrite=overwrite, limit=limit)
            print(f"  -> {r}", flush=True)
            db_results.append(r)

    summary = {
        "generated_at": _utc_now(),
        "overwrite": overwrite,
        "limit": limit,
        "dry_run": dry_run,
        "feeds": results,
        "databases": db_results,
    }
    out = root / "data" / "rating_cache" / "writeback_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary -> {out}")
    return summary
