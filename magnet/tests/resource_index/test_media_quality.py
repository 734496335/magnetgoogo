from __future__ import annotations

from magnet.resource_index.normalize.media import (
    label_has_anomaly,
    normalize_country_labels,
    normalize_genre_label,
    normalize_genre_labels,
    normalize_resource,
    normalize_series_item_titles,
    parse_episode_identity,
)


def test_real_genre_and_country_fragments_normalize_deterministically() -> None:
    assert normalize_genre_label(": 喜剧") == "喜剧"
    assert normalize_genre_label("惊悚 片\"> 惊悚") == "惊悚"
    assert normalize_genre_label("纪录 片") == "纪录片"
    assert normalize_genre_labels([": 剧情", "惊悚 片\"> 惊悚", "纪录 片"]) == (
        "剧情",
        "惊悚",
        "纪录片",
    )
    assert normalize_country_labels([": 美国", ": 中国 大陆"]) == (
        "美国",
        "中国",
        "大陆",
    )


def test_normalized_labels_pass_anomaly_gate() -> None:
    dirty = [": 喜剧", "惊悚 片\"> 惊悚", "纪录 片", ": 美国", ": 中国 大陆"]
    assert all(label_has_anomaly(value) for value in dirty)
    cleaned = [
        *normalize_genre_labels(dirty[:3]),
        *normalize_country_labels(dirty[3:]),
    ]
    assert cleaned == ["喜剧", "惊悚", "纪录片", "美国", "中国", "大陆"]
    assert all(not label_has_anomaly(value) for value in cleaned)


def test_episode_identity_covers_required_patterns() -> None:
    first = parse_episode_identity("X-Men 97 S01E01 1080p")
    assert (first.season_number, first.episode_start, first.episode_end, first.episode_label) == (
        1,
        1,
        1,
        "S01E01",
    )

    range_english = parse_episode_identity("Show S01E01-E02 WEB-DL")
    assert (
        range_english.season_number,
        range_english.episode_start,
        range_english.episode_end,
        range_english.episode_label,
    ) == (1, 1, 2, "S01E01-E02")

    range_chinese = parse_episode_identity("第1-2集 1080P")
    assert (
        range_chinese.season_number,
        range_chinese.episode_start,
        range_chinese.episode_end,
        range_chinese.episode_label,
    ) == (None, 1, 2, "E01-E02")


def test_zero_or_reverse_episode_ranges_are_not_treated_as_real_episodes() -> None:
    assert parse_episode_identity("E00").episode_start is None
    assert parse_episode_identity("S00E01").season_number is None
    assert parse_episode_identity("S01E03-E02").episode_start is None


def test_generic_quality_title_uses_magnet_dn_episode_identity() -> None:
    normalized = normalize_resource(
        {
            "resource_type": "magnet",
            "provider": "magnet",
            "url": "magnet:?xt=urn:btih:ABC&dn=X-Men%2097%20S01E04%201080p%20WEB-DL",
            "info_hash": "ABC",
            "display_title": "1080P",
            "extraction_code": None,
            "quality_tags": ["1080p"],
        }
    )
    assert normalized.resource["display_title"] == "S01E04 · 1080P"
    assert normalized.resource["season_number"] == 1
    assert normalized.resource["episode_start"] == 4
    assert normalized.resource["episode_end"] == 4
    assert normalized.resource["episode_label"] == "S01E04"
    assert normalized.resource["title_source"] == "magnet_dn"


def test_series_output_title_follows_explicit_candidate_season() -> None:
    title, series_title = normalize_series_item_titles(
        {
            "title": "X战警97 第一季",
            "series_title": "X战警97 第一至二季",
            "season_number": 2,
        }
    )
    assert series_title == "X战警97"
    assert title == "X战警97 第二季"
