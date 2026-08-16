"""Tests for CookieStore — pure filesystem, no mocking."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from magnet.crawler_v3.cookie_store import CookieStore


def _make_cookie(name: str, value: str, *, expires: float | None = None, domain: str = ".example.com") -> dict:
    c = {"name": name, "value": value, "domain": domain, "path": "/"}
    if expires is not None:
        c["expires"] = expires
    return c


class TestCookieStore:
    def test_put_get_roundtrip(self, tmp_path: Path):
        store = CookieStore(root=tmp_path)
        cookies = [_make_cookie("cf_clearance", "abc123")]
        store.put("https://example.com", cookies)
        got = store.get("https://example.com")
        assert len(got) == 1
        assert got[0]["name"] == "cf_clearance"
        assert got[0]["value"] == "abc123"

    def test_origin_isolation(self, tmp_path: Path):
        store = CookieStore(root=tmp_path)
        store.put("https://a.com", [_make_cookie("k", "v_a")])
        store.put("https://b.com", [_make_cookie("k", "v_b")])
        assert store.get("https://a.com")[0]["value"] == "v_a"
        assert store.get("https://b.com")[0]["value"] == "v_b"
        assert store.get("https://c.com") == []

    def test_expired_cookie_pruned(self, tmp_path: Path):
        store = CookieStore(root=tmp_path)
        past = time.time() - 3600  # 1 hour ago
        store.put("https://example.com", [_make_cookie("old", "expired", expires=past)])
        assert store.get("https://example.com") == []

    def test_session_cookie_minus_one_is_retained(self, tmp_path: Path):
        store = CookieStore(root=tmp_path)
        store.put("https://example.com", [_make_cookie("session", "alive", expires=-1)])
        assert store.get("https://example.com")[0]["value"] == "alive"

    def test_wrong_json_shapes_fail_closed(self, tmp_path: Path):
        store = CookieStore(root=tmp_path)
        path = store.path_for("https://example.com")
        path.write_text("[]", encoding="utf-8")
        assert store.get("https://example.com") == []
        path.write_text(json.dumps({"cookies": "not-a-list"}), encoding="utf-8")
        assert store.get("https://example.com") == []
        path.write_text(json.dumps({"cookies": [{"name": "x", "value": "y", "expires": "bad"}]}), encoding="utf-8")
        assert store.get("https://example.com") == []

    def test_atomic_write_leaves_no_temporary_files(self, tmp_path: Path):
        store = CookieStore(root=tmp_path)
        store.put("https://example.com", [_make_cookie("k", "v")])
        assert store.get("https://example.com")[0]["value"] == "v"
        assert list(tmp_path.glob("*.tmp")) == []
        assert list(tmp_path.glob(".*.tmp")) == []

    def test_delete_removes_file(self, tmp_path: Path):
        store = CookieStore(root=tmp_path)
        store.put("https://example.com", [_make_cookie("k", "v")])
        assert store.path_for("https://example.com").exists()
        store.delete("https://example.com")
        assert not store.path_for("https://example.com").exists()
        assert store.get("https://example.com") == []

    def test_to_header_format(self, tmp_path: Path):
        store = CookieStore(root=tmp_path)
        store.put("https://example.com", [
            _make_cookie("cf_clearance", "abc"),
            _make_cookie("session", "xyz"),
        ])
        header = store.to_header("https://example.com")
        assert "cf_clearance=abc" in header
        assert "session=xyz" in header
        assert "; " in header

    def test_cross_process_persistence(self, tmp_path: Path):
        """Write with one store instance, read with another (same root)."""
        store1 = CookieStore(root=tmp_path)
        store1.put("https://example.com", [_make_cookie("cf_clearance", "persist_me")])

        # New instance simulates a fresh process
        store2 = CookieStore(root=tmp_path)
        got = store2.get("https://example.com")
        assert len(got) == 1
        assert got[0]["value"] == "persist_me"
