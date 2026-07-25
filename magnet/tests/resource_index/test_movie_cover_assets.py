from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

from magnet.resource_index.pipeline.movie_cover_assets import (
    _normalize_cover,
    export_movie_app_bundle,
)
from magnet.resource_index.store.movie_repository import MovieRepository
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository


NOW = datetime(2026, 7, 25, 15, 0, tzinfo=timezone.utc)
MOVIE_ID = "movie:" + "a" * 64


def _insert_movie(repo: SqliteResourceRepository) -> None:
    now_s = "2026-07-25T15:00:00Z"
    repo.conn.execute(
        """
        INSERT INTO movie_items(
            movie_id, source_id, source_item_key, detail_url,
            listing_title, title, original_title, year, update_date,
            release_date, duration_minutes, countries_json, genres_json,
            languages_json, directors_json, actors_json, imdb_id,
            douban_rating, douban_rating_text, douban_url,
            cover_source_url, synopsis, recommended,
            highlight_labels_json, quality_tags_json, parser_version,
            raw_document_hash, first_seen_at, last_seen_at,
            created_at, updated_at
        ) VALUES (
            ?, 'sixv', '/dy/test.html', 'https://www.6v520.com/dy/test.html',
            '2026动作《测试电影》4K', '测试电影', NULL, 2026, '2026-07-25',
            '2026-07-01', 120, '["中国"]', '["动作"]',
            '["国语"]', '["导演"]', '["演员"]', 'tt1234567',
            8.1, '8.1/10', NULL,
            'https://www.66tutup.com/test.jpg', '简介', 1,
            '["推荐"]', '["4K"]', 'sixv-parser/1',
            'abc', ?, ?, ?, ?
        )
        """,
        (MOVIE_ID, now_s, now_s, now_s, now_s),
    )


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (1200, 1800), (30, 80, 140))
    output = BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def test_normalize_cover_resizes_and_hashes() -> None:
    encoded, mime_type, width, height, digest = _normalize_cover(_jpeg_bytes())
    assert mime_type == "image/jpeg"
    assert width <= 720
    assert height <= 1080
    assert len(encoded) > 0
    assert len(digest) == 64


def test_cover_asset_is_stored_once_and_exported_to_app_bundle(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "movie.db")
    assert repo.init_schema() == "0005"
    _insert_movie(repo)
    encoded, mime_type, width, height, digest = _normalize_cover(_jpeg_bytes())
    movies = MovieRepository(repo)
    movies.upsert_cover_asset(
        movie_id=MOVIE_ID,
        source_url="https://www.66tutup.com/test.jpg",
        mime_type=mime_type,
        content_hash=digest,
        width=width,
        height=height,
        image_blob=encoded,
        fetched_at=NOW,
    )
    targets = movies.cover_targets(source_id="sixv")
    assert len(targets) == 1
    assert targets[0]["cover_stored"] == 1

    feed = {
        "schema_version": "movie-feed/1",
        "source_id": "sixv",
        "generated_at": "2026-07-25T15:00:00Z",
        "snapshot_captured_at": "2026-07-25T14:00:00Z",
        "items": [
            {
                "rank": 1,
                "movie_id": MOVIE_ID,
                "title": "测试电影",
                "recommended": True,
            }
        ],
        "summary": {"record_count": 1, "recommended_count": 1},
    }
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(json.dumps(feed, ensure_ascii=False), encoding="utf-8")
    result = export_movie_app_bundle(
        repo,
        feed_path=feed_path,
        output_dir=tmp_path / "bundle",
    )
    assert result.item_count == 1
    assert result.cover_count == 1
    app_feed = json.loads(Path(result.feed_path).read_text(encoding="utf-8"))
    assert app_feed["schema_version"] == "movie-app-feed/1"
    assert app_feed["summary"]["offline_ready"] is True
    cover_path = tmp_path / "bundle" / app_feed["items"][0]["cover_asset_path"]
    assert cover_path.read_bytes() == encoded
    repo.close()
