# -*- coding: utf-8 -*-
"""Bangumi public API — type=6 live-action first, then anime."""
from __future__ import annotations

import json
from urllib.parse import quote

from magnet.rating_resolver.http_client import fetch
from magnet.rating_resolver.models import LookupQuery, RatingValue
from magnet.rating_resolver.normalize import strip_year_from_title
from magnet.rating_resolver.providers.base import Provider


class BangumiProvider(Provider):
    name = "bangumi"

    def lookup(self, query: LookupQuery) -> RatingValue:
        title = strip_year_from_title(query.title)
        if not title:
            return RatingValue(source=self.name, status="no_match", note="empty title")

        items = []
        last_status = 0
        # type 6 = real (三次元), 2 = anime
        for t in (6, 2):
            url = (
                f"https://api.bgm.tv/search/subject/{quote(title)}"
                f"?type={t}&responseGroup=large"
            )
            resp = fetch(
                url,
                headers={
                    "User-Agent": "magnet-rating-resolver/1.0 (local tool; +https://localhost)",
                    "Accept": "application/json",
                },
                timeout=15,
            )
            last_status = resp.status_code
            if resp.status_code != 200 or not resp.text:
                continue
            try:
                data = json.loads(resp.text)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("error"):
                continue
            items = data.get("list") or []
            if items:
                break

        if not items:
            return RatingValue(
                source=self.name,
                status="no_match",
                note=f"search empty HTTP {last_status}",
            )

        pick = items[0]
        if query.year is not None:
            for it in items:
                ad = str(it.get("air_date") or "")
                if str(query.year) in ad:
                    pick = it
                    break

        sid = pick.get("id")
        matched_year = None
        air_date = str(pick.get("air_date") or "")
        if len(air_date) >= 4 and air_date[:4].isdigit():
            matched_year = int(air_date[:4])
        score = None
        rating = pick.get("rating") or {}
        if isinstance(rating, dict):
            score = rating.get("score")
        if score in (None, 0, 0.0):
            score = self._subject_score(sid)

        try:
            score_f = float(score) if score not in (None, "", 0, 0.0) else None
        except (TypeError, ValueError):
            score_f = None

        name = pick.get("name_cn") or pick.get("name")
        url_page = f"https://bgm.tv/subject/{sid}" if sid else None
        if score_f is None:
            return RatingValue(
                source=self.name,
                status="no_match",
                external_id=str(sid) if sid else None,
                url=url_page,
                matched_title=name,
                matched_year=matched_year,
                note="found subject without score",
            )
        return RatingValue(
            source=self.name,
            status="ok",
            score=score_f,
            scale=10.0,
            score_text=f"{score_f}/10",
            url=url_page,
            external_id=str(sid) if sid else None,
            matched_title=name,
            matched_year=matched_year,
            confidence=0.7,
            via="bgm_api",
        )

    def _subject_score(self, sid) -> float | None:
        if not sid:
            return None
        resp = fetch(
            f"https://api.bgm.tv/v0/subjects/{sid}",
            headers={
                "User-Agent": "magnet-rating-resolver/1.0 (local tool; +https://localhost)",
                "Accept": "application/json",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        try:
            data = json.loads(resp.text)
        except json.JSONDecodeError:
            return None
        rating = data.get("rating") or {}
        score = rating.get("score")
        try:
            v = float(score)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
