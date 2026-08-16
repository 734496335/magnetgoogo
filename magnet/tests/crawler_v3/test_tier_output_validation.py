from unittest.mock import MagicMock, patch

import pytest

from magnet.crawler_v3.parser import _bruteforce_magnet_scan
from magnet.crawler_v3.tiers.base import (
    SearchResult,
    TierError,
    has_bound_result_title,
    has_valid_btih_magnet,
    valid_search_results,
)
from magnet.crawler_v3.tiers.tier2_handler import HANDLER_REGISTRY, Tier2Handler


VALID_HEX = "0123456789abcdef0123456789abcdef01234567"
VALID_B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def test_btih_validator_accepts_only_standard_lengths():
    assert has_valid_btih_magnet(f"magnet:?xt=urn:btih:{VALID_HEX}&dn=test")
    assert has_valid_btih_magnet(f"magnet:?xt=urn:btih:{VALID_B32}&dn=test")
    assert not has_valid_btih_magnet("magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef&dn=test")
    assert not has_valid_btih_magnet("magnet:?xt=urn:btih:tooshort&dn=test")


def test_result_validator_requires_non_hash_bound_title():
    magnet = f"magnet:?xt=urn:btih:{VALID_HEX}"
    assert has_bound_result_title(SearchResult(title="Inception 2010", magnet=magnet))
    assert not has_bound_result_title(SearchResult(title="", magnet=magnet))
    assert not has_bound_result_title(SearchResult(title=VALID_HEX, magnet=magnet))
    assert not has_bound_result_title(SearchResult(title=f"hash:{VALID_HEX}", magnet=magnet))
    assert not has_bound_result_title(SearchResult(title="hash:01234567...", magnet=magnet))
    assert not has_bound_result_title(SearchResult(title=magnet, magnet=magnet))
    assert [r.title for r in valid_search_results([
        SearchResult(title="Inception 2010", magnet=magnet),
        SearchResult(title=VALID_HEX, magnet=magnet),
    ])] == ["Inception 2010"]


def test_bruteforce_requires_title_bound_dn():
    bare = f'<script>const x="magnet:?xt=urn:btih:{VALID_HEX}"</script>'
    assert _bruteforce_magnet_scan(bare) == []

    bound = f'<script>const x="magnet:?xt=urn:btih:{VALID_HEX}&amp;dn=Inception+2010"</script>'
    results = _bruteforce_magnet_scan(bound)
    assert len(results) == 1
    assert results[0].title == "Inception 2010"


def test_tier2_filters_invalid_magnets(monkeypatch):
    platform = "unit_validation_mixed"
    monkeypatch.setitem(
        HANDLER_REGISTRY,
        platform,
        lambda _source, _query: [
            SearchResult(title="bad", magnet="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef"),
            SearchResult(title="good", magnet=f"magnet:?xt=urn:btih:{VALID_HEX}"),
        ],
    )
    source = {"tier_override": {"platform": platform}}
    results = Tier2Handler().search(source, "test")
    assert [result.title for result in results] == ["good"]


def test_tier2_rejects_all_invalid_magnets(monkeypatch):
    platform = "unit_validation_invalid"
    monkeypatch.setitem(
        HANDLER_REGISTRY,
        platform,
        lambda _source, _query: [
            SearchResult(title="bad", magnet="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef"),
        ],
    )
    source = {"tier_override": {"platform": platform}}
    with pytest.raises(TierError, match="0 valid bound results"):
        Tier2Handler().search(source, "test")


def test_tier1_rejects_render_results_without_valid_btih():
    from magnet.crawler_v3.tiers import tier1_cloak

    browser = MagicMock()
    browser.new_page.return_value = MagicMock()
    tier = tier1_cloak.Tier1Cloak.__new__(tier1_cloak.Tier1Cloak)
    tier.headless = True
    tier.humanize = True
    tier.timeout = 5
    tier._poll_for_results = MagicMock(
        return_value=[SearchResult(title="bad", magnet="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef")]
    )
    source = {"site": {"origin": "https://example.com"}, "search": {"request_template": "/search?q={query}"}}

    with patch.object(tier1_cloak, "cloak_launch", return_value=browser):
        with pytest.raises(TierError, match="zero valid bound results"):
            tier.search(source, "test")
