"""CLI entry: python -m magnet.resource_index.cli ..."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
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


def _print_media_dependency_error(exc: ModuleNotFoundError) -> int:
    print("error_code=CONFIG_ERROR", file=sys.stderr)
    print(
        "message=media release signing dependency is missing; run deploy\\resource-index\\setup.bat",
        file=sys.stderr,
    )
    print(f"dependency={exc.name}", file=sys.stderr)
    return 1


def cmd_init_media_signing_key(args: argparse.Namespace) -> int:
    try:
        from magnet.resource_index.release.protocol import generate_ed25519_keypair

        result = generate_ed25519_keypair(
            args.private_key,
            args.public_key,
        )
        _print_json({"status": result.get("key_state", "ready"), **result}, pretty=True)
        return 0
    except ModuleNotFoundError as exc:
        return _print_media_dependency_error(exc)
    except ResourceIndexError as exc:
        print(f"error_code={exc.error_code}", file=sys.stderr)
        print(f"message={exc.message}", file=sys.stderr)
        return 1


def cmd_build_media_release(args: argparse.Namespace) -> int:
    try:
        from magnet.resource_index.release.builder import MediaReleaseConfig, build_media_release

        config = MediaReleaseConfig(
            movie_feed_path=Path(args.movie_feed),
            series_feed_path=Path(args.series_feed),
            movie_cover_bundle=Path(args.movie_cover_bundle),
            series_cover_bundle=Path(args.series_cover_bundle),
            output_dir=Path(args.output_dir),
            private_key_path=Path(args.private_key),
            public_key_path=Path(args.public_key),
            pointer_revision=args.pointer_revision,
            min_app_version=args.min_app_version,
            page_size=args.page_size,
            min_movies=args.min_movies,
            min_series=args.min_series,
            max_object_bytes=args.max_object_bytes,
            previous_manifest_path=Path(args.previous_manifest) if args.previous_manifest else None,
            allow_regression_reason=args.allow_regression,
        )
        result = build_media_release(config)
        _print_json(result.__dict__, pretty=True)
        return 0
    except ModuleNotFoundError as exc:
        return _print_media_dependency_error(exc)
    except ResourceIndexError as exc:
        print(f"error_code={exc.error_code}", file=sys.stderr)
        print(f"message={exc.message}", file=sys.stderr)
        if exc.context:
            print(f"context={json.dumps(exc.context, ensure_ascii=False, sort_keys=True)}", file=sys.stderr)
        return 1


def cmd_verify_media_release(args: argparse.Namespace) -> int:
    try:
        from magnet.resource_index.release.builder import verify_media_release

        result = verify_media_release(args.release_dir, args.public_key, args.current)
        _print_json(result, pretty=True)
        return 0
    except ModuleNotFoundError as exc:
        return _print_media_dependency_error(exc)
    except ResourceIndexError as exc:
        print(f"error_code={exc.error_code}", file=sys.stderr)
        print(f"message={exc.message}", file=sys.stderr)
        if exc.context:
            print(f"context={json.dumps(exc.context, ensure_ascii=False, sort_keys=True)}", file=sys.stderr)
        return 1


def cmd_publish_media_r2_staging(args: argparse.Namespace) -> int:
    if not args.yes and not args.dry_run:
        print("error_code=LIVE_POLICY_NOT_ACKNOWLEDGED", file=sys.stderr)
        print(
            "message=pass --yes to acknowledge remote upload to the isolated R2 staging destination",
            file=sys.stderr,
        )
        return 1
    if not args.prefix.strip().startswith("m2-test"):
        print("error_code=PUBLISH_CONFIG_ERROR", file=sys.stderr)
        print("message=M2 R2 staging prefix must begin with m2-test", file=sys.stderr)
        return 1
    try:
        from magnet.resource_index.publish.orchestrator import (
            MediaPublishConfig,
            build_media_publish_plan,
            publish_media_release,
        )
        from magnet.resource_index.publish.r2 import R2PublisherBackend

        publish_config = MediaPublishConfig(
            release_dir=Path(args.release_dir),
            current_path=Path(args.current),
            public_key_path=Path(args.public_key),
            receipt_dir=Path(args.receipt_dir),
            max_workers=args.max_workers,
            deep_verify=not args.shallow_verify,
            upload_pointer_candidate=not args.no_pointer_candidate,
        )
        if args.dry_run:
            plan = build_media_publish_plan(publish_config)
            _print_json(
                {
                    "status": "dry-run",
                    "bucket": args.bucket,
                    "prefix": args.prefix,
                    "release_id": plan.release_id,
                    "pointer_revision": plan.pointer_revision,
                    "manifest_sha256": plan.manifest_sha256,
                    "verified_object_count": plan.verified_object_count,
                    "object_count": plan.object_count,
                    "artifact_count": plan.artifact_count,
                    "total_file_count": plan.total_file_count,
                    "total_bytes": plan.total_bytes,
                    "upload_pointer_candidate": plan.upload_pointer_candidate,
                    "object_kinds": plan.object_kinds,
                    "first_keys": [request.key for request in plan.requests[:5]],
                    "last_keys": [request.key for request in plan.requests[-5:]],
                    "current_promoted": False,
                    "remote_requests": 0,
                },
                pretty=True,
            )
            return 0
        if args.worker_bridge_url:
            from magnet.resource_index.publish.worker_bridge import WorkerR2PublisherBackend

            backend = WorkerR2PublisherBackend(
                worker_url=args.worker_bridge_url,
                upload_token=os.environ.get("R2_UPLOAD_WORKER_TOKEN", ""),
                prefix=args.prefix,
            )
        elif args.temporary_credentials:
            from magnet.resource_index.publish.temporary_credentials import (
                mint_temporary_r2_credentials_from_environment,
            )

            temporary = mint_temporary_r2_credentials_from_environment(
                bucket=args.bucket,
                prefix=args.prefix,
                ttl_seconds=args.credential_ttl_seconds,
            )
            backend = R2PublisherBackend(
                bucket=args.bucket,
                prefix=args.prefix,
                account_id=os.environ.get("R2_ACCOUNT_ID"),
                access_key_id=temporary.access_key_id,
                secret_access_key=temporary.secret_access_key,
                session_token=temporary.session_token,
            )
        else:
            backend = R2PublisherBackend.from_environment(
                bucket=args.bucket,
                prefix=args.prefix,
            )
        result = publish_media_release(backend, publish_config)
        _print_json(result.__dict__, pretty=True)
        return 0
    except ModuleNotFoundError as exc:
        print("error_code=PUBLISH_CONFIG_ERROR", file=sys.stderr)
        print(
            "message=media R2 publishing dependency is missing; run deploy\\resource-index\\setup.bat",
            file=sys.stderr,
        )
        print(f"dependency={exc.name}", file=sys.stderr)
        return 1
    except ResourceIndexError as exc:
        print(f"error_code={exc.error_code}", file=sys.stderr)
        print(f"message={exc.message}", file=sys.stderr)
        if exc.context:
            print(f"context={json.dumps(exc.context, ensure_ascii=False, sort_keys=True)}", file=sys.stderr)
        return 1


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
        "init-media-signing-key",
        help="Create the local Ed25519 keypair used to sign media releases",
    )
    s.add_argument(
        "--private-key",
        default="data/resource_index/.secrets/media-ed25519-private.pem",
    )
    s.add_argument(
        "--public-key",
        default="data/resource_index/.secrets/media-ed25519-public.pem",
    )
    s.set_defaults(func=cmd_init_media_signing_key)

    s = sub.add_parser(
        "build-media-release",
        help="Build and preflight a signed local media release without network publishing",
    )
    s.add_argument("--movie-feed", default="data/resource_index/movies_latest_100_feed.json")
    s.add_argument("--series-feed", default="data/resource_index/series_latest_100_feed.json")
    s.add_argument("--movie-cover-bundle", default="data/resource_index/movie_app_bundle")
    s.add_argument("--series-cover-bundle", default="data/resource_index/series_app_bundle")
    s.add_argument("--output-dir", default="data/resource_index/media_releases")
    s.add_argument(
        "--private-key",
        default="data/resource_index/.secrets/media-ed25519-private.pem",
    )
    s.add_argument(
        "--public-key",
        default="data/resource_index/.secrets/media-ed25519-public.pem",
    )
    s.add_argument("--pointer-revision", type=int, default=1)
    s.add_argument("--min-app-version", default="0.2.1")
    s.add_argument("--page-size", type=int, default=50)
    s.add_argument("--min-movies", type=int, default=100)
    s.add_argument("--min-series", type=int, default=100)
    s.add_argument("--max-object-bytes", type=int, default=524288)
    s.add_argument("--previous-manifest", default=None)
    s.add_argument(
        "--allow-regression",
        default=None,
        help="Explicit reason for an intentional count/cover regression",
    )
    s.set_defaults(func=cmd_build_media_release)

    s = sub.add_parser(
        "verify-media-release",
        help="Verify signatures, hashes, sizes and paths in a staged media release",
    )
    s.add_argument("--release-dir", required=True)
    s.add_argument("--current", required=True, help="Signed current.json pointer candidate")
    s.add_argument(
        "--public-key",
        default="data/resource_index/.secrets/media-ed25519-public.pem",
    )
    s.set_defaults(func=cmd_verify_media_release)

    s = sub.add_parser(
        "publish-media-r2-staging",
        help="Upload a verified release to an isolated R2 M2 prefix without promoting current.json",
    )
    s.add_argument("--release-dir", required=True)
    s.add_argument("--current", required=True, help="Signed staging pointer candidate")
    s.add_argument(
        "--public-key",
        default="data/resource_index/.secrets/media-ed25519-public.pem",
    )
    s.add_argument("--bucket", default="magnetgoogo-media-m2-test")
    s.add_argument("--prefix", default="m2-test")
    s.add_argument("--receipt-dir", default="data/resource_index/media_publish_receipts")
    s.add_argument("--max-workers", type=int, default=8)
    s.add_argument(
        "--temporary-credentials",
        action="store_true",
        help="Mint short-lived prefix-scoped R2 S3 credentials from parent environment variables",
    )
    s.add_argument("--credential-ttl-seconds", type=int, default=900)
    s.add_argument(
        "--worker-bridge-url",
        default=None,
        help="Temporary authenticated Worker URL used when Wrangler OAuth is the only R2 credential",
    )
    s.add_argument("--shallow-verify", action="store_true")
    s.add_argument("--no-pointer-candidate", action="store_true")
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify and print the complete local upload plan without credentials or remote requests",
    )
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_publish_media_r2_staging)

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
