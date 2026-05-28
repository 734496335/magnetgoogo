"""Tests for the orchestrator — TierError fallback chain and classify routing."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from magnet.crawler_v3.detector import classify, TierPlan
from magnet.crawler_v3.tiers.base import TierError, TierKind, SearchResult


class TestClassify:
    """detector.classify() should return correct Tier ordering."""

    def test_default_source_fast_first(self, fake_source):
        plan = classify(fake_source)
        assert TierKind.HTTP in plan.order
        assert TierKind.CLOAK in plan.order
        assert plan.order.index(TierKind.HTTP) < plan.order.index(TierKind.CLOAK)

    def test_tier_override_forces_handler_first(self, thatcdn_source):
        plan = classify(thatcdn_source)
        assert plan.order[0] == TierKind.HANDLER

    def test_requires_browser_goes_cloak_first(self, fake_source):
        fake_source["capabilities"] = {"requires_browser": True}
        plan = classify(fake_source)
        assert plan.order[0] == TierKind.CLOAK

    def test_waf_status_detail_goes_cloak_first(self, fake_source):
        fake_source["health"] = {"status": "yellow", "status_detail": "waf"}
        plan = classify(fake_source)
        assert plan.order[0] == TierKind.CLOAK

    def test_handler_override_has_http_fallback(self, thatcdn_source):
        plan = classify(thatcdn_source)
        assert TierKind.HTTP in plan.order
        # handler should be before http
        assert plan.order.index(TierKind.HANDLER) < plan.order.index(TierKind.HTTP)


class TestOrchestratorFallback:
    """orchestrator.search() should walk the Tier plan on TierError."""

    def test_fallback_on_retryable_error(self, fake_source):
        """Tier 0 raises retryable TierError → orchestrator tries Tier 1."""
        from magnet.crawler_v3 import orchestrator

        tier0 = MagicMock()
        tier0.kind = TierKind.HTTP
        tier0.supports.return_value = True
        tier0.search.side_effect = TierError("timeout", retryable=True)

        tier1 = MagicMock()
        tier1.kind = TierKind.CLOAK
        tier1.supports.return_value = True
        tier1.search.return_value = [SearchResult(title="ok", magnet="magnet:?xt=urn:btih:abc123")]

        def fake_get_tier(kind):
            return {TierKind.HTTP: tier0, TierKind.CLOAK: tier1}[kind]

        # Clear cached tiers
        orchestrator._TIER_CACHE.clear()
        with patch.object(orchestrator, "_get_tier", side_effect=fake_get_tier):
            results = orchestrator.search(fake_source, "test")

        assert len(results) == 1
        assert results[0].title == "ok"
        tier0.search.assert_called_once()
        tier1.search.assert_called_once()

    def test_returns_first_success(self, fake_source):
        """Tier 0 succeeds → orchestrator returns immediately, no Tier 1."""
        from magnet.crawler_v3 import orchestrator

        tier0 = MagicMock()
        tier0.kind = TierKind.HTTP
        tier0.supports.return_value = True
        tier0.search.return_value = [SearchResult(title="fast", magnet="magnet:?xt=urn:btih:def456")]

        tier1 = MagicMock()
        tier1.kind = TierKind.CLOAK
        tier1.supports.return_value = True

        def fake_get_tier(kind):
            return {TierKind.HTTP: tier0, TierKind.CLOAK: tier1}[kind]

        orchestrator._TIER_CACHE.clear()
        with patch.object(orchestrator, "_get_tier", side_effect=fake_get_tier):
            results = orchestrator.search(fake_source, "test")

        assert len(results) == 1
        tier1.search.assert_not_called()

    def test_handler_declines_fallback_to_tier0(self, thatcdn_source):
        """tier2_handler has no registered platform → supports()=False → falls to Tier 0."""
        from magnet.crawler_v3 import orchestrator

        # Use real Tier2Handler — it should decline since "thatcdn" is registered
        # but we can test with a platform that ISN'T registered
        bad_source = {
            "site": {"name": "bad", "origin": "https://bad.example.com"},
            "tier_override": {"tier": "tier2_handler", "platform": "nonexistent_platform"},
        }

        tier0 = MagicMock()
        tier0.kind = TierKind.HTTP
        tier0.supports.return_value = True
        tier0.search.return_value = [SearchResult(title="fallback", magnet="magnet:?xt=urn:btih:fallback123")]

        def fake_get_tier(kind):
            if kind == TierKind.HTTP:
                return tier0
            from magnet.crawler_v3.tiers.tier2_handler import Tier2Handler
            return Tier2Handler()

        orchestrator._TIER_CACHE.clear()
        with patch.object(orchestrator, "_get_tier", side_effect=fake_get_tier):
            results = orchestrator.search(bad_source, "test")

        # Tier 2 should decline, Tier 0 should succeed
        assert len(results) == 1
        assert results[0].title == "fallback"

    def test_exhausted_all_tiers_returns_empty(self, fake_source):
        """All tiers fail → returns empty list."""
        from magnet.crawler_v3 import orchestrator

        tier0 = MagicMock()
        tier0.kind = TierKind.HTTP
        tier0.supports.return_value = True
        tier0.search.side_effect = TierError("fail", retryable=False)

        tier1 = MagicMock()
        tier1.kind = TierKind.CLOAK
        tier1.supports.return_value = True
        tier1.search.side_effect = TierError("also fail", retryable=False)

        def fake_get_tier(kind):
            return {TierKind.HTTP: tier0, TierKind.CLOAK: tier1}[kind]

        orchestrator._TIER_CACHE.clear()
        with patch.object(orchestrator, "_get_tier", side_effect=fake_get_tier):
            results = orchestrator.search(fake_source, "test")

        assert results == []
