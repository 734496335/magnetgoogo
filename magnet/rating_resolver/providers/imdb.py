# -*- coding: utf-8 -*-
"""IMDb ratings: IMDb suggestion API → Cinemeta snapshot (stable third-party)."""
from __future__ import annotations

import json
import re
from urllib.parse import quote

from magnet.rating_resolver.http_client import fetch
from magnet.rating_resolver.models import LookupQuery, RatingValue
from magnet.rating_resolver.normalize import normalize_title, strip_year_from_title
from magnet.rating_resolver.providers.base import Provider

_TT_RE = re.compile(r"(tt\d{7,})")


class ImdbProvider(Provider):
    name = "imdb"

    def lookup(self, query: LookupQuery) -> RatingValue:
        imdb_id = (query.imdb_id or "").strip().lower()
        if imdb_id and not imdb_id.startswith("tt"):
            imdb_id = f"tt{imdb_id}" if imdb_id.isdigit() else imdb_id

        matched_title = None
        matched_year = None
        if not imdb_id:
            imdb_id, matched_title, matched_year = self._suggest(query)
        if not imdb_id:
            return RatingValue(
                source=self.name,
                status="no_match",
                note="no imdb id from suggestion",
            )

        # Cinemeta first (stable, no anti-bot)
        r = self._cinemeta_by_id(imdb_id)
        if r.status == "ok":
            if matched_title and not r.matched_title:
                r.matched_title = matched_title
            if matched_year and not r.matched_year:
                r.matched_year = matched_year
            return r

        # Direct page scrape as last resort
        return self._scrape_title(imdb_id)

    def _suggest(
        self, query: LookupQuery
    ) -> tuple[str | None, str | None, int | None]:
        title = strip_year_from_title(query.title) or normalize_title(query.title)
        if not title:
            return None, None, None
        # IMDb suggestion path uses first character + slug
        slug = re.sub(r"\s+", "_", title.strip())
        # first path segment: first ascii letter or 'x'
        first = slug[0].lower() if slug and slug[0].isascii() and slug[0].isalnum() else "x"
        candidates = [
            f"https://v3.sg.media-imdb.com/suggestion/{first}/{quote(slug)}.json",
            f"https://v3.sg.media-imdb.com/suggestion/{first}/{quote(title)}.json",
            f"https://v2.sg.media-imdb.com/suggestion/{first}/{quote(slug)}.json",
        ]
        for url in candidates:
            resp = fetch(url, timeout=12)
            if resp.status_code != 200 or not resp.text:
                continue
            try:
                data = json.loads(resp.text)
            except json.JSONDecodeError:
                continue
            items = data.get("d") or []
            if not items:
                continue
            pick = None
            for it in items:
                iid = str(it.get("id") or "")
                if not iid.startswith("tt"):
                    continue
                qid = str(it.get("qid") or it.get("q") or "")
                # prefer movies/series
                if pick is None:
                    pick = it
                if query.year is not None:
                    y = it.get("y")
                    if y is not None and int(y) == int(query.year):
                        pick = it
                        break
                if "movie" in qid or qid == "feature":
                    if query.year is None or it.get("y") is None:
                        pick = it
            if pick is None:
                # first tt*
                for it in items:
                    if str(it.get("id") or "").startswith("tt"):
                        pick = it
                        break
            if pick is None:
                continue
            iid = str(pick.get("id"))
            year = None
            try:
                year = int(pick["y"]) if pick.get("y") is not None else None
            except (TypeError, ValueError):
                year = None
            return iid, pick.get("l"), year
        return None, None, None

    def _cinemeta_by_id(self, imdb_id: str) -> RatingValue:
        for kind in ("movie", "series"):
            url = f"https://v3-cinemeta.strem.io/meta/{kind}/{imdb_id}.json"
            resp = fetch(url, timeout=15)
            if resp.status_code != 200 or not resp.text:
                continue
            try:
                data = json.loads(resp.text)
            except json.JSONDecodeError:
                continue
            meta = data.get("meta") or {}
            score = meta.get("imdbRating") or meta.get("imdb_rating")
            try:
                score_f = float(score) if score not in (None, "", "N/A") else None
            except (TypeError, ValueError):
                score_f = None
            if score_f is None:
                continue
            year = None
            try:
                year = int(str(meta.get("releaseInfo") or meta.get("year") or "")[:4])
            except ValueError:
                year = None
            return RatingValue(
                source=self.name,
                status="ok",
                score=score_f,
                scale=10.0,
                score_text=f"{score_f}/10",
                url=f"https://www.imdb.com/title/{imdb_id}/",
                external_id=imdb_id,
                matched_title=meta.get("name"),
                matched_year=year,
                confidence=0.9,
                via="cinemeta",
                latency_ms=resp.elapsed_ms,
                note="third-party cinemeta snapshot of IMDb score",
            )
        return RatingValue(
            source=self.name,
            status="no_match",
            external_id=imdb_id,
            note="cinemeta no imdbRating",
            via="cinemeta",
            url=f"https://www.imdb.com/title/{imdb_id}/",
        )

    def _scrape_title(self, imdb_id: str) -> RatingValue:
        url = f"https://www.imdb.com/title/{imdb_id}/"
        resp = fetch(url, headers={"Accept-Language": "en-US,en;q=0.9"}, timeout=25)
        if resp.status_code in {403, 429}:
            return RatingValue(
                source=self.name,
                status="blocked",
                external_id=imdb_id,
                url=url,
                note=f"HTTP {resp.status_code}",
            )
        if resp.status_code >= 400:
            return RatingValue(
                source=self.name,
                status="error",
                external_id=imdb_id,
                url=url,
                note=f"HTTP {resp.status_code}",
            )
        m = re.search(
            r'"aggregateRating"\s*:\s*\{[^}]*"ratingValue"\s*:\s*"?(?P<v>\d+(?:\.\d+)?)"?',
            resp.text,
            re.I,
        )
        score = None
        if m:
            try:
                score = float(m.group("v"))
            except ValueError:
                score = None
        if score is None:
            return RatingValue(
                source=self.name,
                status="no_match",
                external_id=imdb_id,
                url=url,
                note="page has no ratingValue",
            )
        return RatingValue(
            source=self.name,
            status="ok",
            score=score,
            scale=10.0,
            score_text=f"{score}/10",
            url=url,
            external_id=imdb_id,
            confidence=0.85,
            via="imdb_scrape",
            latency_ms=resp.elapsed_ms,
        )
