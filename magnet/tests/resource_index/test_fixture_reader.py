"""Fixture reader contract tests."""

import hashlib

import pytest

from magnet.resource_index.acquisition.fixture_reader import load_manifest, read_document
from magnet.resource_index.errors import FIXTURE_HASH_MISMATCH, FixtureError


def test_load_manifest(manifest_path):
    m = load_manifest(manifest_path)
    assert m.source_id == "javbus"
    assert m.sanitized is True
    assert len(m.documents) >= 10


def test_hash_mismatch(manifest_path, tmp_path):
    m = load_manifest(manifest_path)
    doc = m.documents[0]
    # copy with wrong expected hash
    from magnet.resource_index.acquisition.models import FixtureDocumentRef, FixtureManifest

    bad = FixtureDocumentRef(
        name=doc.name,
        document_type=doc.document_type,
        path=doc.path,
        sha256="0" * 64,
        expected=None,
        source_url=doc.source_url,
    )
    bad_manifest = FixtureManifest(
        fixture_schema=m.fixture_schema,
        source_id=m.source_id,
        captured_at=m.captured_at,
        sanitized=True,
        documents=(bad,),
        root_dir=m.root_dir,
    )
    with pytest.raises(FixtureError) as ei:
        read_document(bad_manifest, bad)
    assert ei.value.error_code == FIXTURE_HASH_MISMATCH


def test_read_document_ok(manifest_path):
    m = load_manifest(manifest_path)
    doc = next(d for d in m.documents if d.name == "listing_page_1")
    env = read_document(m, doc)
    assert env.sanitized is True
    assert "movie-box" in env.body
    assert env.sha256 == hashlib.sha256(env.body.encode("utf-8")).hexdigest()
