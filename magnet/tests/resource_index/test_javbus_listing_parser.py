"""JavBus listing parser tests."""

import pytest

from magnet.resource_index.acquisition.fixture_reader import load_manifest, read_document
from magnet.resource_index.adapters.javbus.listing_parser import parse_listing
from magnet.resource_index.errors import (
    AGE_GATE_PAGE,
    LISTING_DOM_DRIFT,
    LISTING_EMPTY,
    ParseError,
)


def _env(manifest_path, name: str):
    m = load_manifest(manifest_path)
    doc = next(d for d in m.documents if d.name == name)
    return read_document(m, doc)


def test_listing_multi_and_dedupe(manifest_path):
    env = _env(manifest_path, "listing_page_1")
    cands = parse_listing(env)
    assert len(cands) == 4
    codes = [c.content_code for c in cands]
    assert codes == ["TST-001", "TST-002", "TST-003", "TST-004"]
    assert all(c.detail_url.startswith("https://") for c in cands)
    assert cands[0].list_position == 1


def test_listing_empty(manifest_path):
    env = _env(manifest_path, "listing_empty")
    with pytest.raises(ParseError) as ei:
        parse_listing(env)
    assert ei.value.error_code == LISTING_EMPTY


def test_age_gate(manifest_path):
    env = _env(manifest_path, "age_gate")
    with pytest.raises(ParseError) as ei:
        parse_listing(env)
    assert ei.value.error_code == AGE_GATE_PAGE


def test_dom_drift(manifest_path):
    env = _env(manifest_path, "listing_dom_drift")
    with pytest.raises(ParseError) as ei:
        parse_listing(env)
    assert ei.value.error_code in {LISTING_EMPTY, LISTING_DOM_DRIFT}
