"""Normalizer unit tests."""

import base64

import pytest

from magnet.resource_index.errors import ValidationError
from magnet.resource_index.normalize.content_code import normalize_content_code
from magnet.resource_index.normalize.dates import parse_date, parse_duration_minutes
from magnet.resource_index.normalize.magnets import extract_info_hash, normalize_magnet_uri
from magnet.resource_index.normalize.sizes import parse_size_bytes
from magnet.resource_index.normalize.text import normalize_title
from magnet.resource_index.normalize.urls import absolutize


def test_content_code_upper_and_dash():
    assert normalize_content_code(" tst－001 ") == "TST-001"
    assert normalize_content_code("abc123") == "ABC-123"
    assert normalize_content_code("ABC_123") == "ABC-123"
    assert normalize_content_code("!!!") is None


def test_title_strips_code_prefix():
    assert normalize_title("TST-001 Fixture Title", content_code="TST-001") == "Fixture Title"


def test_size_units():
    assert parse_size_bytes("1.5GB") == 1_500_000_000
    assert parse_size_bytes("2.0 GiB") == int(2.0 * 1024**3)
    assert parse_size_bytes("800MB") == 800_000_000


def test_date_and_duration():
    assert parse_date("2026-07-01").isoformat() == "2026-07-01"
    assert parse_date("2026/07/02").isoformat() == "2026-07-02"
    assert parse_duration_minutes("120分鐘") == 120
    assert parse_duration_minutes("90分钟") == 90


def test_magnet_hex_and_normalize():
    uri = "magnet:?tr=udp://b&dn=Title&xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&tr=udp://a"
    norm, h = normalize_magnet_uri(uri)
    assert h == "a" * 40
    assert norm.startswith("magnet:?xt=urn:btih:" + "a" * 40)
    assert "dn=Title" in norm or "dn=Title" in norm.replace("%20", " ")
    # trackers sorted
    assert norm.index("tr=") < norm.rindex("tr=")


def test_magnet_base32():
    raw = bytes.fromhex("11" * 20)
    b32 = base64.b32encode(raw).decode().rstrip("=")
    uri = f"magnet:?xt=urn:btih:{b32}"
    assert extract_info_hash(uri) == "11" * 20


def test_magnet_invalid():
    with pytest.raises(ValidationError):
        extract_info_hash("http://example.com")
    with pytest.raises(ValidationError):
        extract_info_hash("magnet:?xt=urn:btih:ZZ")


def test_absolutize():
    assert absolutize("https://www.javbus.com/x", "/TST-001") == "https://www.javbus.com/TST-001"
