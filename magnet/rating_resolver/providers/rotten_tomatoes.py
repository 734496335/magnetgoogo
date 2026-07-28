# -*- coding: utf-8 -*-
"""Rotten Tomatoes: scorecard JSON scrape + OMDb compensation.

Important: never use bare `class="critics-score"` text — RT pages embed many
related-title scores (often 94%) that caused systematic false matches.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import quote

from magnet.rating_resolver.http_client import fetch
from magnet.rating_resolver.models import LookupQuery, RatingValue
from magnet.rating_resolver.normalize import strip_year_from_title
from magnet.rating_resolver.providers.base import Provider

_SCORECARD_RE = re.compile(
    r'<script[^>]+id="media-scorecard-json"[^>]*>(.*?)</script>',
    re.S | re.I,
)


class RottenTomatoesProvider(Provider):
    name = "rotten_tomatoes"

    def lookup(self, query: LookupQuery) -> RatingValue:
        omdb = self._omdb(query)
        if omdb.status == "ok":
            return omdb

        scraped = self._scrape(query)
        if scraped.status == "ok":
            return scraped
        if scraped.status == "blocked":
            return scraped
        return scraped if scraped.status != "skipped" else omdb

    def _omdb(self, query: LookupQuery) -> RatingValue:
        key = os.environ.get("OMDB_API_KEY") or os.environ.get("OMDB_KEY")
        if not key:
            return RatingValue(
                source=self.name,
                status="skipped",
                note="no OMDB_API_KEY; try scrape",
                via="omdb",
            )
        params: dict = {"apikey": key, "r": "json"}
        if query.imdb_id:
            params["i"] = query.imdb_id
        else:
            params["t"] = strip_year_from_title(query.title)
            if query.year:
                params["y"] = str(query.year)
        resp = fetch("https://www.omdbapi.com/", params=params, timeout=15)
        if resp.status_code != 200:
            return RatingValue(
                source=self.name,
                status="error",
                note=f"omdb HTTP {resp.status_code}",
                via="omdb",
            )
        try:
            data = json.loads(resp.text)
        except json.JSONDecodeError:
            return RatingValue(
                source=self.name, status="error", note="omdb bad json", via="omdb"
            )
        if str(data.get("Response")).lower() == "false":
            return RatingValue(
                source=self.name,
                status="no_match",
                note=data.get("Error") or "omdb not found",
                via="omdb",
            )
        score = None
        for r in data.get("Ratings") or []:
            if "Rotten" in str(r.get("Source") or ""):
                raw = str(r.get("Value") or "").replace("%", "").strip()
                try:
                    score = float(raw)
                except ValueError:
                    score = None
                break
        if score is None:
            return RatingValue(
                source=self.name,
                status="no_match",
                matched_title=data.get("Title"),
                note="omdb has title but no RT rating",
                via="omdb",
                external_id=data.get("imdbID"),
            )
        year = None
        yraw = str(data.get("Year") or "")[:4]
        if yraw.isdigit():
            year = int(yraw)
        return RatingValue(
            source=self.name,
            status="ok",
            score=score,
            scale=100.0,
            score_text=f"{int(score)}%",
            matched_title=data.get("Title"),
            matched_year=year,
            external_id=data.get("imdbID"),
            confidence=0.85,
            via="omdb",
            latency_ms=resp.elapsed_ms,
            note="third-party OMDb snapshot of RT",
        )

    def _scrape(self, query: LookupQuery) -> RatingValue:
        title = strip_year_from_title(query.title)
        if not title:
            return RatingValue(source=self.name, status="no_match", note="empty title")

        # Prefer English-ish search keys for Chinese titles when original_title present
        search_title = title
        if query.original_title and re.search(r"[A-Za-z]{3,}", query.original_title):
            search_title = strip_year_from_title(query.original_title) or query.original_title

        search_url = f"https://www.rottentomatoes.com/search?search={quote(search_title)}"
        resp = fetch(search_url, timeout=20)
        if resp.status_code in {403, 429, 503}:
            return RatingValue(
                source=self.name,
                status="blocked",
                note=f"search HTTP {resp.status_code}",
                via="rt_scrape",
            )
        if resp.status_code >= 400:
            return RatingValue(
                source=self.name,
                status="error",
                note=f"search HTTP {resp.status_code}",
                via="rt_scrape",
            )

        path = self._pick_search_path(resp.text, search_title, query.year)
        if not path:
            # retry with original query title if different
            if search_title != title:
                path = self._pick_search_path(resp.text, title, query.year)
        if not path:
            return RatingValue(
                source=self.name,
                status="no_match",
                note="search no confident movie path",
                via="rt_scrape",
            )

        candidates = [path]
        # if path ends with _YYYY, also try canonical without year
        m_year_path = re.match(r"(.+)_((?:19|20)\d{2})$", path)
        if m_year_path:
            candidates.append(m_year_path.group(1))

        page_url = None
        score = None
        kind = None
        meta_title = None
        latency = None
        for cand in candidates:
            page_url = f"https://www.rottentomatoes.com{cand}"
            page = fetch(page_url, timeout=20)
            latency = page.elapsed_ms
            if page.status_code in {403, 429}:
                return RatingValue(
                    source=self.name,
                    status="blocked",
                    url=page_url,
                    note=f"detail HTTP {page.status_code}",
                    via="rt_scrape",
                )
            if page.status_code >= 400:
                continue
            score, kind, meta_title = self._parse_scorecard(page.text)
            if score is not None:
                path = cand
                break

        if score is None or page_url is None:
            return RatingValue(
                source=self.name,
                status="no_match",
                url=page_url,
                matched_title=meta_title,
                note="scorecard has no critics/audience score",
                via="rt_scrape",
            )

        conf = 0.75 if kind == "critics" else 0.55
        text = f"{int(score)}%" if kind == "critics" else f"{int(score)}% audience"
        return RatingValue(
            source=self.name,
            status="ok",
            score=score,
            scale=100.0,
            score_text=text,
            url=page_url,
            matched_title=meta_title,
            confidence=conf,
            via="rt_scorecard",
            latency_ms=latency,
            note=f"from media-scorecard-json ({kind})",
        )

    def _parse_scorecard(self, html: str) -> tuple[float | None, str | None, str | None]:
        m = _SCORECARD_RE.search(html)
        if not m:
            return None, None, None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None, None, None

        meta_title = None
        # optional title fields vary
        for key in ("title", "name"):
            if isinstance(data.get(key), str):
                meta_title = data[key]
                break

        critics = data.get("criticsScore") or {}
        audience = data.get("audienceScore") or {}

        def _score_of(block: dict) -> float | None:
            raw = block.get("score")
            if raw in (None, "", "null"):
                return None
            try:
                v = float(raw)
            except (TypeError, ValueError):
                return None
            if not (0 < v <= 100):
                return None
            # require some signal that this is a real rating block
            counts = (
                block.get("ratingCount")
                or block.get("reviewCount")
                or block.get("likedCount")
                or 0
            )
            try:
                c = int(str(counts).replace(",", "").split("+")[0] or 0)
            except ValueError:
                c = 0
            if c <= 0 and not block.get("bandedRatingCount"):
                # allow if score present and certified fields exist
                if not block.get("sentiment") and not block.get("scoreType"):
                    return None
            return v

        cs = _score_of(critics) if isinstance(critics, dict) else None
        if cs is not None:
            return cs, "critics", meta_title
        aus = _score_of(audience) if isinstance(audience, dict) else None
        if aus is not None:
            return aus, "audience", meta_title
        return None, None, meta_title

    def _pick_search_path(self, html: str, title: str, year: int | None) -> str | None:
        """Require slug token overlap; never fall back to unrelated first hit."""
        paths = re.findall(r"/(?:m|tv)/[a-z0-9_]+", html, re.I)
        if not paths:
            return None
        seen: set[str] = set()
        uniq: list[str] = []
        for p in paths:
            pl = p.lower()
            if pl in seen:
                continue
            seen.add(pl)
            uniq.append(pl)

        stop = {
            "the", "and", "for", "part", "vol", "volume", "season", "series",
            "movie", "film", "with", "from",
        }
        tokens = re.findall(r"[a-z0-9]+", (title or "").lower())
        # drop tiny tokens, stopwords, pure years
        tokens = [
            t
            for t in tokens
            if len(t) > 2
            and t not in stop
            and not re.fullmatch(r"(?:19|20)\d{2}", t)
        ][:8]
        if not tokens:
            # Chinese-only / no latin tokens: refuse slug guessing
            return None

        best = None
        best_score = -10**9
        for p in uniq:
            slug = p.split("/")[-1]
            score = 0
            hits = 0
            for t in tokens:
                if t in slug:
                    score += 3
                    hits += 1
            # trailing _YYYY: only reward when matches query year; else penalize
            ym = re.search(r"_((?:19|20)\d{2})$", slug)
            if ym:
                y = int(ym.group(1))
                if year is not None and y == int(year):
                    score += 1
                else:
                    score -= 2
            # strong: all significant tokens present
            if hits >= max(1, len(tokens) - 1) and hits >= 2:
                score += 4
            # slight preference for shorter slugs (canonical over long alts)
            if hits > 0:
                score -= min(3, slug.count("_") // 2)
            if score > best_score:
                best_score = score
                best = p

        # need at least two points from a real token hit (hit=3)
        if best is None or best_score < 3:
            return None
        return best
