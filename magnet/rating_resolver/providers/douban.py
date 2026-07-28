# -*- coding: utf-8 -*-
"""Douban ratings via suggest + subject_abstract JSON (avoids anti-bot HTML)."""
from __future__ import annotations

import json
import re

from magnet.rating_resolver.http_client import fetch
from magnet.rating_resolver.models import LookupQuery, RatingValue
from magnet.rating_resolver.normalize import normalize_title, strip_year_from_title
from magnet.rating_resolver.providers.base import Provider

_ID_RE = re.compile(r"subject/(\d+)")


class DoubanProvider(Provider):
    name = "douban"

    def lookup(self, query: LookupQuery) -> RatingValue:
        title = strip_year_from_title(query.title) or normalize_title(query.title)
        if not title:
            return RatingValue(source=self.name, status="no_match", note="empty title")

        sid, matched, myear = self._suggest(title, query.year)
        if not sid:
            return RatingValue(source=self.name, status="no_match", note="no douban subject")

        # Prefer JSON abstract (HTML subject page is often challenge-walled)
        abstract = self._abstract(sid)
        if abstract.get("rate") is not None:
            rate = abstract["rate"]
            return RatingValue(
                source=self.name,
                status="ok",
                score=rate,
                scale=10.0,
                score_text=f"{rate}/10",
                url=f"https://movie.douban.com/subject/{sid}/",
                external_id=sid,
                matched_title=abstract.get("title") or matched,
                matched_year=abstract.get("year") or myear,
                confidence=0.85,
                via="subject_abstract",
            )

        return RatingValue(
            source=self.name,
            status="no_match",
            external_id=sid,
            url=f"https://movie.douban.com/subject/{sid}/",
            matched_title=matched or abstract.get("title"),
            matched_year=myear,
            note=abstract.get("note") or "subject found but no rate field",
        )

    def _suggest(
        self, title: str, year: int | None
    ) -> tuple[str | None, str | None, int | None]:
        resp = fetch(
            "https://movie.douban.com/j/subject_suggest",
            params={"q": title},
            headers={
                "Referer": "https://movie.douban.com/",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15,
        )
        if resp.status_code != 200 or not resp.text.strip():
            return None, None, None
        try:
            items = json.loads(resp.text)
        except json.JSONDecodeError:
            return None, None, None
        if not isinstance(items, list) or not items:
            return None, None, None

        best = items[0]
        if year is not None:
            for it in items:
                y = str(it.get("year") or "")
                if str(year) in y:
                    best = it
                    break
        sid = str(best.get("id") or "") or None
        if not sid and best.get("url"):
            m = _ID_RE.search(str(best["url"]))
            sid = m.group(1) if m else None
        myear = None
        try:
            myear = int(str(best.get("year") or "")[:4])
        except ValueError:
            myear = None
        return sid, best.get("title") or best.get("sub_title"), myear

    def _abstract(self, sid: str) -> dict:
        resp = fetch(
            "https://movie.douban.com/j/subject_abstract",
            params={"subject_id": sid},
            headers={
                "Referer": f"https://movie.douban.com/subject/{sid}/",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15,
        )
        if resp.status_code != 200 or not resp.text:
            return {"note": f"abstract HTTP {resp.status_code}"}
        try:
            data = json.loads(resp.text)
        except json.JSONDecodeError:
            return {"note": "abstract bad json"}
        sub = data.get("subject") or {}
        rate = sub.get("rate")
        try:
            rate_f = float(rate) if rate not in (None, "", "0", 0) else None
        except (TypeError, ValueError):
            rate_f = None
        year = None
        try:
            year = int(str(sub.get("release_year") or "")[:4])
        except ValueError:
            year = None
        return {
            "rate": rate_f,
            "title": sub.get("title"),
            "year": year,
            "note": None if rate_f is not None else "no rate in abstract",
        }
