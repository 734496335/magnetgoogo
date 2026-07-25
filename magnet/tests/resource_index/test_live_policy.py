"""Live acquisition policy tests (no network)."""

import pytest

from magnet.resource_index.acquisition.live_fetcher import LiveFetcher
from magnet.resource_index.acquisition.policy import LiveFetchPolicy, should_stop_on_status
from magnet.resource_index.errors import (
    LIVE_FETCH_DISABLED,
    LIVE_POLICY_NOT_ACKNOWLEDGED,
    LIVE_RATE_LIMITED,
    LivePolicyError,
)


def test_default_disabled():
    p = LiveFetchPolicy.from_flags(env_enabled=False, acknowledged=True, max_pages=1)
    with pytest.raises(LivePolicyError) as ei:
        p.assert_allowed()
    assert ei.value.error_code == LIVE_FETCH_DISABLED


def test_missing_ack():
    p = LiveFetchPolicy.from_flags(env_enabled=True, acknowledged=False, max_pages=1)
    with pytest.raises(LivePolicyError) as ei:
        p.assert_allowed()
    assert ei.value.error_code == LIVE_POLICY_NOT_ACKNOWLEDGED


def test_delay_floor():
    p = LiveFetchPolicy.from_flags(
        env_enabled=True,
        acknowledged=True,
        max_pages=1,
        request_delay_seconds=1,
    )
    with pytest.raises(LivePolicyError) as ei:
        p.assert_allowed()
    assert ei.value.error_code == LIVE_RATE_LIMITED


def test_page_cap():
    p = LiveFetchPolicy.from_flags(
        env_enabled=True,
        acknowledged=True,
        max_pages=99,
        request_delay_seconds=10,
    )
    with pytest.raises(LivePolicyError) as ei:
        p.assert_allowed()
    assert ei.value.error_code == LIVE_RATE_LIMITED


def test_stop_on_status():
    assert should_stop_on_status(403) is not None
    assert should_stop_on_status(429) is not None
    assert should_stop_on_status(200, "cf-challenge turnstile") is not None


def test_fetcher_no_network_even_when_allowed():
    p = LiveFetchPolicy.from_flags(
        env_enabled=True,
        acknowledged=True,
        max_pages=1,
        request_delay_seconds=10,
    )
    f = LiveFetcher(p)
    with pytest.raises(LivePolicyError):
        f.fetch("https://example.invalid")
    # cookies never persisted to disk — only memory
    assert f.cookies_snapshot() == {}
