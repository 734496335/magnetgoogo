"""Tests for tier1_cloak CF challenge detection — false positive avoidance."""
from unittest.mock import MagicMock

from magnet.crawler_v3.tiers.tier1_cloak import (
    CF_STRONG_MARKERS,
    CF_WEAK_TITLE_MARKERS,
    Tier1Cloak,
)


class _FakePage:
    """Minimal page mock for _title_has_weak_marker tests."""

    def __init__(self, title: str = ""):
        self._title = title

    def title(self) -> str:
        return self._title


def test_cf_strong_marker_in_body_is_challenge():
    """Body containing 'Just a moment' should be detected as challenge."""
    cloak = Tier1Cloak.__new__(Tier1Cloak)
    html = "<html><head></head><body>" + "x" * 200 + "Just a moment</body></html>"
    head = html[:8000]
    challenge = any(m in head for m in CF_STRONG_MARKERS)
    assert challenge is True


def test_weak_marker_only_in_body_not_challenge():
    """Body containing '请稍候' but title clean should NOT be challenge."""
    cloak = Tier1Cloak.__new__(Tier1Cloak)
    page = _FakePage(title="磁力星球 - 懂你的磁力链接搜索引擎")
    html = "<html><head></head><body>请稍候，正在加载内容</body></html>"
    head = html[:8000]
    challenge = (
        any(m in head for m in CF_STRONG_MARKERS)
        or cloak._title_has_weak_marker(page)
    )
    assert challenge is False


def test_weak_marker_in_title_is_challenge():
    """Title='请稍候...' should be detected as challenge."""
    cloak = Tier1Cloak.__new__(Tier1Cloak)
    page = _FakePage(title="请稍候...")
    html = "<html><head></head><body>正常内容</body></html>"
    head = html[:8000]
    challenge = (
        any(m in head for m in CF_STRONG_MARKERS)
        or cloak._title_has_weak_marker(page)
    )
    assert challenge is True


def test_clean_page_not_challenge():
    """Page with no markers should not be challenge."""
    cloak = Tier1Cloak.__new__(Tier1Cloak)
    page = _FakePage(title="磁力星球")
    html = "<html><head></head><body>正常搜索结果</body></html>"
    head = html[:8000]
    challenge = (
        any(m in head for m in CF_STRONG_MARKERS)
        or cloak._title_has_weak_marker(page)
    )
    assert challenge is False
