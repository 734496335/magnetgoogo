from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from magnet.rating_resolver.writeback import enrich_feed_file


def _feed(path: Path, count: int = 5) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "media-feed/1",
                "generated_at": "2026-07-31T00:00:00Z",
                "items": [
                    {
                        "movie_id": f"movie:{index}",
                        "title": f"Title {index}",
                        "year": 2026,
                    }
                    for index in range(count)
                ],
            }
        ),
        encoding="utf-8",
    )


class RecordingResolver:
    def __init__(self) -> None:
        self.titles: list[str] = []

    def lookup(self, title: str, **_kwargs):
        self.titles.append(title)
        return SimpleNamespace(ratings={}, display=[])


def test_rating_lookup_budget_rotates_without_starving_later_items(tmp_path: Path) -> None:
    path = tmp_path / "feed.json"
    _feed(path)
    resolver = RecordingResolver()

    first = enrich_feed_file(
        path,
        resolver,
        lookup_limit=2,
        start_offset=0,
        dry_run=True,
    )
    second = enrich_feed_file(
        path,
        resolver,
        lookup_limit=2,
        start_offset=first["next_offset"],
        dry_run=True,
    )
    third = enrich_feed_file(
        path,
        resolver,
        lookup_limit=2,
        start_offset=second["next_offset"],
        dry_run=True,
    )

    assert resolver.titles == ["Title 0", "Title 1", "Title 2", "Title 3", "Title 4", "Title 0"]
    assert first["lookup_attempts"] == 2
    assert first["next_offset"] == 2
    assert second["next_offset"] == 4
    assert third["next_offset"] == 1


def test_rating_lookup_budget_counts_provider_errors_and_advances(tmp_path: Path) -> None:
    path = tmp_path / "feed.json"
    _feed(path, count=3)

    class FailingResolver:
        def lookup(self, *_args, **_kwargs):
            raise RuntimeError("provider unavailable")

    result = enrich_feed_file(
        path,
        FailingResolver(),
        lookup_limit=2,
        start_offset=1,
        dry_run=True,
    )

    assert result["lookup_attempts"] == 2
    assert result["errors"] == 2
    assert result["next_offset"] == 0


def test_rating_lookup_budget_skips_complete_items_without_consuming_budget(tmp_path: Path) -> None:
    path = tmp_path / "feed.json"
    _feed(path, count=3)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"][0].update(
        {
            "douban_rating": 8.0,
            "imdb_rating": 7.5,
            "rotten_tomatoes_rating": 85,
            "bangumi_rating": 7.0,
        }
    )
    path.write_text(json.dumps(data), encoding="utf-8")
    resolver = RecordingResolver()

    result = enrich_feed_file(
        path,
        resolver,
        lookup_limit=2,
        start_offset=0,
        dry_run=True,
    )

    assert resolver.titles == ["Title 1", "Title 2"]
    assert result["visited"] == 3
    assert result["lookup_attempts"] == 2
    assert result["next_offset"] == 0
