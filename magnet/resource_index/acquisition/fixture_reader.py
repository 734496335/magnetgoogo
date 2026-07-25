"""Read and validate sanitized fixture manifests."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from magnet.resource_index.acquisition.models import FixtureDocumentRef, FixtureManifest
from magnet.resource_index.domain.enums import DocumentType
from magnet.resource_index.domain.identity import document_id_for
from magnet.resource_index.domain.models import RawDocumentEnvelope
from magnet.resource_index.errors import (
    FIXTURE_HASH_MISMATCH,
    FIXTURE_MANIFEST_INVALID,
    FixtureError,
)


def _parse_dt(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def load_manifest(manifest_path: str | Path) -> FixtureManifest:
    path = Path(manifest_path)
    if not path.is_file():
        raise FixtureError(
            FIXTURE_MANIFEST_INVALID,
            "manifest file not found",
            {"path": path.name},
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureError(
            FIXTURE_MANIFEST_INVALID,
            f"invalid JSON: {exc}",
            {"path": path.name},
        ) from exc

    required = ("fixture_schema", "source_id", "captured_at", "sanitized", "documents")
    for key in required:
        if key not in data:
            raise FixtureError(
                FIXTURE_MANIFEST_INVALID,
                f"missing field {key}",
                {"path": path.name},
            )
    if not data["sanitized"]:
        raise FixtureError(
            FIXTURE_MANIFEST_INVALID,
            "manifest must declare sanitized=true for committed fixtures",
            {},
        )
    docs: list[FixtureDocumentRef] = []
    for raw in data["documents"]:
        if "name" not in raw or "type" not in raw or "path" not in raw or "sha256" not in raw:
            raise FixtureError(
                FIXTURE_MANIFEST_INVALID,
                "document entry missing required fields",
                {"name": raw.get("name")},
            )
        docs.append(
            FixtureDocumentRef(
                name=raw["name"],
                document_type=raw["type"],
                path=raw["path"],
                sha256=raw["sha256"].lower(),
                expected=raw.get("expected"),
                source_url=raw.get("source_url")
                or f"https://fixtures.invalid/{raw['type']}/{raw['name']}",
                content_code=raw.get("content_code"),
                links_to=tuple(raw.get("links_to") or ()),
            )
        )
    return FixtureManifest(
        fixture_schema=str(data["fixture_schema"]),
        source_id=str(data["source_id"]),
        captured_at=_parse_dt(str(data["captured_at"])),
        sanitized=bool(data["sanitized"]),
        documents=tuple(docs),
        root_dir=str(path.parent.resolve()),
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_document(
    manifest: FixtureManifest,
    doc: FixtureDocumentRef,
) -> RawDocumentEnvelope:
    root = Path(manifest.root_dir)
    file_path = (root / doc.path).resolve()
    if not str(file_path).startswith(str(root.resolve())):
        raise FixtureError(
            FIXTURE_MANIFEST_INVALID,
            "fixture path escapes root",
            {"path": doc.path},
        )
    if not file_path.is_file():
        raise FixtureError(
            FIXTURE_MANIFEST_INVALID,
            "fixture body missing",
            {"path": doc.path},
        )
    digest = sha256_file(file_path)
    if digest != doc.sha256.lower():
        raise FixtureError(
            FIXTURE_HASH_MISMATCH,
            "fixture body hash mismatch",
            {"name": doc.name, "expected": doc.sha256, "actual": digest},
        )
    body = file_path.read_text(encoding="utf-8")
    try:
        doc_type = DocumentType(doc.document_type)
    except ValueError as exc:
        raise FixtureError(
            FIXTURE_MANIFEST_INVALID,
            f"unknown document type: {doc.document_type}",
            {"name": doc.name},
        ) from exc

    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return RawDocumentEnvelope(
        document_id=document_id_for(manifest.source_id, doc.source_url, body_hash),
        source_id=manifest.source_id,
        document_type=doc_type,
        source_url=doc.source_url,
        captured_at=manifest.captured_at,
        status_code=200,
        content_type="text/html; charset=utf-8",
        encoding="utf-8",
        sha256=body_hash,
        body=body,
        fixture_name=doc.name,
        sanitized=True,
    )


def iter_envelopes(manifest: FixtureManifest) -> list[tuple[FixtureDocumentRef, RawDocumentEnvelope]]:
    return [(doc, read_document(manifest, doc)) for doc in manifest.documents]
