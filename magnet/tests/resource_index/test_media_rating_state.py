from __future__ import annotations

import json
from pathlib import Path

import pytest

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline.media_rating_state import (
    apply_media_rating_state,
    load_media_rating_state,
    persist_media_rating_state,
)


def _write_feed(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "media-feed/1",
                "content_kind_filter": item["content_kind"],
                "items": [item],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _rated_item() -> dict:
    return {
        "movie_id": "movie:test:2026",
        "content_kind": "movie",
        "title": "Test Movie",
        "year": 2026,
        "imdb_id": "tt1234567",
        "imdb_rating": 7.8,
        "imdb_rating_text": "7.8/10",
        "douban_rating": 8.1,
        "douban_rating_text": "8.1/10",
        "douban_url": "https://movie.douban.com/subject/123/",
        "rotten_tomatoes_rating": 91,
        "rotten_tomatoes_rating_text": "91%",
        "rotten_tomatoes_url": "https://www.rottentomatoes.com/m/test_movie",
        "bangumi_rating": 7.4,
        "bangumi_rating_text": "7.4/10",
        "bangumi_subject_id": "456",
        "bangumi_url": "https://bgm.tv/subject/456",
    }


def test_rating_state_persists_and_restores_all_four_sources(tmp_path: Path) -> None:
    feed = tmp_path / "movies.json"
    state = tmp_path / "ratings" / "media-ratings.json"
    _write_feed(feed, _rated_item())

    persisted = persist_media_rating_state(feed_paths=(feed,), state_path=state)
    assert persisted["stored_item_count"] == 1
    assert persisted["score_counts"] == {
        "imdb_rating": 1,
        "douban_rating": 1,
        "rotten_tomatoes_rating": 1,
        "bangumi_rating": 1,
    }

    stripped = {
        "movie_id": "movie:test:2026",
        "content_kind": "movie",
        "title": "Test Movie",
        "year": 2026,
    }
    _write_feed(feed, stripped)
    restored = apply_media_rating_state(feed_paths=(feed,), state_path=state)
    assert restored["restored_items"] == 1
    assert restored["restored_fields"] == 13

    item = json.loads(feed.read_text(encoding="utf-8"))["items"][0]
    assert item["imdb_rating"] == 7.8
    assert item["douban_rating"] == 8.1
    assert item["rotten_tomatoes_rating"] == 91.0
    assert item["bangumi_rating"] == 7.4
    assert item["bangumi_subject_id"] == "456"


def test_rating_state_never_clears_previous_values_on_empty_update(tmp_path: Path) -> None:
    feed = tmp_path / "movies.json"
    state = tmp_path / "media-ratings.json"
    _write_feed(feed, _rated_item())
    persist_media_rating_state(feed_paths=(feed,), state_path=state)

    _write_feed(
        feed,
        {
            "movie_id": "movie:test:2026",
            "content_kind": "movie",
            "title": "Test Movie",
            "year": 2026,
            "imdb_rating": None,
            "douban_rating": None,
            "rotten_tomatoes_rating": None,
            "bangumi_rating": None,
        },
    )
    second = persist_media_rating_state(feed_paths=(feed,), state_path=state)
    assert second["changed_items"] == 0

    stored = load_media_rating_state(state)["items"]["movie:test:2026"]["ratings"]
    assert stored["imdb_rating"] == 7.8
    assert stored["douban_rating"] == 8.1
    assert stored["rotten_tomatoes_rating"] == 91.0
    assert stored["bangumi_rating"] == 7.4


def test_rating_state_keeps_safe_ids_but_rejects_bogus_or_out_of_range_scores(tmp_path: Path) -> None:
    feed = tmp_path / "movies.json"
    state = tmp_path / "media-ratings.json"
    item = _rated_item()
    item["imdb_rating"] = 0
    item["douban_rating"] = 11
    item["rotten_tomatoes_url"] = "https://www.rottentomatoes.com/m/the_odyssey_2026"
    item["bangumi_rating"] = float("inf")
    _write_feed(feed, item)

    result = persist_media_rating_state(feed_paths=(feed,), state_path=state)
    assert result["stored_item_count"] == 1
    assert result["rating_item_count"] == 1
    ratings = load_media_rating_state(state)["items"]["movie:test:2026"]["ratings"]
    assert ratings["imdb_id"] == "tt1234567"
    assert ratings["douban_url"] == "https://movie.douban.com/subject/123/"
    assert ratings["bangumi_subject_id"] == "456"
    assert "imdb_rating" not in ratings
    assert "douban_rating" not in ratings
    assert "rotten_tomatoes_rating" not in ratings
    assert "rotten_tomatoes_url" not in ratings
    assert "bangumi_rating" not in ratings


def test_rating_state_restores_imdb_id_without_imdb_score(tmp_path: Path) -> None:
    feed = tmp_path / "movies.json"
    state = tmp_path / "media-ratings.json"
    _write_feed(
        feed,
        {
            "movie_id": "movie:test:2026",
            "content_kind": "movie",
            "title": "Test Movie",
            "imdb_id": "tt1234567",
        },
    )
    persist_media_rating_state(feed_paths=(feed,), state_path=state)
    _write_feed(
        feed,
        {
            "movie_id": "movie:test:2026",
            "content_kind": "movie",
            "title": "Test Movie",
        },
    )
    restored = apply_media_rating_state(feed_paths=(feed,), state_path=state)
    assert restored["restored_fields"] == 1
    item = json.loads(feed.read_text(encoding="utf-8"))["items"][0]
    assert item["imdb_id"] == "tt1234567"
    assert item.get("imdb_rating") is None


def test_rating_state_rejects_content_kind_collision(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    state = tmp_path / "media-ratings.json"
    _write_feed(feed, _rated_item())
    persist_media_rating_state(feed_paths=(feed,), state_path=state)

    item = _rated_item()
    item["content_kind"] = "series"
    _write_feed(feed, item)
    with pytest.raises(ResourceIndexError, match="content kind collision"):
        persist_media_rating_state(feed_paths=(feed,), state_path=state)
