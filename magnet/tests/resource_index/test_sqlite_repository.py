"""SQLite repository tests."""

from datetime import date, datetime, timezone

import pytest

from magnet.resource_index.domain.enums import ContentType, MediaStatus, MediaType, PersonRole
from magnet.resource_index.domain.identity import content_id_for, media_id_for, person_id_for, resource_id_for
from magnet.resource_index.domain.models import (
    ContentItem,
    MediaAssetRef,
    ParseProvenance,
    ParsedContentBundle,
    PersonRef,
    ResourceRelease,
    TagRef,
)
from magnet.resource_index.errors import ConflictError
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository


NOW = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)


def _bundle(
    code: str = "TST-001",
    title: str = "Title A",
    maker: str | None = "Maker",
    resources: list[ResourceRelease] | None = None,
    info_hash: str = "a" * 40,
) -> ParsedContentBundle:
    cid = content_id_for(ContentType.ADULT_VIDEO, code)
    content = ContentItem(
        content_id=cid,
        content_type=ContentType.ADULT_VIDEO,
        content_code=code,
        raw_content_code=code,
        title=title,
        original_title=None,
        release_date=date(2026, 7, 1),
        duration_minutes=120,
        maker_name=maker,
        publisher_name=None,
        label_name=None,
        series_name="Series",
        cover_source_url="https://fixtures.invalid/c.jpg",
        detail_url=f"https://www.javbus.com/{code}",
        adult=True,
        source_id="javbus",
        source_item_key=f"/{code}",
        parser_version="javbus-parser/1.0.0",
    )
    person = PersonRef(
        person_id=person_id_for(slug="p1", display_name="Person", source_prefix="javbus"),
        display_name="Person",
        role=PersonRole.ACTOR,
        source_profile_url=None,
        source_external_key="p1",
        sort_order=0,
    )
    tag = TagRef(tag_id="javbus:tag:t1", display_name="Tag", source_url=None, source_external_key="t1")
    media = MediaAssetRef(
        media_id=media_id_for(cid, MediaType.COVER, "https://fixtures.invalid/c.jpg"),
        media_type=MediaType.COVER,
        source_url="https://fixtures.invalid/c.jpg",
        stored_url=None,
        content_hash=None,
        width=None,
        height=None,
        adult=True,
        status=MediaStatus.REMOTE_REFERENCE_ONLY,
    )
    if resources is None:
        resources = [
            ResourceRelease(
                resource_id=resource_id_for(info_hash),
                content_id=cid,
                info_hash=info_hash,
                magnet_uri=f"magnet:?xt=urn:btih:{info_hash}",
                display_title=title,
                size_bytes=1000,
                size_display="1KB",
                published_at=date(2026, 7, 2),
                has_subtitle=False,
                has_hd=True,
                quality_tags=("hd",),
            )
        ]
    return ParsedContentBundle(
        content=content,
        aliases=(),
        people=(person,),
        tags=(tag,),
        media=(media,),
        resources=tuple(resources),
        warnings=(),
        provenance=ParseProvenance(
            source_id="javbus",
            source_item_key=f"/{code}",
            detail_url=content.detail_url,
            parser_version="javbus-parser/1.0.0",
            document_sha256="abc",
        ),
    )


def test_migration_idempotent(tmp_path):
    db = tmp_path / "m.db"
    r = SqliteResourceRepository(db)
    v1 = r.init_schema()
    v2 = r.init_schema()
    assert v1 == v2 == "0006"
    r.close()


def test_upsert_and_no_null_overwrite(repo: SqliteResourceRepository):
    repo.upsert_bundle(_bundle(title="Title A", maker="Maker"), now=NOW)
    repo.upsert_bundle(_bundle(title="Title B", maker=None), now=NOW)
    row = repo.get_content_by_code("TST-001")
    assert row["title"] == "Title B"
    assert row["maker_name"] == "Maker"  # not overwritten by None
    # previous title alias
    aliases = repo.conn.execute(
        "SELECT alias FROM content_aliases WHERE content_id = ?",
        (row["content_id"],),
    ).fetchall()
    assert any(a["alias"] == "Title A" for a in aliases)


def test_info_hash_unique_conflict(repo: SqliteResourceRepository):
    repo.upsert_bundle(_bundle(code="TST-001", info_hash="a" * 40), now=NOW)
    with pytest.raises(ConflictError):
        repo.upsert_bundle(_bundle(code="TST-002", info_hash="a" * 40), now=NOW)


def test_transaction_rollback_on_conflict(repo: SqliteResourceRepository):
    repo.upsert_bundle(_bundle(code="TST-001", info_hash="a" * 40), now=NOW)
    before = repo.counts().contents
    try:
        repo.upsert_bundle(_bundle(code="TST-009", info_hash="a" * 40), now=NOW)
    except ConflictError:
        pass
    assert repo.counts().contents == before
