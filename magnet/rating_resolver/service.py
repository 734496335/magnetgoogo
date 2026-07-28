# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from magnet.rating_resolver.cache import JsonCache
from magnet.rating_resolver.matching import enforce_match
from magnet.rating_resolver.models import LookupQuery, RatingReport, RatingValue
from magnet.rating_resolver.normalize import normalize_title, strip_year_from_title
from magnet.rating_resolver.providers import DEFAULT_SOURCES, build_providers

# Preferred display order for App-like tags
_DISPLAY_ORDER = ("douban", "imdb", "rotten_tomatoes", "bangumi")
_DISPLAY_LABEL = {
    "douban": "豆瓣",
    "imdb": "IMDb",
    "rotten_tomatoes": "烂番茄",
    "bangumi": "Bangumi",
}


class RatingResolver:
    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        cache_ttl_seconds: int = 86400 * 14,
        sources: Iterable[str] | None = None,
        max_workers: int = 4,
    ) -> None:
        root = Path(cache_dir) if cache_dir else Path("data/rating_cache")
        self.cache = JsonCache(root, ttl_seconds=cache_ttl_seconds)
        self.source_names = tuple(sources) if sources else DEFAULT_SOURCES
        self.max_workers = max_workers

    def lookup(
        self,
        title: str,
        *,
        year: int | None = None,
        imdb_id: str | None = None,
        original_title: str | None = None,
        use_cache: bool = True,
        parallel: bool = True,
    ) -> RatingReport:
        query = LookupQuery(
            title=title,
            year=year,
            imdb_id=imdb_id,
            original_title=original_title,
        )
        norm = strip_year_from_title(title) or normalize_title(title)
        # Empty / whitespace-only titles: never hit providers (prevents false matches).
        if not norm and not (imdb_id or "").strip():
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            return RatingReport(
                query={
                    "title": title,
                    "year": year,
                    "imdb_id": imdb_id,
                    "original_title": original_title,
                },
                normalized_title="",
                ratings={
                    name: {
                        "source": name,
                        "status": "skipped",
                        "score": None,
                        "scale": 10.0,
                        "score_text": None,
                        "url": None,
                        "external_id": None,
                        "matched_title": None,
                        "matched_year": None,
                        "confidence": 0.0,
                        "note": "empty title",
                        "latency_ms": 0,
                        "via": None,
                    }
                    for name in (
                        "douban",
                        "imdb",
                        "rotten_tomatoes",
                        "bangumi",
                    )
                },
                display=[],
                fetched_at=now,
                cache_hit=False,
            )

        cache_key = f"lookup-match-gate-v2::{query.cache_key()}::{','.join(self.source_names)}"

        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                report = RatingReport(
                    query=cached.get("query") or {
                        "title": title,
                        "year": year,
                        "imdb_id": imdb_id,
                    },
                    normalized_title=cached.get("normalized_title") or norm,
                    ratings=cached.get("ratings") or {},
                    display=cached.get("display") or [],
                    fetched_at=cached.get("fetched_at") or "",
                    cache_hit=True,
                )
                return report

        providers = build_providers(self.source_names)
        results: dict[str, RatingValue] = {}

        if parallel and len(providers) > 1:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(providers))) as ex:
                futs = {ex.submit(p.safe_lookup, query): p.name for p in providers}
                for fut in as_completed(futs):
                    val = enforce_match(query, fut.result())
                    results[val.source] = val
        else:
            for p in providers:
                val = enforce_match(query, p.safe_lookup(query))
                results[val.source] = val

        # Cross-fill: if imdb got id but douban empty, nothing extra for now.
        # If imdb failed but we have imdb_id from query, already tried.

        ratings_dict = {k: v.to_dict() for k, v in results.items()}
        display = self._build_display(ratings_dict)
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        report = RatingReport(
            query={"title": title, "year": year, "imdb_id": imdb_id, "original_title": original_title},
            normalized_title=norm,
            ratings=ratings_dict,
            display=display,
            fetched_at=now,
            cache_hit=False,
        )
        if use_cache:
            self.cache.set(cache_key, report.to_dict())
        return report

    def _build_display(self, ratings: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for src in _DISPLAY_ORDER:
            r = ratings.get(src)
            if not r or r.get("status") != "ok" or r.get("score") is None:
                continue
            out.append(
                {
                    "label": _DISPLAY_LABEL.get(src, src),
                    "source": src,
                    "value": r["score"],
                    "scale": r.get("scale") or 10,
                    "score_text": r.get("score_text"),
                    "via": r.get("via"),
                }
            )
        # any other ok sources
        for src, r in ratings.items():
            if src in _DISPLAY_ORDER:
                continue
            if r.get("status") == "ok" and r.get("score") is not None:
                out.append(
                    {
                        "label": src,
                        "source": src,
                        "value": r["score"],
                        "scale": r.get("scale") or 10,
                        "score_text": r.get("score_text"),
                        "via": r.get("via"),
                    }
                )
        return out

    def enrich_scan_titles(
        self,
        titles: list[dict[str, Any]],
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        items = []
        ok = 0
        for row in titles:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            year = row.get("year")
            if year is not None:
                try:
                    year = int(year)
                except (TypeError, ValueError):
                    year = None
            report = self.lookup(
                title,
                year=year,
                imdb_id=row.get("imdb_id"),
                original_title=row.get("original_title"),
                use_cache=use_cache,
            )
            if report.ok_count() > 0:
                ok += 1
            items.append(report.to_dict())
        return {
            "total": len(items),
            "with_any_score": ok,
            "items": items,
            "generated_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }

    def enrich_scan_db(
        self,
        db_path: str | Path,
        *,
        only_missing: bool = True,
        limit: int = 50,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        path = Path(db_path)
        con = sqlite3.connect(str(path))
        con.row_factory = sqlite3.Row
        try:
            tables = {
                r[0]
                for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "movie_items" not in tables:
                return {"error": "movie_items table not found", "db": str(path)}
            sql = """
                SELECT movie_id, title, original_title, year, imdb_id,
                       douban_rating, content_kind, series_title
                FROM movie_items
            """
            if only_missing:
                sql += """
                    WHERE (douban_rating IS NULL OR douban_rating = 0)
                """
            sql += " ORDER BY updated_at DESC LIMIT ?"
            rows = con.execute(sql, (limit,)).fetchall()
        finally:
            con.close()

        titles = [
            {
                "movie_id": r["movie_id"],
                "title": (
                    r["series_title"]
                    if r["content_kind"] == "series" and r["series_title"]
                    else r["title"]
                ),
                "original_title": r["original_title"],
                "year": r["year"],
                "imdb_id": r["imdb_id"],
            }
            for r in rows
        ]
        result = self.enrich_scan_titles(titles, use_cache=use_cache)
        result["db"] = str(path)
        result["only_missing"] = only_missing
        return result


def self_check(
    *,
    cache_dir: str | Path | None = None,
    use_cache: bool = False,
) -> dict[str, Any]:
    """Run golden samples; GOAL_MATCHED when enough sources produce scores."""
    resolver = RatingResolver(cache_dir=cache_dir)
    samples = [
        {"title": "The Shawshank Redemption", "year": 1994},
        {"title": "肖申克的救赎", "year": 1994},
        {"title": "Inception", "year": 2010},
    ]
    reports = []
    any_ok_samples = 0
    sources_ok: set[str] = set()
    for s in samples:
        rep = resolver.lookup(
            s["title"],
            year=s.get("year"),
            use_cache=use_cache,
            parallel=True,
        )
        d = rep.to_dict()
        reports.append(d)
        if rep.ok_count() > 0:
            any_ok_samples += 1
        for name, r in rep.ratings.items():
            if r.get("status") == "ok" and r.get("score") is not None:
                sources_ok.add(name)

    # Goal: at least 2 of 3 samples get a score; at least 1 provider channel works
    # Prefer 2+ distinct sources across all samples for multi-channel proof
    goal = any_ok_samples >= 2 and len(sources_ok) >= 1
    # stronger: if we got 2+ source types, even better
    strong = any_ok_samples >= 2 and len(sources_ok) >= 2

    return {
        "GOAL_MATCHED": goal,
        "GOAL_STRONG": strong,
        "samples_ok": any_ok_samples,
        "samples_total": len(samples),
        "sources_with_ok": sorted(sources_ok),
        "reports": reports,
        "criteria": {
            "independent_cli": True,
            "min_samples_with_score": 2,
            "min_source_channels": 1,
        },
    }
