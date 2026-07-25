"""Idempotent double-import tests."""

from datetime import datetime, timezone

from magnet.resource_index.pipeline.ingest import ingest_fixture


FIXED = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_double_ingest_stable_counts(repo, manifest_path):
    r1 = ingest_fixture(manifest_path=manifest_path, repo=repo, clock=lambda: FIXED)
    c1 = repo.counts()
    r2 = ingest_fixture(manifest_path=manifest_path, repo=repo, clock=lambda: FIXED)
    c2 = repo.counts()

    assert c1.contents == c2.contents
    assert c1.people == c2.people
    assert c1.tags == c2.tags
    assert c1.content_people == c2.content_people
    assert c1.content_tags == c2.content_tags
    assert c1.resources == c2.resources
    assert c1.observations == c2.observations

    # seen_count should increase
    rows = repo.conn.execute("SELECT MAX(seen_count) AS m FROM resource_observations").fetchone()
    assert int(rows["m"]) >= 2
    assert r2.contents_updated >= 1 or r2.resources_updated >= 1
