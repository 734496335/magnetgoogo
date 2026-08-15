"""Tests for CookieStore integration in Tier 0 and Tier 1."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from magnet.crawler_v3.tiers.tier0_http import Tier0Http
from magnet.crawler_v3.tiers.base import SearchResult, TierError


@pytest.fixture
def tier0():
    return Tier0Http(timeout=5)


@pytest.fixture
def simple_source():
    return {
        "site": {"name": "test", "origin": "https://example.com"},
        "search": {"request_template": "/search?keyword={query}"},
    }


class TestTier0CookieInjection:
    @patch("magnet.crawler_v3.tiers.tier0_http._COOKIE_STORE")
    @patch.object(Tier0Http, "_fetch")
    def test_injects_cookie_header_when_present(self, mock_fetch, mock_store, tier0, simple_source):
        mock_store.to_header.return_value = "cf_clearance=abc123"
        mock_fetch.return_value = "<html>" * 200 + "result</html>"

        with patch("magnet.crawler_v3.tiers.tier0_http._looks_like_anti_bot", return_value=False):
            with patch("magnet.crawler_v3.tiers.tier0_http.extract_results_from_html", return_value=[SearchResult(title="t", magnet="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567")]):
                tier0.search(simple_source, "test")

        # Verify _fetch was called with Cookie header
        call_kwargs = mock_fetch.call_args
        headers = call_kwargs[1]["headers"] if "headers" in call_kwargs[1] else call_kwargs[0][1]
        assert "Cookie" in headers
        assert headers["Cookie"] == "cf_clearance=abc123"

    @patch("magnet.crawler_v3.tiers.tier0_http._COOKIE_STORE")
    @patch.object(Tier0Http, "_fetch")
    def test_no_cookie_header_when_empty(self, mock_fetch, mock_store, tier0, simple_source):
        mock_store.to_header.return_value = ""
        mock_fetch.return_value = "<html>" * 200 + "result</html>"

        with patch("magnet.crawler_v3.tiers.tier0_http._looks_like_anti_bot", return_value=False):
            with patch("magnet.crawler_v3.tiers.tier0_http.extract_results_from_html", return_value=[SearchResult(title="t", magnet="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567")]):
                tier0.search(simple_source, "test")

        call_kwargs = mock_fetch.call_args
        headers = call_kwargs[1]["headers"] if "headers" in call_kwargs[1] else call_kwargs[0][1]
        assert "Cookie" not in headers


class TestTier1CookieHarvest:
    def test_harvests_cookies_on_success(self):
        """Verify Tier 1 puts cookies when search succeeds."""
        mock_store = MagicMock()
        mock_cookies = [{"name": "cf_clearance", "value": "xyz", "domain": ".example.com"}]

        with patch("magnet.crawler_v3.tiers.tier1_cloak._COOKIE_STORE", mock_store):
            with patch("magnet.crawler_v3.tiers.tier1_cloak._HAS_CLOAK", True):
                with patch("magnet.crawler_v3.tiers.tier1_cloak.cloak_launch") as mock_launch:
                    mock_page = MagicMock()
                    mock_page.content.return_value = "<html>" * 200 + "result</html>"
                    mock_page.title.return_value = "Search Results"
                    mock_page.context.cookies.return_value = mock_cookies

                    mock_browser = MagicMock()
                    mock_browser.new_page.return_value = mock_page
                    mock_launch.return_value = mock_browser

                    with patch("magnet.crawler_v3.tiers.tier1_cloak.extract_results_from_html", return_value=[SearchResult(title="t", magnet="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567")]):
                        from magnet.crawler_v3.tiers.tier1_cloak import Tier1Cloak
                        tier1 = Tier1Cloak.__new__(Tier1Cloak)
                        tier1.headless = True
                        tier1.humanize = True
                        tier1.timeout = 5

                        source = {
                            "site": {"name": "test", "origin": "https://example.com"},
                            "search": {"request_template": "/search?q={query}"},
                        }
                        results = tier1.search(source, "test")

        assert len(results) == 1
        mock_store.put.assert_called_once()
        call_args = mock_store.put.call_args
        assert call_args[0][0] == "https://example.com"
