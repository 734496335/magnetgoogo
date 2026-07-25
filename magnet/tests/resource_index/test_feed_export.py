"""Adult feed export tests."""

import json
from datetime import datetime, timezone

from magnet.resource_index.pipeline.export_feed import build_adult_feed, export_adult_feed
from magnet.resource_index.pipeline.ingest import ingest_fixture
from magnet.resource_index.errors import ResourceIndexError
import pytest


FIXED = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_feed_schema_and_isolation(repo, manifest_path, tmp_path):
    ingest_fixture(manifest_path=manifest_path, repo=repo, clock=lambda: FIXED)
    out = tmp_path / "feed.json"
    export_adult_feed(
        repo,
        out,
        scope="adult",
        include_review_fixtures=True,
        clock=lambda: FIXED,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["scope"] == "adult"
    assert data["source"] == "resource_index_test"
    assert data["items"]
    for item in data["items"]:
        assert item["adult"] is True
        assert "magnet" not in item
        assert "magnet_uri" not in item
        assert "gid" not in item
        assert item["cover"] is None

    # stable bytes with frozen clock
    feed1 = json.dumps(
        build_adult_feed(repo, include_review_fixtures=True, clock=lambda: FIXED),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    feed2 = json.dumps(
        build_adult_feed(repo, include_review_fixtures=True, clock=lambda: FIXED),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    assert feed1 == feed2


def test_general_scope_rejected(repo, tmp_path):
    with pytest.raises(ResourceIndexError):
        export_adult_feed(repo, tmp_path / "x.json", scope="general")
