"""Canonical JSON, SHA-256 and Ed25519 helpers for media release documents."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from magnet.resource_index.errors import CONFIG_ERROR, VALIDATION_ERROR, ResourceIndexError


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes with no insignificant whitespace."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signature_payload(document: Mapping[str, Any]) -> bytes:
    unsigned = dict(document)
    unsigned.pop("signature", None)
    return canonical_json_bytes(unsigned)


def _load_private_key(path: str | Path) -> Ed25519PrivateKey:
    key_path = Path(path)
    if not key_path.is_file():
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media signing private key does not exist",
            {"path": str(key_path)},
        )
    try:
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    except (ValueError, TypeError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media signing private key is not a valid unencrypted PEM key",
            {"path": str(key_path), "error": str(exc)},
        ) from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media signing private key must be Ed25519",
            {"path": str(key_path)},
        )
    return key


def _load_public_key(path: str | Path) -> Ed25519PublicKey:
    key_path = Path(path)
    if not key_path.is_file():
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media signing public key does not exist",
            {"path": str(key_path)},
        )
    try:
        key = serialization.load_pem_public_key(key_path.read_bytes())
    except (ValueError, TypeError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media signing public key is not a valid PEM key",
            {"path": str(key_path), "error": str(exc)},
        ) from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media signing public key must be Ed25519",
            {"path": str(key_path)},
        )
    return key


def _public_key_pem(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _atomic_write(path: Path, payload: bytes, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if private:
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def public_key_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"media-ed25519-{sha256_bytes(raw)[:12]}"


def generate_ed25519_keypair(
    private_key_path: str | Path,
    public_key_path: str | Path,
    *,
    force: bool = False,
) -> dict[str, str]:
    """Create a local Ed25519 keypair without ever logging private key material."""

    private_path = Path(private_key_path)
    public_path = Path(public_key_path)
    if private_path.resolve() == public_path.resolve():
        raise ResourceIndexError(
            CONFIG_ERROR,
            "private and public media signing keys must use different paths",
            {"path": str(private_path)},
        )

    private_exists = private_path.is_file()
    public_exists = public_path.is_file()
    if not force and private_exists and not public_exists:
        private_key = _load_private_key(private_path)
        public_key = private_key.public_key()
        _atomic_write(public_path, _public_key_pem(public_key))
        return {
            "private_key_path": str(private_path),
            "public_key_path": str(public_path),
            "signature_key_id": public_key_id(public_key),
            "key_state": "public_key_recovered",
        }
    if not force and public_exists and not private_exists:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "media signing keypair is incomplete and the private key cannot be recovered",
            {"public_key_path": str(public_path)},
        )
    if private_exists and public_exists and not force:
        private_key = _load_private_key(private_path)
        public_key = _load_public_key(public_path)
        derived_public = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        stored_public = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        if derived_public != stored_public:
            repaired_public = private_key.public_key()
            _atomic_write(public_path, _public_key_pem(repaired_public))
            return {
                "private_key_path": str(private_path),
                "public_key_path": str(public_path),
                "signature_key_id": public_key_id(repaired_public),
                "key_state": "public_key_repaired",
            }
        return {
            "private_key_path": str(private_path),
            "public_key_path": str(public_path),
            "signature_key_id": public_key_id(public_key),
            "key_state": "existing",
        }

    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_payload = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _atomic_write(private_path, private_payload, private=True)
    _atomic_write(public_path, _public_key_pem(public_key))

    return {
        "private_key_path": str(private_path),
        "public_key_path": str(public_path),
        "signature_key_id": public_key_id(public_key),
        "key_state": "rotated" if force and (private_exists or public_exists) else "created",
    }


def sign_document(document: Mapping[str, Any], private_key_path: str | Path) -> dict[str, Any]:
    private_key = _load_private_key(private_key_path)
    signed = dict(document)
    signed["signature_key_id"] = public_key_id(private_key.public_key())
    signed.pop("signature", None)
    signature = private_key.sign(_signature_payload(signed))
    signed["signature"] = base64.b64encode(signature).decode("ascii")
    return signed


def verify_document(document: Mapping[str, Any], public_key_path: str | Path) -> None:
    public_key = _load_public_key(public_key_path)
    expected_key_id = public_key_id(public_key)
    actual_key_id = document.get("signature_key_id")
    signature_text = document.get("signature")
    if actual_key_id != expected_key_id:
        raise ResourceIndexError(
            VALIDATION_ERROR,
            "media document signature_key_id does not match the supplied public key",
            {"expected": expected_key_id, "actual": actual_key_id},
        )
    if not isinstance(signature_text, str) or not signature_text:
        raise ResourceIndexError(
            VALIDATION_ERROR,
            "media document signature is missing",
            {},
        )
    try:
        signature = base64.b64decode(signature_text, validate=True)
        public_key.verify(signature, _signature_payload(document))
    except (ValueError, InvalidSignature) as exc:
        raise ResourceIndexError(
            VALIDATION_ERROR,
            "media document Ed25519 signature verification failed",
            {},
        ) from exc
