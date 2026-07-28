# -*- coding: utf-8 -*-
from __future__ import annotations

from magnet.rating_resolver.matching import enforce_match, rejection_reason, titles_equivalent
from magnet.rating_resolver.models import LookupQuery, RatingValue


def _ok(**kwargs) -> RatingValue:
    payload = {
        "source": "imdb",
        "status": "ok",
        "score": 8.0,
        "matched_title": "Inception",
        "matched_year": 2010,
        "confidence": 0.9,
    }
    payload.update(kwargs)
    return RatingValue(**payload)


def test_bilingual_subject_contains_long_query_title() -> None:
    assert titles_equivalent(
        "肖申克的救赎",
        "肖申克的救赎 The Shawshank Redemption (1994)",
    )
    assert titles_equivalent(
        "The Shawshank Redemption",
        "肖申克的救赎 The Shawshank Redemption (1994)",
    )


def test_short_chinese_containment_is_rejected() -> None:
    assert not titles_equivalent("侦探", "大喜侦探")
    assert titles_equivalent("木乃伊", "木乃伊")


def test_year_mismatch_is_rejected() -> None:
    query = LookupQuery(title="荣耀", year=2026)
    value = _ok(matched_title="The Glory", matched_year=2022)
    assert rejection_reason(query, value) == "year_mismatch"
    assert enforce_match(query, value).status == "no_match"


def test_cross_script_match_requires_original_title() -> None:
    value = _ok(matched_title="Wings of Dread", matched_year=2026)
    assert rejection_reason(LookupQuery(title="恐惧之翼", year=2026), value) == "title_mismatch"
    assert rejection_reason(
        LookupQuery(title="恐惧之翼", original_title="Wings of Dread", year=2026),
        value,
    ) is None


def test_exact_imdb_id_overrides_title_translation() -> None:
    query = LookupQuery(title="盗梦空间", year=2010, imdb_id="tt1375666")
    value = _ok(external_id="tt1375666", matched_title="Inception", matched_year=2010)
    assert rejection_reason(query, value) is None


def test_wrong_imdb_id_is_rejected() -> None:
    query = LookupQuery(title="盗梦空间", year=2010, imdb_id="tt1375666")
    value = _ok(external_id="tt0111161", matched_title="Inception", matched_year=2010)
    assert rejection_reason(query, value) == "imdb_id_mismatch"


def test_rt_result_without_a_matchable_title_is_rejected() -> None:
    query = LookupQuery(title="一个中文片名", year=2026)
    value = _ok(
        source="rotten_tomatoes",
        matched_title=None,
        matched_year=None,
        url="https://www.rottentomatoes.com/m/unrelated_movie",
        via="rt_scorecard",
    )
    assert rejection_reason(query, value) == "title_mismatch"


def test_short_exact_title_without_provider_year_is_rejected() -> None:
    query = LookupQuery(title="木乃伊", year=2026)
    value = _ok(source="bangumi", matched_title="木乃伊", matched_year=None)
    assert rejection_reason(query, value) == "short_title_without_year"
