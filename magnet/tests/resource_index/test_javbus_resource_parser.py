"""JavBus resource table parser tests."""

import base64

from magnet.resource_index.acquisition.fixture_reader import load_manifest, read_document
from magnet.resource_index.adapters.javbus.resource_parser import parse_resource_table


def _env(manifest_path, name: str):
    m = load_manifest(manifest_path)
    doc = next(d for d in m.documents if d.name == name)
    return read_document(m, doc)


def test_multiple_and_dedupe_hash(manifest_path):
    env = _env(manifest_path, "resource_tst_001")
    releases, warnings = parse_resource_table(env, content_id="adult_video:TST-001")
    hashes = [r.info_hash for r in releases]
    assert len(hashes) == 2
    assert len(set(hashes)) == 2
    assert any(r.has_hd for r in releases)
    assert any(r.has_subtitle for r in releases)


def test_base32_hash(manifest_path):
    env = _env(manifest_path, "resource_tst_003")
    releases, _ = parse_resource_table(env, content_id="adult_video:TST-003")
    expected = "11" * 20
    assert any(r.info_hash == expected for r in releases)


def test_empty_table_warning(manifest_path):
    env = _env(manifest_path, "resource_empty")
    releases, warnings = parse_resource_table(env, content_id="adult_video:TST-006")
    assert releases == []
    assert any(w.error_code == "RESOURCE_TABLE_EMPTY" for w in warnings)


def test_invalid_magnet_skipped(manifest_path):
    env = _env(manifest_path, "resource_invalid_magnet")
    releases, warnings = parse_resource_table(env, content_id="adult_video:X")
    assert releases == []
    assert any(
        w.error_code in {"MAGNET_INVALID", "INFO_HASH_INVALID"} for w in warnings
    )
