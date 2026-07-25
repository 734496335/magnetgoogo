"""CLI entry: python -m magnet.resource_index.cli ..."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.observability.events import log_event, setup_logging
from magnet.resource_index.pipeline.export_feed import export_adult_feed
from magnet.resource_index.pipeline.ingest import ingest_fixture
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository


def _print_json(data: Any, pretty: bool) -> None:
    if pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))


def cmd_init_db(args: argparse.Namespace) -> int:
    repo = SqliteResourceRepository(args.db)
    try:
        version = repo.init_schema()
        print(f"schema_version={version}")
        print("status=ready")
        return 0
    finally:
        repo.close()


def cmd_ingest_fixture(args: argparse.Namespace) -> int:
    logger = setup_logging(args.log)
    repo = SqliteResourceRepository(args.db)
    try:
        repo.init_schema()
        result = ingest_fixture(
            manifest_path=args.manifest,
            repo=repo,
            source_id=args.source,
        )
        log_event(
            logger,
            run_id=result.run_id,
            source_id=args.source,
            stage="ingest",
            message="fixture ingest complete",
            status=result.status,
            contents_created=result.contents_created,
            errors=result.errors,
        )
        print(f"run_id={result.run_id}")
        print(f"status={result.status}")
        print(f"contents_created={result.contents_created}")
        print(f"contents_updated={result.contents_updated}")
        print(f"resources_created={result.resources_created}")
        print(f"resources_updated={result.resources_updated}")
        print(f"warnings={result.warnings}")
        print(f"errors={result.errors}")
        return 0 if result.status in {"success", "partial"} else 1
    except ResourceIndexError as exc:
        print(f"error_code={exc.error_code}", file=sys.stderr)
        print(f"message={exc.message}", file=sys.stderr)
        return 1
    finally:
        repo.close()


def cmd_show_content(args: argparse.Namespace) -> int:
    repo = SqliteResourceRepository(args.db)
    try:
        repo.init_schema()
        data = repo.get_content_by_code(args.content_code)
        if data is None:
            print("error_code=NOT_FOUND", file=sys.stderr)
            return 1
        # Strip internal risk if needed — keep for CLI audit
        _print_json(data, args.pretty)
        return 0
    finally:
        repo.close()


def cmd_search(args: argparse.Namespace) -> int:
    repo = SqliteResourceRepository(args.db)
    try:
        repo.init_schema()
        rows = repo.search_contents(args.query, limit=args.limit)
        _print_json(rows, args.pretty)
        return 0
    finally:
        repo.close()


def cmd_list_resources(args: argparse.Namespace) -> int:
    repo = SqliteResourceRepository(args.db)
    try:
        repo.init_schema()
        rows = repo.list_resources_for_content(args.content_code)
        # Optionally redact magnets unless --include-magnets
        if not args.include_magnets:
            for r in rows:
                r.pop("magnet_uri", None)
        _print_json(rows, args.pretty)
        return 0
    finally:
        repo.close()


def cmd_stats(args: argparse.Namespace) -> int:
    repo = SqliteResourceRepository(args.db)
    try:
        repo.init_schema()
        c = repo.counts()
        last = repo.last_successful_run()
        out = {
            "contents": c.contents,
            "people": c.people,
            "tags": c.tags,
            "resources": c.resources,
            "observations": c.observations,
            "contents_without_resources": c.contents_without_resources,
            "parse_warning_counts": repo.warning_counts(),
            "last_successful_run": last,
        }
        _print_json(out, True)
        return 0
    finally:
        repo.close()


def cmd_export_feed(args: argparse.Namespace) -> int:
    repo = SqliteResourceRepository(args.db)
    try:
        repo.init_schema()
        path = export_adult_feed(
            repo,
            args.output,
            scope=args.scope,
            limit=args.limit,
            include_review_fixtures=args.include_review_fixtures,
        )
        print(f"output={path}")
        print("scope=adult")
        print("status=ok")
        return 0
    except ResourceIndexError as exc:
        print(f"error_code={exc.error_code}", file=sys.stderr)
        print(f"message={exc.message}", file=sys.stderr)
        return 1
    finally:
        repo.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="magnet.resource_index.cli")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init-db")
    s.add_argument("--db", required=True)
    s.set_defaults(func=cmd_init_db)

    s = sub.add_parser("ingest-fixture")
    s.add_argument("--source", required=True)
    s.add_argument("--manifest", required=True)
    s.add_argument("--db", required=True)
    s.add_argument("--log", default=None)
    s.set_defaults(func=cmd_ingest_fixture)

    s = sub.add_parser("show-content")
    s.add_argument("content_code")
    s.add_argument("--db", required=True)
    s.add_argument("--pretty", action="store_true")
    s.set_defaults(func=cmd_show_content)

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--db", required=True)
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--pretty", action="store_true")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("list-resources")
    s.add_argument("content_code")
    s.add_argument("--db", required=True)
    s.add_argument("--pretty", action="store_true")
    s.add_argument("--include-magnets", action="store_true")
    s.set_defaults(func=cmd_list_resources)

    s = sub.add_parser("stats")
    s.add_argument("--db", required=True)
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("export-feed")
    s.add_argument("--scope", required=True)
    s.add_argument("--db", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--limit", type=int, default=100)
    s.add_argument("--include-review-fixtures", action="store_true")
    s.set_defaults(func=cmd_export_feed)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
