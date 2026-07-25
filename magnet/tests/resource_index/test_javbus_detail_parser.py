"""JavBus detail parser tests."""

import pytest

from magnet.resource_index.acquisition.fixture_reader import load_manifest, read_document
from magnet.resource_index.adapters.javbus.detail_parser import derive_resource_request, parse_detail
from magnet.resource_index.errors import TITLE_MISSING, ParseError


def _env(manifest_path, name: str):
    m = load_manifest(manifest_path)
    doc = next(d for d in m.documents if d.name == name)
    return read_document(m, doc)


def test_full_detail(manifest_path):
    env = _env(manifest_path, "detail_tst_001")
    bundle = parse_detail(env)
    c = bundle.content
    assert c.content_code == "TST-001"
    assert c.adult is True
    assert c.content_id == "adult_video:TST-001"
    assert "Fixture Title" in c.title
    assert c.maker_name == "Fixture Maker"
    assert c.series_name == "Fixture Series"
    assert c.duration_minutes == 120
    assert c.release_date is not None
    assert any(p.role.value == "actor" for p in bundle.people)
    assert len(bundle.tags) >= 2
    assert bundle.media
    assert all(m.stored_url is None for m in bundle.media)
    assert bundle.provenance.internal.get("gid") == "100001"


def test_no_series(manifest_path):
    env = _env(manifest_path, "detail_tst_002")
    bundle = parse_detail(env)
    assert bundle.content.series_name is None


def test_no_maker_multi_actor(manifest_path):
    env = _env(manifest_path, "detail_tst_003")
    bundle = parse_detail(env)
    assert bundle.content.maker_name is None
    actors = [p for p in bundle.people if p.role.value == "actor"]
    assert len(actors) >= 2


def test_missing_title_hard_fail(manifest_path):
    env = _env(manifest_path, "detail_missing_title")
    with pytest.raises(ParseError) as ei:
        parse_detail(env)
    assert ei.value.error_code in {TITLE_MISSING, "DETAIL_DOM_DRIFT"}


def test_derive_resource_request(manifest_path):
    env = _env(manifest_path, "detail_tst_001")
    desc = derive_resource_request(env)
    assert desc is not None
    assert desc.query["gid"] == "100001"
