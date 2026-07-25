"""Ingest pipeline tests."""

from datetime import datetime, timezone

from magnet.resource_index.pipeline.ingest import ingest_fixture


FIXED = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_ingest_creates_contents_and_resources(repo, manifest_path):
    result = ingest_fixture(
        manifest_path=manifest_path,
        repo=repo,
        clock=lambda: FIXED,
    )
    assert result.status in {"success", "partial"}
    assert result.contents_created >= 6
    counts = repo.counts()
    assert counts.contents >= 6
    assert counts.resources >= 4
    # at least one without resources
    assert counts.contents_without_resources >= 1
    row = repo.get_content_by_code("TST-001")
    assert row is not None
    assert row["adult"] == 1
    resources = repo.list_resources_for_content("TST-001")
    assert len(resources) >= 2
