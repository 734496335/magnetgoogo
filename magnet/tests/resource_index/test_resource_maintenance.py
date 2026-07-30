from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from magnet.resource_index.domain.movie_models import MovieDetail, MovieResource
from magnet.resource_index.pipeline.resource_maintenance import normalize_durable_resources
from magnet.resource_index.store.movie_repository import MovieRepository
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _detail(resources: tuple[MovieResource, ...]) -> MovieDetail:
    return MovieDetail(
        source_id="fixture",
        source_item_key="/1",
        content_code="1",
        detail_url="https://fixture.example/1",
        listing_title="Fixture",
        title="Fixture",
        original_title=None,
        year=2026,
        update_date=date(2026, 7, 30),
        release_date=None,
        duration_minutes=None,
        countries=(),
        genres=(),
        languages=(),
        directors=(),
        actors=(),
        imdb_id=None,
        douban_rating=None,
        douban_rating_text=None,
        douban_url=None,
        cover_source_url="https://images.example/1.jpg",
        synopsis=None,
        recommended=False,
        highlight_labels=(),
        quality_tags=(),
        parser_version="fixture/1",
        raw_document_hash="a" * 64,
        resources=resources,
    )


def test_resource_maintenance_repairs_http_typo_and_deduplicates_hash(tmp_path: Path) -> None:
    duplicate_hash = "1" * 40
    resources = (
        MovieResource(
            resource_type="cloud",
            provider="quark",
            resource_url="ttps://pan.quark.cn/s/example",
            info_hash=None,
            display_title="quark",
            extraction_code=None,
            quality_tags=(),
        ),
        MovieResource(
            resource_type="magnet",
            provider="magnet",
            resource_url=f"magnet:?xt=urn:btih:{duplicate_hash}&dn=Fixture",
            info_hash=duplicate_hash,
            display_title="Fixture 1080p",
            extraction_code=None,
            quality_tags=("1080p",),
        ),
        MovieResource(
            resource_type="magnet",
            provider="magnet",
            resource_url=f"magnet:?xt=urn:btih:{duplicate_hash}&dn=Fixture&tr=udp://tracker.example:80/announce",
            info_hash=duplicate_hash,
            display_title="Fixture 4K",
            extraction_code=None,
            quality_tags=("4K",),
        ),
    )
    repo = SqliteResourceRepository(tmp_path / "fixture.db")
    repo.init_schema()
    MovieRepository(repo).upsert(_detail(resources), now=NOW)

    first = normalize_durable_resources(repo, source_id="fixture")
    second = normalize_durable_resources(repo, source_id="fixture")
    rows = repo.conn.execute(
        "SELECT resource_type, resource_url, info_hash FROM movie_resources ORDER BY resource_type"
    ).fetchall()
    repo.close()

    assert first.malformed_urls_repaired == 1
    assert first.duplicate_magnets_removed == 1
    assert second.malformed_urls_repaired == 0
    assert second.duplicate_magnets_removed == 0
    assert len(rows) == 2
    assert any(row["resource_url"] == "https://pan.quark.cn/s/example" for row in rows)
    magnet = next(row for row in rows if row["resource_type"] == "magnet")
    assert magnet["info_hash"] == duplicate_hash
    assert "tracker.example" in magnet["resource_url"]
