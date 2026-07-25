"""CLI entry: python -m magnet.resource_index.cli ..."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.registry import list_sources
from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.observability.events import log_event, setup_logging
from magnet.resource_index.pipeline.export_feed import export_adult_feed
from magnet.resource_index.pipeline.ingest import ingest_fixture
from magnet.resource_index.pipeline.ingest_live import ingest_live
from magnet.resource_index.pipeline.movie_cover_assets import (
    export_movie_app_bundle,
    sync_movie_covers,
)
from magnet.resource_index.pipeline.latest_crawl import (
    LatestCrawlPaths,
    LatestCrawlRunner,
    read_latest_status,
    run_deployment_doctor,
)
from magnet.resource_index.pipeline.sixv_latest import SixVLatestRunner
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository


def _print_json(data: Any, pretty: bool) -> None:
    if pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))


def _crawl_exit_code(status: str) -> int:
    if status == "success":
        return 0
    if status == "partial":
        return 2
    if status == "cancelled":
        return 130
    return 1


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
            "content_observations": c.content_observations,
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


def cmd_list_sources(_args: argparse.Namespace) -> int:
    sources = list_sources()
    _print_json(sources, pretty=True)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    paths = LatestCrawlPaths.for_output_dir(
        args.output_dir,
        source_id=args.source,
        target_count=args.count,
        db_path=args.db,
    )
    report = run_deployment_doctor(
        output_dir=paths.output_dir,
        db_path=paths.db_path,
        source_id=args.source,
    )
    _print_json(report, pretty=True)
    return 0 if report["status"] == "pass" else 1


def cmd_latest_status(args: argparse.Namespace) -> int:
    paths = LatestCrawlPaths.for_output_dir(
        args.output_dir,
        source_id=args.source,
        target_count=args.count,
        db_path=args.db,
    )
    repo = SqliteResourceRepository(paths.db_path)
    try:
        status = read_latest_status(
            repo=repo,
            paths=paths,
            source_id=args.source,
            target_count=args.count,
        )
        _print_json(status, pretty=True)
        return 0
    except ResourceIndexError as exc:
        print(f"error_code={exc.error_code}", file=sys.stderr)
        print(f"message={exc.message}", file=sys.stderr)
        return 1
    finally:
        repo.close()


def cmd_crawl_latest(args: argparse.Namespace) -> int:
    if not args.yes:
        print("error_code=LIVE_POLICY_NOT_ACKNOWLEDGED", file=sys.stderr)
        print(
            "message=pass --yes to acknowledge live crawl of the target source",
            file=sys.stderr,
        )
        return 1
    paths = LatestCrawlPaths.for_output_dir(
        args.output_dir,
        source_id=args.source,
        target_count=args.count,
        db_path=args.db,
    )
    logger = setup_logging(args.log or paths.log_path, append=True)
    repo = SqliteResourceRepository(paths.db_path)
    try:
        if args.source == "sixv":
            runner = SixVLatestRunner(
                repo=repo,
                paths=paths,
                target_count=args.count,
                batch_size=args.batch_size,
                max_attempts=args.max_attempts,
                delay_seconds=args.delay,
                snapshot_max_requests=args.snapshot_max_requests,
                batch_max_requests=args.batch_max_requests,
                max_listing_pages=args.max_listing_pages,
                logger=logger,
            )
            result = runner.run(
                refresh=args.refresh,
                max_batches=args.max_batches,
                reparse_incomplete=args.reparse_incomplete,
            )
        else:
            if args.reparse_incomplete:
                raise ResourceIndexError(
                    "CONFIG_ERROR",
                    "--reparse-incomplete is only supported for source=sixv",
                    {"source_id": args.source},
                )
            runner = LatestCrawlRunner(
                repo=repo,
                source_id=args.source,
                paths=paths,
                target_count=args.count,
                batch_size=args.batch_size,
                max_attempts=args.max_attempts,
                delay_seconds=args.delay,
                snapshot_max_requests=args.snapshot_max_requests,
                batch_max_requests=args.batch_max_requests,
                max_listing_pages=args.max_listing_pages,
                logger=logger,
            )
            result = runner.run(
                refresh=args.refresh,
                max_batches=args.max_batches,
            )
        _print_json(result.__dict__, pretty=True)
        if result.status == "success":
            return 0
        if result.status in {"pending", "partial", "paused"}:
            return 2
        return 1
    except KeyboardInterrupt:
        print("status=paused", file=sys.stderr)
        print("message=interrupted; rerun the same command to resume", file=sys.stderr)
        return 130
    except (ResourceIndexError, RuntimeError) as exc:
        if isinstance(exc, ResourceIndexError):
            print(f"error_code={exc.error_code}", file=sys.stderr)
            print(f"message={exc.message}", file=sys.stderr)
        else:
            print("error_code=LATEST_CRAWL_LOCKED", file=sys.stderr)
            print(f"message={exc}", file=sys.stderr)
        return 1
    finally:
        repo.close()


def cmd_sync_movie_covers(args: argparse.Namespace) -> int:
    if not args.yes:
        print("error_code=LIVE_POLICY_NOT_ACKNOWLEDGED", file=sys.stderr)
        print("message=pass --yes to acknowledge movie cover downloads", file=sys.stderr)
        return 1
    repo = SqliteResourceRepository(args.db)
    try:
        result = sync_movie_covers(
            repo,
            source_id=args.source,
            delay_seconds=args.delay,
            timeout_seconds=args.timeout,
        )
        _print_json(result.__dict__, pretty=True)
        return 0 if result.failed == 0 else 2
    except ResourceIndexError as exc:
        print(f"error_code={exc.error_code}", file=sys.stderr)
        print(f"message={exc.message}", file=sys.stderr)
        return 1
    finally:
        repo.close()


def cmd_export_movie_app_bundle(args: argparse.Namespace) -> int:
    repo = SqliteResourceRepository(args.db)
    try:
        result = export_movie_app_bundle(
            repo,
            feed_path=args.feed,
            output_dir=args.output_dir,
        )
        _print_json(result.__dict__, pretty=True)
        return 0
    except ResourceIndexError as exc:
        print(f"error_code={exc.error_code}", file=sys.stderr)
        print(f"message={exc.message}", file=sys.stderr)
        return 1
    finally:
        repo.close()


def cmd_crawl(args: argparse.Namespace) -> int:
    """Live crawl a source into the resource index DB."""
    if not args.yes:
        print(
            "error_code=LIVE_POLICY_NOT_ACKNOWLEDGED",
            file=sys.stderr,
        )
        print(
            "message=pass --yes to acknowledge live crawl of the target source",
            file=sys.stderr,
        )
        return 1
    logger = setup_logging(args.log)
    repo = SqliteResourceRepository(args.db)
    try:
        repo.init_schema()
        detail_urls = None
        if args.detail_url:
            detail_urls = list(args.detail_url)
        policy = LiveFetchPolicy.from_flags(
            env_enabled=True,
            acknowledged=args.yes,
            max_pages=args.max_pages,
            request_delay_seconds=args.delay,
        )
        result = ingest_live(
            repo=repo,
            source_id=args.source,
            query=args.query,
            detail_urls=detail_urls,
            listing_url=args.listing_url,
            limit=args.limit,
            policy=policy,
        )
        log_event(
            logger,
            run_id=result.run_id,
            source_id=args.source,
            stage="crawl",
            message="live crawl complete",
            status=result.status,
            contents_created=result.contents_created,
            resources_created=result.resources_created,
            errors=result.errors,
        )
        print(f"run_id={result.run_id}")
        print(f"status={result.status}")
        print(f"documents_seen={result.documents_seen}")
        print(f"contents_created={result.contents_created}")
        print(f"contents_updated={result.contents_updated}")
        print(f"resources_created={result.resources_created}")
        print(f"resources_updated={result.resources_updated}")
        print(f"http_requests={result.http_requests}")
        print(f"warnings={result.warnings}")
        print(f"errors={result.errors}")
        if result.error_summary:
            print(f"error_summary={json.dumps(result.error_summary, ensure_ascii=False)}")
        return _crawl_exit_code(result.status)
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

    s = sub.add_parser("list-sources")
    s.set_defaults(func=cmd_list_sources)

    s = sub.add_parser(
        "doctor",
        help="Check the portable resource-index runtime and output paths",
    )
    s.add_argument("--source", default="javbus")
    s.add_argument("--count", type=int, default=100)
    s.add_argument("--output-dir", default="data/resource_index")
    s.add_argument("--db", default=None)
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser(
        "latest-status",
        help="Show durable progress for the current latest-list snapshot",
    )
    s.add_argument("--source", default="javbus")
    s.add_argument("--count", type=int, default=100)
    s.add_argument("--output-dir", default="data/resource_index")
    s.add_argument("--db", default=None)
    s.set_defaults(func=cmd_latest_status)

    s = sub.add_parser(
        "crawl-latest",
        help="Snapshot and resumably ingest the latest source records",
    )
    s.add_argument("--source", default="javbus")
    s.add_argument("--count", type=int, default=100)
    s.add_argument("--output-dir", default="data/resource_index")
    s.add_argument("--db", default=None)
    s.add_argument("--batch-size", type=int, default=5)
    s.add_argument("--max-attempts", type=int, default=3)
    s.add_argument("--delay", type=float, default=10.0)
    s.add_argument("--snapshot-max-requests", type=int, default=20)
    s.add_argument("--batch-max-requests", type=int, default=16)
    s.add_argument("--max-listing-pages", type=int, default=20)
    s.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Process only this many batches, then exit 2 for a later resume",
    )
    s.add_argument(
        "--refresh",
        action="store_true",
        help="Capture a new latest-list snapshot instead of resuming the existing one",
    )
    s.add_argument(
        "--reparse-incomplete",
        action="store_true",
        help="For source=sixv, re-fetch current items missing genres or synopsis",
    )
    s.add_argument("--yes", action="store_true")
    s.add_argument("--log", default=None)
    s.set_defaults(func=cmd_crawl_latest)

    s = sub.add_parser(
        "sync-movie-covers",
        help="Download missing SixV movie covers into SQLite",
    )
    s.add_argument("--source", default="sixv")
    s.add_argument("--db", required=True)
    s.add_argument("--delay", type=float, default=1.5)
    s.add_argument("--timeout", type=float, default=30.0)
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_sync_movie_covers)

    s = sub.add_parser(
        "export-movie-app-bundle",
        help="Export the SixV movie feed and SQLite covers for App bundling",
    )
    s.add_argument("--db", required=True)
    s.add_argument("--feed", required=True)
    s.add_argument("--output-dir", required=True)
    s.set_defaults(func=cmd_export_movie_app_bundle)

    s = sub.add_parser(
        "crawl",
        help="Live crawl a source (javbus first) into the local resource index DB",
    )
    s.add_argument("--source", default="javbus")
    s.add_argument("--db", required=True)
    s.add_argument("--query", default=None, help="Search keyword (e.g. SSIS-960)")
    s.add_argument(
        "--detail-url",
        action="append",
        default=None,
        help="Direct detail URL (repeatable)",
    )
    s.add_argument(
        "--listing-url",
        default=None,
        help="Listing/home URL when not using --query",
    )
    s.add_argument("--limit", type=int, default=6, help="Max detail items to ingest")
    s.add_argument("--delay", type=float, default=10.0, help="Seconds between HTTP requests")
    s.add_argument(
        "--max-pages",
        type=int,
        default=40,
        help="Physical HTTP request budget for this run, including retries and redirects",
    )
    s.add_argument(
        "--yes",
        action="store_true",
        help="Acknowledge live crawl of the target source",
    )
    s.add_argument("--log", default=None)
    s.set_defaults(func=cmd_crawl)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
