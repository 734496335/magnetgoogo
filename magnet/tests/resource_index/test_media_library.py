from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from magnet.resource_index.domain.movie_models import MovieDetail, MovieResource
from magnet.resource_index.pipeline.media_library import export_source_library_feed
from magnet.resource_index.store.movie_repository import MovieRepository
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository


def _detail(index: int, *, update_date: date) -> MovieDetail:
    return MovieDetail(
        source_id="sixv",
        source_item_key=f"/{index}.html",
        content_code=f"movie-{index}",
        detail_url=f"https://www.6v520.com/dy/{index}.html",
        listing_title=f"电影{index}",
        title=f"电影{index}",
        original_title=None,
        year=2026,
        update_date=update_date,
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
        cover_source_url=f"https://images.example/{index}.jpg",
        synopsis=None,
        recommended=False,
        highlight_labels=(),
        quality_tags=(),
        parser_version="test/1",
        raw_document_hash=f"{index:064x}",
        resources=(
            MovieResource(
                resource_type="magnet",
                provider="magnet",
                resource_url=f"magnet:?xt=urn:btih:{index:040x}",
                info_hash=f"{index:040x}",
                display_title=f"资源{index}",
                extraction_code=None,
                quality_tags=(),
            ),
        ),
        brand_id="sixv",
        endpoint_origin="https://www.6v520.com",
    )


def test_export_source_library_includes_rows_outside_latest_window(tmp_path: Path) -> None:
    db_path = tmp_path / "sixv.db"
    output_path = tmp_path / "sixv-library.json"
    repo = SqliteResourceRepository(db_path)
    repo.init_schema()
    movie_repo = MovieRepository(repo)
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    movie_repo.upsert(_detail(1, update_date=date(2026, 7, 30)), now=now)
    movie_repo.upsert(_detail(2, update_date=date(2026, 7, 20)), now=now)
    repo.close()

    payload = export_source_library_feed(
        db_path=db_path,
        source_id="sixv",
        output_path=output_path,
        generated_at=now,
    )

    assert payload["library_scope"] == "durable_all"
    assert payload["summary"]["record_count"] == 2
    assert payload["summary"]["resource_count"] == 2
    assert [item["title"] for item in payload["items"]] == ["电影1", "电影2"]
    assert json.loads(output_path.read_text(encoding="utf-8"))["items"] == payload["items"]
