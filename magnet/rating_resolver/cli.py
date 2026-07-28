# -*- coding: utf-8 -*-
"""CLI: python -m magnet.rating_resolver ..."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _print(data: Any, pretty: bool) -> None:
    if pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False))


def cmd_lookup(args: argparse.Namespace) -> int:
    from magnet.rating_resolver.service import RatingResolver

    sources = None
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    resolver = RatingResolver(cache_dir=args.cache_dir, sources=sources)
    report = resolver.lookup(
        args.title,
        year=args.year,
        imdb_id=args.imdb_id,
        use_cache=not args.no_cache,
        parallel=not args.serial,
    )
    _print(report.to_dict(), args.pretty)
    return 0 if report.ok_count() > 0 else 2


def cmd_enrich_scan(args: argparse.Namespace) -> int:
    from magnet.rating_resolver.service import RatingResolver

    sources = None
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    resolver = RatingResolver(cache_dir=args.cache_dir, sources=sources)

    if args.db:
        result = resolver.enrich_scan_db(
            args.db,
            only_missing=not args.all_rows,
            limit=args.limit,
            use_cache=not args.no_cache,
        )
    elif args.titles_file:
        path = Path(args.titles_file)
        text = path.read_text(encoding="utf-8")
        titles: list[dict] = []
        if path.suffix.lower() == ".json":
            data = json.loads(text)
            if isinstance(data, list):
                for x in data:
                    if isinstance(x, str):
                        titles.append({"title": x})
                    elif isinstance(x, dict):
                        titles.append(x)
            elif isinstance(data, dict) and "titles" in data:
                titles = list(data["titles"])
        else:
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # title | year | imdb_id
                parts = [p.strip() for p in line.split("|")]
                row: dict[str, Any] = {"title": parts[0]}
                if len(parts) > 1 and parts[1]:
                    try:
                        row["year"] = int(parts[1])
                    except ValueError:
                        pass
                if len(parts) > 2 and parts[2]:
                    row["imdb_id"] = parts[2]
                titles.append(row)
        if args.limit:
            titles = titles[: args.limit]
        result = resolver.enrich_scan_titles(titles, use_cache=not args.no_cache)
    else:
        print("error: need --db or --titles-file", file=sys.stderr)
        return 1

    out = Path(args.output) if args.output else None
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
        print(f"wrote={out}")
        print(f"total={result.get('total')}")
        print(f"with_any_score={result.get('with_any_score')}")
    else:
        print(payload)
    return 0


def cmd_self_check(args: argparse.Namespace) -> int:
    from magnet.rating_resolver.service import self_check

    result = self_check(cache_dir=args.cache_dir, use_cache=not args.no_cache)
    _print(result, pretty=True)
    matched = bool(result.get("GOAL_MATCHED"))
    print(f"GOAL_MATCHED={str(matched).lower()}")
    print(f"GOAL_STRONG={str(bool(result.get('GOAL_STRONG'))).lower()}")
    return 0 if matched else 1


def cmd_writeback(args: argparse.Namespace) -> int:
    from magnet.rating_resolver.writeback import run_writeback

    summary = run_writeback(
        overwrite=args.overwrite,
        limit=args.limit,
        dry_run=args.dry_run,
        include_sqlite=not args.skip_sqlite,
        cache_dir=args.cache_dir,
    )
    feeds = summary.get("feeds") or []
    changed = sum(int(f.get("changed_items") or 0) for f in feeds if isinstance(f, dict))
    errors = sum(int(f.get("errors") or 0) for f in feeds if isinstance(f, dict))
    print(f"feeds={len(feeds)} changed_items_total={changed} errors_total={errors}")
    return 1 if errors and not changed else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="magnet.rating_resolver",
        description="独立影视评分爬虫：豆瓣/IMDb/烂番茄/Bangumi（第三方补偿）",
    )
    p.add_argument("--cache-dir", default="data/rating_cache", help="评分缓存目录")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("lookup", help="查询单部影片评分")
    s.add_argument("title", help="片名")
    s.add_argument("--year", type=int, default=None)
    s.add_argument("--imdb-id", default=None)
    s.add_argument("--sources", default=None, help="comma list: douban,imdb,rt,bangumi")
    s.add_argument("--no-cache", action="store_true")
    s.add_argument("--serial", action="store_true", help="串行请求各源")
    s.add_argument("--pretty", action="store_true", default=True)
    s.add_argument("--compact", action="store_true")
    s.set_defaults(func=cmd_lookup)

    s = sub.add_parser("enrich-scan", help="批量扫描标题或 SQLite movie_items（只读）")
    s.add_argument("--db", default=None, help="resource_index sqlite path")
    s.add_argument("--titles-file", default=None, help="txt(line) or json list")
    s.add_argument("--all-rows", action="store_true", help="扫库时不限缺分")
    s.add_argument("--limit", type=int, default=30)
    s.add_argument("--sources", default=None)
    s.add_argument("--no-cache", action="store_true")
    s.add_argument("-o", "--output", default=None)
    s.set_defaults(func=cmd_enrich_scan)

    s = sub.add_parser("self-check", help="金样例验收，打印 GOAL_MATCHED")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_self_check)

    s = sub.add_parser(
        "writeback",
        help="查评分并回写离线 movie/series feed（及可选 sqlite）",
    )
    s.add_argument("--overwrite", action="store_true", help="覆盖已有有效评分")
    s.add_argument("--limit", type=int, default=None, help="每个 feed 最多处理 N 条")
    s.add_argument("--dry-run", action="store_true", help="只查询不写文件")
    s.add_argument("--skip-sqlite", action="store_true", help="不写 movie_items 库")
    s.set_defaults(func=cmd_writeback)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "compact", False):
        args.pretty = False
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
