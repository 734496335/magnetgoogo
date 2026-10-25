from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "deploy/source-sync/linux/verify-source-packs.py"
PRODUCTION_PAYLOAD_SHA = "3f154d667b8b167e419e9a3ec45b0154fbecfc3449f128bef3ae5ecd7a8f25f7"
KEY = bytes.fromhex("37" * 32)


@pytest.fixture
def verifier():
    spec = importlib.util.spec_from_file_location("source64_verifier", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def envelope(now):
    return {
        "schema_version": 1,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=72)).isoformat(),
        "min_app_version": "0.2.5",
        "payload": {"rulesets": [{"rules": [
            {"id": "source-%d" % i, "health": {"status": "green" if i < 48 else "yellow"}}
            for i in range(64)
        ]}]},
    }


def write_pack(path, value):
    raw = gzip.compress(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    padder = padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    iv = os.urandom(16)
    encryptor = Cipher(algorithms.AES(KEY), modes.CBC(iv)).encryptor()
    ct = base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode("ascii")
    wrapper = {"iv": iv.hex(), "ct": ct, "sig": hmac.new(KEY, ct.encode(), hashlib.sha256).hexdigest(), "gz": True}
    path.write_text(json.dumps(wrapper), encoding="utf-8")


def approve_fixture(verifier, value):
    digest = verifier.canonical_payload_hash(value["payload"])
    verifier.REVIEWED_SOURCE_PROFILES = {
        digest: {"name": "test-original64", "rules": 64, "green": 48, "min_app_version": "0.2.5"}
    }


def test_production_profile_is_exact_and_explicit(verifier):
    assert verifier.REVIEWED_SOURCE_PROFILES == {
        PRODUCTION_PAYLOAD_SHA: {"name": "original64-20261025", "rules": 64, "green": 48, "min_app_version": "0.2.5"}
    }


def test_reviewed64_accepts_fresh_and_renewed_envelopes(verifier, tmp_path):
    now = datetime.now(timezone.utc)
    value = envelope(now)
    approve_fixture(verifier, value)
    path = tmp_path / "sources.enc.json"
    write_pack(path, value)
    first = verifier.validate(path, KEY, now, 12)
    later = now + timedelta(hours=41)
    value["issued_at"] = later.isoformat()
    value["expires_at"] = (later + timedelta(hours=72)).isoformat()
    write_pack(path, value)
    renewed = verifier.validate(path, KEY, later, 12)
    assert first["source_profile"] == renewed["source_profile"] == "test-original64"
    assert first["payload_sha256"] == renewed["payload_sha256"]
    assert first["sha256"] != renewed["sha256"]


@pytest.mark.parametrize("change", ["unreviewed", "content", "identity", "count", "health"])
def test_unknown_or_changed_small_payload_stays_rejected(verifier, tmp_path, change):
    now = datetime.now(timezone.utc)
    value = envelope(now)
    if change != "unreviewed":
        approve_fixture(verifier, value)
    rules = value["payload"]["rulesets"][0]["rules"]
    if change == "content":
        rules[0]["unexpected"] = "changed"
    elif change == "identity":
        rules[0]["id"] = "different"
    elif change == "count":
        rules.pop()
    elif change == "health":
        rules[0]["health"]["status"] = "yellow"
    path = tmp_path / "sources.enc.json"
    write_pack(path, value)
    with pytest.raises(ValueError, match="source counts are implausible"):
        verifier.validate(path, KEY, now, 12)


def test_reviewed_payload_rejects_global_minimum_change(verifier, tmp_path):
    now = datetime.now(timezone.utc)
    value = envelope(now)
    approve_fixture(verifier, value)
    value["min_app_version"] = "0.2.10"
    path = tmp_path / "sources.enc.json"
    write_pack(path, value)
    with pytest.raises(ValueError, match="reviewed source profile contract mismatch"):
        verifier.validate(path, KEY, now, 12)


@pytest.mark.parametrize("failure", ["signature", "near-expiry", "future-issue", "lifetime"])
def test_reviewed_profile_preserves_crypto_and_freshness_gates(verifier, tmp_path, failure):
    now = datetime.now(timezone.utc)
    value = envelope(now)
    approve_fixture(verifier, value)
    expected = "HMAC verification failed"
    if failure == "near-expiry":
        value["issued_at"] = (now - timedelta(hours=66)).isoformat()
        value["expires_at"] = (now + timedelta(hours=6)).isoformat()
        expected = "validity hours remain"
    elif failure == "future-issue":
        value["issued_at"] = (now + timedelta(hours=2)).isoformat()
        value["expires_at"] = (now + timedelta(hours=74)).isoformat()
        expected = "implausibly in the future"
    elif failure == "lifetime":
        value["expires_at"] = (now + timedelta(hours=120)).isoformat()
        expected = "lifetime is outside"
    path = tmp_path / "sources.enc.json"
    write_pack(path, value)
    if failure == "signature":
        wrapper = json.loads(path.read_text("utf-8"))
        wrapper["sig"] = "0" * 64
        path.write_text(json.dumps(wrapper), encoding="utf-8")
    with pytest.raises(ValueError, match=expected):
        verifier.validate(path, KEY, now, 12)
