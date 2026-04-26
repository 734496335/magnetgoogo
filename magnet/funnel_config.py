from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StageBudgets:
    stage0_concurrency: int = 120
    stage1_concurrency: int = 80
    stage2_concurrency: int = 40
    stage3_concurrency: int = 6

    stage0_timeout_s: float = 6.0
    stage1_timeout_s: float = 10.0
    stage2_timeout_s: float = 15.0
    stage3_timeout_s: float = 45.0

    max_seconds_per_site_total: float = 120.0
    stage3_reserve_s: float = 40.0
    stage0_retries: int = 2
    stage0_retry_backoff_s: float = 0.8


@dataclass(frozen=True)
class EvidencePolicy:
    min_hashes_to_green: int = 3
    max_magnets_to_collect: int = 20


@dataclass(frozen=True)
class SearchPolicy:
    bait_words: tuple[str, ...] = ("Inception", "Big Buck Bunny", "mp4", "权力的游戏", "战狼2", "流浪地球", "sdde", "act", "hunt")
    max_form_inferred_templates: int = 3
    max_fallback_templates: int = 8

    fallback_templates: tuple[str, ...] = (
        "/search?q={query}",
        "/search/{query}",
        "/?q={query}",
        "/?s={query}",
        "/search?keyword={query}",
        "/search?query={query}",
        "/s/{query}",
        "/index.php?q={query}",
    )


@dataclass(frozen=True)
class FunnelConfig:
    budgets: StageBudgets = StageBudgets()
    evidence: EvidencePolicy = EvidencePolicy()
    search: SearchPolicy = SearchPolicy()

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

