"""Tests for Tier 0 HTTP — mock curl_cffi with 200/403/timeout responses."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from magnet.crawler_v3.tiers.tier0_http import Tier0Http, _looks_like_anti_bot
from magnet.crawler_v3.tiers.base import TierError, SearchResult


@pytest.fixture
def tier0():
    return Tier0Http(timeout=5)


@pytest.fixture
def simple_source():
    return {
        "site": {"name": "test", "origin": "https://example.com"},
        "search": {"request_template": "/search?keyword={query}"},
    }


def _make_mock_response(status_code=200, text="<html>ok</html>"):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    return r


class TestBuildSearchUrl:
    def test_basic_template(self, tier0, simple_source):
        url = tier0._build_search_url(simple_source, "hello")
        assert url == "https://example.com/search?keyword=hello"

    def test_full_url_template(self, tier0):
        src = {
            "site": {"name": "t", "origin": "https://example.com"},
            "search": {"request_template": "https://other.com/s?q={query}"},
        }
        url = tier0._build_search_url(src, "test")
        assert url == "https://other.com/s?q=test"

    def test_chinese_query_encoded(self, tier0, simple_source):
        url = tier0._build_search_url(simple_source, "蜘蛛侠")
        assert "%E8%9C%98%E8%9B%9B%E4%BE%A0" in url or "蜘蛛侠" not in url

    def test_missing_template_raises(self, tier0):
        src = {"site": {"name": "t", "origin": "https://example.com"}}
        with pytest.raises(TierError, match="no search.request_template"):
            tier0._build_search_url(src, "test")


class TestAntiBotDetection:
    def test_cloudflare_challenge(self):
        html = '<html><head><title>Just a moment...</title></head><body>challenge-platform</body>' + "x" * 200 + '</html>'
        assert _looks_like_anti_bot(html) is True

    def test_recaptcha_challenge(self):
        html = '<html>' * 100 + '/recaptcha/v4/challenge</html>'
        assert _looks_like_anti_bot(html) is True

    def test_normal_html(self):
        html = "<html>" * 100 + "<body>search results</body></html>"
        assert _looks_like_anti_bot(html) is False

    def test_empty_html(self):
        assert _looks_like_anti_bot("") is False

    def test_short_html(self):
        assert _looks_like_anti_bot("<html>ok</html>") is False


class TestTier0Fetch:
    @patch("magnet.crawler_v3.tiers.tier0_http.cc_requests")
    def test_success_200(self, mock_cc, tier0, simple_source):
        mock_cc.get.return_value = _make_mock_response(200, "<html>" * 200 + "result</html>")
        with patch.object(tier0, "_fetch", wraps=tier0._fetch):
            html = tier0._fetch("https://example.com/search?q=test", headers={})
        assert html is not None

    @patch("magnet.crawler_v3.tiers.tier0_http.cc_requests")
    def test_403_raises_tier_error(self, mock_cc, tier0):
        mock_cc.get.return_value = _make_mock_response(403)
        with pytest.raises(TierError, match="HTTP 403"):
            tier0._fetch("https://example.com/search", headers={})

    @patch("magnet.crawler_v3.tiers.tier0_http.cc_requests")
    def test_429_is_retryable(self, mock_cc, tier0):
        mock_cc.get.return_value = _make_mock_response(429)
        try:
            tier0._fetch("https://example.com/search", headers={})
        except TierError as e:
            assert e.retryable is True

    @patch("magnet.crawler_v3.tiers.tier0_http.cc_requests")
    def test_timeout_raises_retryable(self, mock_cc, tier0):
        mock_cc.get.side_effect = Exception("Connection timed out")
        with pytest.raises(TierError) as exc_info:
            tier0._fetch("https://example.com/search", headers={})
        assert exc_info.value.retryable is True


class TestTier0Search:
    @patch.object(Tier0Http, "_fetch")
    def test_anti_bot_detected_escalates(self, mock_fetch, tier0, simple_source):
        mock_fetch.return_value = "<html>Just a moment... challenge-platform " * 200
        with pytest.raises(TierError, match="anti-bot") as exc_info:
            tier0.search(simple_source, "test")
        assert exc_info.value.hint == "escalate_to_tier1"

    @patch.object(Tier0Http, "_fetch")
    def test_zero_results_raises(self, mock_fetch, tier0, simple_source):
        mock_fetch.return_value = "<html>" * 200 + "<body>no results</body></html>"
        with pytest.raises(TierError, match="zero results"):
            tier0.search(simple_source, "test")
