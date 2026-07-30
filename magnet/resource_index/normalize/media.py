"""Deterministic media label and episodic-resource normalization.

This module is deliberately local and rule-based.  It is part of the runtime
path and must never call an LLM or require human interpretation.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse

from magnet.resource_index.normalize.text import normalize_whitespace

_CANONICAL_GENRES = (
    "纪录片",
    "真人秀",
    "脱口秀",
    "动作",
    "剧情",
    "科幻",
    "喜剧",
    "惊悚",
    "恐怖",
    "爱情",
    "奇幻",
    "动画",
    "战争",
    "犯罪",
    "悬疑",
    "冒险",
    "传记",
    "历史",
    "音乐",
    "歌舞",
    "家庭",
    "运动",
    "灾难",
    "古装",
    "武侠",
    "儿童",
    "短片",
    "同性",
    "西部",
)
_GENRE_COMPACT = {label.replace(" ", ""): label for label in _CANONICAL_GENRES}
_COUNTRY_ALIASES = {
    "usa": ("美国",),
    "u.s.a": ("美国",),
    "unitedstates": ("美国",),
    "unitedstatesofamerica": ("美国",),
    "美国": ("美国",),
    "uk": ("英国",),
    "u.k": ("英国",),
    "unitedkingdom": ("英国",),
    "英国": ("英国",),
    "southkorea": ("韩国",),
    "korea": ("韩国",),
    "韩国": ("韩国",),
    "japan": ("日本",),
    "日本": ("日本",),
    "中国大陆": ("中国", "大陆"),
    "中国内地": ("中国", "大陆"),
    "中国": ("中国",),
    "大陆": ("大陆",),
    "hongkong": ("香港",),
    "中国香港": ("中国", "香港"),
    "香港": ("香港",),
    "taiwan": ("台湾",),
    "中国台湾": ("中国", "台湾"),
    "台湾": ("台湾",),
}
_GENERIC_RESOURCE_TITLE = re.compile(
    r"(?i)^\s*(?:2160p|1080p|720p|4k|uhd|fhd|hd|bd|蓝光|磁力资源|下载|资源|夸克盘|百度盘|迅雷盘)\s*$"
)
_QUALITY_PATTERNS = (
    (re.compile(r"(?i)(?:2160p|4k|uhd)"), "4K"),
    (re.compile(r"(?i)1080p|fhd"), "1080P"),
    (re.compile(r"(?i)720p"), "720P"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])bd(?![A-Za-z0-9])|blu-?ray|蓝光"), "BD"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])hd(?![A-Za-z0-9])"), "HD"),
)
_HTML_TAG = re.compile(r"<[^>]*>")
_HTML_TAIL = re.compile(r"(?:\\?[\"']?\s*>)+")
_LEADING_PUNCTUATION = re.compile(r"^[\s:：;；,，/／|·•\-—_]+")
_TRAILING_PUNCTUATION = re.compile(r"[\s:：;；,，/／|·•\-—_]+$")
_MULTI_SEPARATOR = re.compile(r"\s*(?:/|／|,|，|\||;|；|·|•)\s*")


@dataclass(frozen=True)
class EpisodeIdentity:
    season_number: int | None
    episode_start: int | None
    episode_end: int | None
    episode_label: str | None

    @property
    def has_episode(self) -> bool:
        return self.episode_start is not None


@dataclass(frozen=True)
class NormalizedResource:
    resource: dict[str, object]
    parsed_identity: EpisodeIdentity
    title_source: str


def _clean_fragment(raw: object) -> str:
    value = html.unescape(str(raw or "")).replace("\u3000", " ").replace("\xa0", " ")
    value = _HTML_TAG.sub(" ", value)
    value = _HTML_TAIL.sub(" ", value)
    value = value.replace("\\\"", " ").replace("\\'", " ")
    value = _LEADING_PUNCTUATION.sub("", value)
    value = _TRAILING_PUNCTUATION.sub("", value)
    return normalize_whitespace(value)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = normalize_whitespace(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return tuple(output)


def normalize_genre_label(raw: object) -> str | None:
    """Normalize one genre label while preserving unknown clean labels."""
    cleaned = _clean_fragment(raw)
    if not cleaned:
        return None
    compact = re.sub(r"\s+", "", cleaned)
    # Real broken values can contain duplicated text around a leaked HTML tail,
    # e.g. ``惊悚 片\"> 惊悚``.  Prefer a known canonical genre found anywhere.
    matches = [label for key, label in _GENRE_COMPACT.items() if key in compact]
    if matches:
        matches.sort(key=lambda value: (-len(value), _CANONICAL_GENRES.index(value)))
        return matches[0]
    cleaned = re.sub(r"(?<=\S)\s+(?=片(?:$|\s))", "", cleaned)
    cleaned = _LEADING_PUNCTUATION.sub("", cleaned)
    cleaned = _TRAILING_PUNCTUATION.sub("", cleaned)
    return normalize_whitespace(cleaned) or None


def normalize_genre_labels(
    values: Iterable[object],
    *,
    fallback_text: str | None = None,
) -> tuple[str, ...]:
    output: list[str] = []
    for raw in values:
        cleaned = _clean_fragment(raw)
        if not cleaned:
            continue
        parts = _MULTI_SEPARATOR.split(cleaned)
        for part in parts:
            label = normalize_genre_label(part)
            if label and label not in output:
                output.append(label)
    if not output and fallback_text:
        compact = re.sub(r"\s+", "", _clean_fragment(fallback_text))
        for label in _CANONICAL_GENRES:
            if label in compact and label not in output:
                output.append(label)
    return tuple(output)


def normalize_country_label(raw: object) -> tuple[str, ...]:
    """Normalize one country/region fragment into stable matching labels."""
    cleaned = _clean_fragment(raw)
    if not cleaned:
        return ()
    compact = re.sub(r"[\s._-]+", "", cleaned).casefold()
    alias = _COUNTRY_ALIASES.get(compact)
    if alias:
        return alias
    # Keep a clean unknown country as one value. Internal spaces are meaningful
    # for names such as ``新 西兰`` only when the source actually inserted them;
    # compact common Chinese country names deterministically.
    for country in ("新西兰", "澳大利亚", "加拿大", "法国", "德国", "西班牙", "意大利", "泰国", "印度"):
        if compact == country.casefold():
            return (country,)
    return (normalize_whitespace(cleaned),)


def normalize_country_labels(values: Iterable[object]) -> tuple[str, ...]:
    output: list[str] = []
    for raw in values:
        cleaned = _clean_fragment(raw)
        if not cleaned:
            continue
        for part in _MULTI_SEPARATOR.split(cleaned):
            for label in normalize_country_label(part):
                if label not in output:
                    output.append(label)
    return tuple(output)


def magnet_display_name(url: str) -> str | None:
    if not str(url).casefold().startswith("magnet:?"):
        return None
    values = parse_qs(urlparse(url).query).get("dn") or []
    if not values:
        return None
    return normalize_whitespace(unquote(str(values[0]))) or None


def resource_filename(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https", "ftp"}:
        return None
    name = PurePosixPath(unquote(parsed.path)).name
    return normalize_whitespace(name) or None


def _identity_from_match(season: str | None, start: str, end: str | None) -> EpisodeIdentity:
    season_number = int(season) if season else None
    episode_start = int(start)
    episode_end = int(end) if end else episode_start
    if (
        episode_start <= 0
        or episode_end <= 0
        or episode_end < episode_start
        or (season_number is not None and season_number <= 0)
    ):
        return EpisodeIdentity(None, None, None, None)
    if season_number is not None:
        if episode_end == episode_start:
            label = f"S{season_number:02d}E{episode_start:02d}"
        else:
            label = f"S{season_number:02d}E{episode_start:02d}-E{episode_end:02d}"
    elif episode_end == episode_start:
        label = f"E{episode_start:02d}"
    else:
        label = f"E{episode_start:02d}-E{episode_end:02d}"
    return EpisodeIdentity(season_number, episode_start, episode_end, label)


def parse_episode_identity(*values: object) -> EpisodeIdentity:
    text = " ".join(_clean_fragment(value) for value in values if _clean_fragment(value))
    if not text:
        return EpisodeIdentity(None, None, None, None)

    patterns = (
        # S01E01-E02 / S01.E01 to S01.E02 / S01E01-02
        re.compile(
            r"(?i)(?<![A-Z0-9])S(\d{1,2})[ ._-]*E(\d{1,4})"
            r"(?:\s*(?:-|~|to|至|到)\s*(?:S\d{1,2}[ ._-]*)?E?(\d{1,4}))?"
        ),
        # 1x03 / 1x03-04
        re.compile(r"(?i)(?<!\d)(\d{1,2})x(\d{1,4})(?:\s*(?:-|~|to)\s*(\d{1,4}))?"),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return _identity_from_match(match.group(1), match.group(2), match.group(3))

    # Chinese ranges must be checked before the single-episode pattern.
    match = re.search(r"第\s*0*(\d{1,4})\s*(?:-|~|至|到)\s*0*(\d{1,4})\s*集", text)
    if match:
        return _identity_from_match(None, match.group(1), match.group(2))
    match = re.search(r"第\s*0*(\d{1,4})\s*集", text)
    if match:
        return _identity_from_match(None, match.group(1), None)

    # Bare E01 is useful only with a clear token boundary.
    match = re.search(r"(?i)(?<![A-Z0-9])E0*(\d{1,4})(?:\s*(?:-|~|to)\s*E?0*(\d{1,4}))?", text)
    if match:
        return _identity_from_match(None, match.group(1), match.group(2))
    return EpisodeIdentity(None, None, None, None)


def extract_quality_label(*values: object, quality_tags: Sequence[object] = ()) -> str | None:
    candidates = [str(value or "") for value in values]
    candidates.extend(str(value or "") for value in quality_tags)
    text = " ".join(candidates)
    for pattern, label in _QUALITY_PATTERNS:
        if pattern.search(text):
            return label
    return None


def is_generic_resource_title(value: object) -> bool:
    cleaned = _clean_fragment(value)
    return not cleaned or bool(_GENERIC_RESOURCE_TITLE.fullmatch(cleaned))


def normalize_resource(
    resource: Mapping[str, object],
) -> NormalizedResource:
    """Return a resource with deterministic episode fields and display title."""
    output = dict(resource)
    url = str(output.get("url") or output.get("resource_url") or "")
    source_title = _clean_fragment(output.get("display_title"))
    dn = magnet_display_name(url)
    filename = resource_filename(url)

    title_source = "source"
    identity = parse_episode_identity(source_title)
    if not identity.has_episode and dn:
        identity = parse_episode_identity(dn)
        if identity.has_episode or is_generic_resource_title(source_title):
            title_source = "magnet_dn"
    if not identity.has_episode and filename:
        identity = parse_episode_identity(filename)
        if identity.has_episode or is_generic_resource_title(source_title):
            title_source = "filename"

    quality = extract_quality_label(
        source_title,
        dn,
        filename,
        quality_tags=tuple(output.get("quality_tags") or ()),
    )
    if identity.episode_label:
        display_title = identity.episode_label
        if quality:
            display_title = f"{display_title} · {quality}"
    elif source_title and not is_generic_resource_title(source_title):
        display_title = source_title
        title_source = "source"
    elif dn:
        display_title = dn
        title_source = "magnet_dn"
    elif filename:
        display_title = filename
        title_source = "filename"
    else:
        display_title = quality or source_title or "资源"
        title_source = "quality"

    output["display_title"] = normalize_whitespace(display_title)
    output["season_number"] = identity.season_number
    output["episode_start"] = identity.episode_start
    output["episode_end"] = identity.episode_end
    output["episode_label"] = identity.episode_label
    output["title_source"] = title_source
    return NormalizedResource(output, identity, title_source)


def chinese_season_label(number: int) -> str:
    digits = "零一二三四五六七八九"
    if number < 10:
        text = digits[number]
    elif number < 20:
        text = "十" + (digits[number % 10] if number % 10 else "")
    elif number < 100:
        text = digits[number // 10] + "十" + (digits[number % 10] if number % 10 else "")
    else:
        text = str(number)
    return f"第{text}季"


def normalize_series_base_title(value: object) -> str:
    text = _clean_fragment(value)
    text = re.sub(
        r"第\s*(?:\d+|[零〇一二两三四五六七八九十百]+)\s*(?:(?:至|到|-)\s*第?\s*(?:\d+|[零〇一二两三四五六七八九十百]+)\s*)?季.*$",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"(?i)\bseason\s*\d+.*$", "", text)
    text = re.sub(r"(?i)\bS\d{1,2}(?:E\d{1,4})?.*$", "", text)
    return normalize_whitespace(text)


def normalize_series_item_titles(item: Mapping[str, object]) -> tuple[str, str]:
    base = normalize_series_base_title(item.get("series_title") or item.get("title"))
    if not base:
        base = _clean_fragment(item.get("title"))
    season = item.get("season_number")
    title = base
    if isinstance(season, int) and not isinstance(season, bool) and season > 0:
        title = f"{base} {chinese_season_label(season)}"
    return normalize_whitespace(title), normalize_whitespace(base)


def label_has_anomaly(value: object) -> bool:
    raw = str(value or "")
    cleaned = normalize_whitespace(raw)
    if not cleaned:
        return True
    return bool(
        re.search(r"^\s*[:：]", raw)
        or _HTML_TAG.search(raw)
        or re.search(r"\\?[\"']?\s*>", raw)
        or re.search(r"\S\s+片(?:$|\s)", raw)
        or cleaned != _clean_fragment(raw)
    )
