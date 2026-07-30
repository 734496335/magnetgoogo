from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from magnet.resource_index.domain.movie_models import MovieDetail, MovieResource
from magnet.resource_index.pipeline.dytt_maintenance import normalize_dytt_player_resources
from magnet.resource_index.store.movie_repository import MovieRepository
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _detail(urls: tuple[str, ...]) -> MovieDetail:
    return MovieDetail(
        source_id="dytt8899",
        source_item_key="/i/1.html",
        content_code="1",
        detail_url="https://www.dytt8899.com/i/1.html",
        listing_title="测试",
        title="测试",
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
        parser_version="dytt-parser/1.0.0",
        raw_document_hash="a" * 64,
        resources=tuple(
            MovieResource(
                resource_type="player",
                provider="jianpian",
                resource_url=url,
                info_hash=None,
                display_title="正片",
                extraction_code=None,
                quality_tags=(),
            )
            for url in urls
        ),
    )


def test_normalize_dytt_player_resources_is_idempotent(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "dytt.db")
    repo.init_schema()
    MovieRepository(repo).upsert(
        _detail(("jianpian://pathtype=url&path=https://video.example/1.m3u8",)),
        now=NOW,
    )

    first = normalize_dytt_player_resources(repo)
    second = normalize_dytt_player_resources(repo)
    row = repo.conn.execute(
        "SELECT provider, resource_url FROM movie_external_resources"
    ).fetchone()
    repo.close()

    assert first.examined == 1
    assert first.repaired == 1
    assert second.examined == 0
    assert row["provider"] == "m3u8"
    assert row["resource_url"] == "https://video.example/1.m3u8"


def test_normalize_dytt_player_resources_merges_existing_target(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "dytt.db")
    repo.init_schema()
    movie_repo = MovieRepository(repo)
    movie_repo.upsert(
        _detail(
            (
                "jianpian://pathtype=url&path=https://video.example/1.m3u8",
                "https://video.example/1.m3u8",
            )
        ),
        now=NOW,
    )

    result = normalize_dytt_player_resources(repo)
    rows = repo.conn.execute(
        "SELECT provider, resource_url FROM movie_external_resources"
    ).fetchall()
    repo.close()

    assert result.merged == 1
    assert len(rows) == 1
    assert rows[0]["provider"] == "m3u8"
    assert rows[0]["resource_url"] == "https://video.example/1.m3u8"
