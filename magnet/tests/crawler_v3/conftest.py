"""Shared fixtures for crawler_v3 tests."""
from __future__ import annotations

import json
import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: hit real sites (not run in CI)")


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SOURCES_FILE = os.path.join(ROOT, "sources.json")


@pytest.fixture
def sources_data():
    """Load and flatten sources.json."""
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for rs in data.get("rulesets") or []:
        out.extend(rs.get("rules") or [])
    return out


@pytest.fixture
def fake_source():
    """Minimal fake source dict for unit tests."""
    return {
        "site": {
            "name": "test-source",
            "origin": "https://example.com",
        },
        "search": {
            "request_template": "/search?keyword={query}",
        },
        "health": {"status": "green"},
    }


@pytest.fixture
def thatcdn_source():
    """A thatcdn source with tier_override (like xiongmaogb.top)."""
    return {
        "site": {
            "name": "test-thatcdn",
            "origin": "https://xiongmaogb.top",
        },
        "tier_override": {"tier": "tier2_handler", "platform": "thatcdn"},
        "health": {"status": "yellow"},
    }
