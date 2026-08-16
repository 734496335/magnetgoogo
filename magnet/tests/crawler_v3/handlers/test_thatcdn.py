"""Tests for the thatcdn handler — algorithm unit tests + integration markers."""
from __future__ import annotations

import base64
import json
from unittest.mock import patch, MagicMock

import pytest

from magnet.crawler_v3.handlers.thatcdn import (
    _random_str,
    _resolve_redirect_domain,
    _solve_captcha,
    _parse_search_results,
    _fetch_detail_magnets,
    _MAGNET_RE,
    _RDATA_RE,
    _TITLE_RE,
)
from magnet.crawler_v3.tiers.base import TierError


class TestRandomStr:
    def test_length(self):
        assert len(_random_str(10)) == 10
        assert len(_random_str(20)) == 20

    def test_alphanumeric(self):
        s = _random_str(100)
        assert all(c.isalnum() for c in s)

    def test_randomness(self):
        # Two calls should (almost certainly) produce different strings
        assert _random_str(20) != _random_str(20)


class TestRdataRegex:
    def test_matches_rdata_meta(self):
        html = '<meta name="rdata" content="abc123==">'
        m = _RDATA_RE.search(html)
        assert m is not None
        assert m.group(1) == "abc123=="

    def test_matches_single_quotes(self):
        html = "<meta name='rdata' content='dGVzdA=='>"  # base64("test") reversed
        m = _RDATA_RE.search(html)
        assert m is not None

    def test_no_match(self):
        html = '<meta name="viewport" content="width=device-width">'
        assert _RDATA_RE.search(html) is None


class TestResolveRedirectDomain:
    def test_returns_origin_when_no_rdata(self):
        session = MagicMock()
        r = MagicMock()
        r.status_code = 200
        r.text = "<html><body>normal site</body></html>"
        session.get.return_value = r

        result = _resolve_redirect_domain(session, "https://example.com")
        assert result == "https://example.com"

    def test_decodes_rdata_to_real_domain(self):
        # Simulate xiongmaogb.top's rdata: base64(reversed(JSON))
        real_urls = ["https://xiongmaoqv.top"]
        payload = json.dumps({"urls": real_urls}).encode()
        encoded = base64.b64encode(payload).decode()
        reversed_encoded = encoded[::-1]

        session = MagicMock()
        r = MagicMock()
        r.status_code = 200
        r.text = f'<html><meta name="rdata" content="{reversed_encoded}"></html>'
        session.get.return_value = r

        result = _resolve_redirect_domain(session, "https://xiongmaogb.top")
        assert result == "https://xiongmaoqv.top"

    def test_returns_origin_on_error(self):
        session = MagicMock()
        session.get.side_effect = Exception("timeout")
        result = _resolve_redirect_domain(session, "https://example.com")
        assert result == "https://example.com"

    def test_returns_origin_on_non_200(self):
        session = MagicMock()
        r = MagicMock()
        r.status_code = 403
        session.get.return_value = r
        result = _resolve_redirect_domain(session, "https://example.com")
        assert result == "https://example.com"


class TestMagnetRegex:
    def test_valid_magnet(self):
        html = 'href="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=test"'
        m = _MAGNET_RE.search(html)
        assert m is not None

    def test_32_char_hex_rejected(self):
        html = 'href="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef&dn=test"'
        assert _MAGNET_RE.search(html) is None

    def test_short_hash_rejected(self):
        html = 'href="magnet:?xt=urn:btih:tooshort"'
        assert _MAGNET_RE.search(html) is None

    def test_40_char_hash(self):
        html = 'magnet:?xt=urn:btih:da39a3ee5e6b4b0d3255bfef95601890afd80709'
        m = _MAGNET_RE.search(html)
        assert m is not None


class TestTitleRegex:
    def test_matches_panel_title(self):
        html = '''<h3 class="panel-title">
            <a href="/detail/12345">Test Movie Title</a>
        </h3>'''
        m = _TITLE_RE.search(html)
        assert m is not None
        assert "/detail/12345" in m.group(1)
        assert "Test Movie Title" in m.group(2)

    def test_no_match_garbage(self):
        html = "<div>no titles here</div>"
        assert _TITLE_RE.search(html) is None


class TestParseSearchResults:
    def test_extracts_titles_and_urls(self):
        html = '''
        <h3 class="panel-title"><a href="/detail/abc">Movie A</a></h3>
        <h3 class="panel-title"><a href="/detail/def">Movie B</a></h3>
        '''
        results = _parse_search_results(html, "https://example.com")
        assert len(results) == 2
        assert results[0]["title"] == "Movie A"
        assert results[0]["detail_url"] == "https://example.com/detail/abc"
        assert results[1]["title"] == "Movie B"

    def test_strips_inner_html(self):
        html = '<h3 class="panel-title"><a href="/detail/x"><span class="highlight">Bold</span> Title</a></h3>'
        results = _parse_search_results(html, "https://example.com")
        assert len(results) == 1
        assert results[0]["title"] == "Bold Title"

    def test_empty_html(self):
        assert _parse_search_results("", "https://example.com") == []


class TestFetchDetailMagnets:
    def test_extracts_magnets_from_detail_page(self):
        session = MagicMock()
        r = MagicMock()
        r.status_code = 200
        r.text = '<a href="magnet:?xt=urn:btih:abcdef0123456789abcdef0123456789abcdef01&dn=test">Download</a>'
        session.get.return_value = r

        magnets = _fetch_detail_magnets(session, "https://example.com/detail/123", "https://example.com")
        assert len(magnets) == 1
        assert "magnet:?xt=urn:btih:abcdef0123456789abcdef0123456789abcdef01" in magnets[0]

    def test_returns_empty_on_non_200(self):
        session = MagicMock()
        r = MagicMock()
        r.status_code = 404
        session.get.return_value = r

        magnets = _fetch_detail_magnets(session, "https://example.com/detail/123", "https://example.com")
        assert magnets == []

    def test_returns_empty_on_exception(self):
        session = MagicMock()
        session.get.side_effect = Exception("timeout")

        magnets = _fetch_detail_magnets(session, "https://example.com/detail/123", "https://example.com")
        assert magnets == []


class TestSolveCaptcha:
    def test_returns_html_if_no_captcha(self):
        """If search returns big HTML without captcha markers, return it directly."""
        session = MagicMock()
        r = MagicMock()
        r.status_code = 200
        r.text = "<html>" + "x" * 6000 + "</html>"
        session.get.return_value = r

        result = _solve_captcha(session, "https://example.com", "test")
        assert result is not None
        assert len(result) > 5000

    def test_returns_html_if_has_magnets(self):
        """If search results page already has magnets, return immediately."""
        session = MagicMock()
        r = MagicMock()
        r.status_code = 200
        r.text = 'magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=test'
        session.get.return_value = r

        result = _solve_captcha(session, "https://example.com", "test")
        assert result is not None

    def test_returns_none_on_non_200(self):
        session = MagicMock()
        r = MagicMock()
        r.status_code = 500
        session.get.return_value = r

        result = _solve_captcha(session, "https://example.com", "test")
        assert result is None


@pytest.mark.integration
class TestThatcdnIntegration:
    """Integration tests — hit real sites. NOT run in CI.

    Run with: pytest magnet/tests/crawler_v3/handlers/test_thatcdn.py -m integration -v
    """

    def test_xiongmaogb_real_search(self):
        from curl_cffi import requests as cc_requests
        from magnet.crawler_v3.handlers.thatcdn import thatcdn_search

        source = {
            "site": {"name": "xiongmaogb", "origin": "https://xiongmaogb.top"},
            "tier_override": {"tier": "tier2_handler", "platform": "thatcdn"},
        }
        results = thatcdn_search(source, "蜘蛛侠")
        assert len(results) >= 5
        assert all(r.magnet for r in results)

    def test_laowangzo_real_search(self):
        from magnet.crawler_v3.handlers.thatcdn import thatcdn_search

        source = {
            "site": {"name": "laowangzo", "origin": "https://laowangzo.top"},
            "tier_override": {"tier": "tier2_handler", "platform": "thatcdn"},
        }
        results = thatcdn_search(source, "蜘蛛侠")
        assert len(results) >= 5
        assert all(r.magnet for r in results)
