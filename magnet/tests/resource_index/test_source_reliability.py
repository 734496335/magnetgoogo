from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from magnet.resource_index.domain.movie_models import MovieDetail, MovieResource
from magnet.resource_index.pipeline.source_reliability import audit_source_reliability
from magnet.resource_index.store.movie_repository import MovieRepository
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _detail(index: int, *, cover: str | None = None, resources: tuple[MovieResource, ...] | None = None) -> MovieDetail:
    return MovieDetail(
        source_id="fixture-source",
        source_item_key=f"/{index}.html",
        content_code=str(index),
        detail_url=f"https://fixture.example/{index}.html",
        listing_title=f"Fixture {index}",
        title=f"Fixture {index}",
        original_title=None,
        year=2026,
        update_date=date(2026, 7, 30),
        release_date=None,
        duration_minutes=None,
        countries=("中国",),
        genres=("剧情",),
        languages=("国语",),
        directors=(),
        actors=(),
        imdb_id=None,
        douban_rating=None,
        douban_rating_text=None,
        douban_url=None,
        cover_source_url=cover if cover is not None else f"https://images.example/{index}.jpg",
        synopsis=None,
        recommended=False,
        highlight_labels=(),
        quality_tags=("1080p",),
        parser_version="fixture/1",
        raw_document_hash=f"{index:064x}",
        resources=resources
        if resources is not None
        else (
            MovieResource(
                resource_type="magnet",
                provider="magnet",
                resource_url=(
                    "magnet:?xt=urn:btih:"
                    f"{index + 1:040x}&dn=Fixture%20{index}"
                ),
                info_hash=f"{index + 1:040x}",
                display_title=f"Fixture {index} 1080p",
                extraction_code=None,
                quality_tags=("1080p",),
            ),
        ),
        brand_id="fixture-brand",
        endpoint_origin="https://fixture.example",
    )


def _build_fixture(tmp_path: Path, details: list[MovieDetail]) -> tuple[Path, Path]:
    db = tmp_path / "fixture.db"
    feed = tmp_path / "fixture-feed.json"
    repo = SqliteResourceRepository(db)
    repo.init_schema()
    movie_repo = MovieRepository(repo)
    for detail in details:
        movie_repo.upsert(detail, now=NOW)
    job_id = "latest-fixture-source-2-test"
    snapshot = {
        "schema_version": "fixture/1",
        "source_id": "fixture-source",
        "captured_at": "2026-07-30T12:00:00Z",
        "items": [
            {
                "rank": index,
                "detail_url": detail.detail_url,
                "source_item_key": detail.source_item_key,
                "content_code": detail.content_code,
                "listing_title": detail.listing_title,
            }
            for index, detail in enumerate(details, 1)
        ],
    }
    repo.conn.execute(
        """
        INSERT INTO latest_crawl_jobs(
            job_id, source_id, target_count, batch_size, max_attempts,
            snapshot_hash, snapshot_json, snapshot_path, feed_path, status,
            snapshot_http_requests, detail_http_requests,
            created_at, updated_at, completed_at, error_summary_json
        ) VALUES (?, ?, ?, 2, 3, ?, ?, ?, ?, 'success', 1, ?, ?, ?, ?, '{}')
        """,
        (
            job_id,
            "fixture-source",
            len(details),
            "a" * 64,
            json.dumps(snapshot),
            str(tmp_path / "snapshot.json"),
            str(feed),
            len(details),
            "2026-07-30T12:00:00Z",
            "2026-07-30T12:00:00Z",
            "2026-07-30T12:00:00Z",
        ),
    )
    for index, detail in enumerate(details, 1):
        repo.conn.execute(
            """
            INSERT INTO latest_crawl_items(
                job_id, rank, detail_url, content_code, listing_title,
                status, attempts, updated_at, source_item_key
            ) VALUES (?, ?, ?, ?, ?, 'success', 1, ?, ?)
            """,
            (
                job_id,
                index,
                detail.detail_url,
                detail.content_code,
                detail.listing_title,
                "2026-07-30T12:00:00Z",
                detail.source_item_key,
            ),
        )
    items = [
        movie_repo.feed_item(
            source_id="fixture-source",
            detail_url=detail.detail_url,
            source_item_key=detail.source_item_key,
            rank=index,
        )
        for index, detail in enumerate(details, 1)
    ]
    repo.close()
    feed.write_text(
        json.dumps(
            {
                "schema_version": "movie-feed/1",
                "source_id": "fixture-source",
                "generated_at": "2026-07-30T12:00:00Z",
                "items": items,
                "summary": {
                    "record_count": len(items),
                    "target_count": len(items),
                    "resource_count": sum(len(item["resources"]) for item in items if item),
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return db, feed


def test_source_reliability_passes_complete_durable_feed(tmp_path: Path) -> None:
    db, feed = _build_fixture(tmp_path, [_detail(0), _detail(1)])
    report = audit_source_reliability(
        source_id="fixture-source",
        db_path=db,
        feed_path=feed,
        expected_count=2,
    )
    assert report["status"] == "pass"
    assert report["crawl_item_state_counts"] == {"success": 2}
    assert report["summary"]["app_resource_count"] == 2
    assert report["summary"]["cover_missing_count"] == 0


def test_source_reliability_rejects_missing_cover_and_non_app_only_resource(tmp_path: Path) -> None:
    download = MovieResource(
        resource_type="download",
        provider="fixture",
        resource_url="https://download.example/file.zip",
        info_hash=None,
        display_title="download",
        extraction_code=None,
        quality_tags=(),
    )
    db, feed = _build_fixture(tmp_path, [_detail(0, cover="", resources=(download,)), _detail(1)])
    report = audit_source_reliability(
        source_id="fixture-source",
        db_path=db,
        feed_path=feed,
        expected_count=2,
    )
    assert report["status"] == "fail"
    codes = {error["code"] for error in report["errors"]}
    assert "COVER_MISSING" in codes
    assert "APP_RESOURCE_EMPTY" not in codes
    assert any(warning["code"] == "APP_RESOURCE_EMPTY" for warning in report["warnings"])

    strict = audit_source_reliability(
        source_id="fixture-source",
        db_path=db,
        feed_path=feed,
        expected_count=2,
        require_app_resources=True,
    )
    strict_codes = {error["code"] for error in strict["errors"]}
    assert "APP_RESOURCE_EMPTY" in strict_codes


def test_source_reliability_reports_cross_item_duplicate_as_warning(tmp_path: Path) -> None:
    shared = MovieResource(
        resource_type="magnet",
        provider="magnet",
        resource_url="magnet:?xt=urn:btih:1111111111111111111111111111111111111111",
        info_hash="1111111111111111111111111111111111111111",
        display_title="shared",
        extraction_code=None,
        quality_tags=(),
    )
    db, feed = _build_fixture(tmp_path, [_detail(0, resources=(shared,)), _detail(1, resources=(shared,))])
    report = audit_source_reliability(
        source_id="fixture-source",
        db_path=db,
        feed_path=feed,
        expected_count=2,
    )
    assert report["status"] == "pass"
    assert report["summary"]["cross_item_duplicate_resource_count"] == 1
    assert report["warnings"][0]["code"] == "CROSS_ITEM_RESOURCE_DUPLICATES"

    strict = audit_source_reliability(
        source_id="fixture-source",
        db_path=db,
        feed_path=feed,
        expected_count=2,
        require_app_resources=True,
    )
    assert strict["status"] == "fail"
    assert any(error["code"] == "CROSS_ITEM_RESOURCE_DUPLICATES" for error in strict["errors"])


def test_source_reliability_accepts_qualified_feed_from_larger_discovery_window(tmp_path: Path) -> None:
    db, feed = _build_fixture(tmp_path, [_detail(0), _detail(1), _detail(2)])
    payload = json.loads(feed.read_text(encoding="utf-8"))
    payload["items"] = payload["items"][:2]
    payload["summary"]["record_count"] = 2
    payload["summary"]["target_count"] = 2
    payload["summary"]["discovery_target_count"] = 3
    feed.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = audit_source_reliability(
        source_id="fixture-source",
        db_path=db,
        feed_path=feed,
        expected_count=2,
        require_app_resources=True,
    )
    assert report["status"] == "pass"
    assert report["summary"]["discovery_target_count"] == 3
    assert report["crawl_item_state_counts"] == {"success": 3}

    repo = SqliteResourceRepository(db)
    repo.conn.execute(
        "UPDATE latest_crawl_items SET status = 'failed', attempts = 3, last_error_code = 'LIVE_HTTP_ERROR' WHERE rank = 3"
    )
    repo.conn.commit()
    repo.close()
    with_spare_failure = audit_source_reliability(
        source_id="fixture-source",
        db_path=db,
        feed_path=feed,
        expected_count=2,
        require_app_resources=True,
    )
    assert with_spare_failure["status"] == "pass"
    assert with_spare_failure["crawl_item_state_counts"] == {"failed": 1, "success": 2}
