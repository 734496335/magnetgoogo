# -*- coding: utf-8 -*-
from __future__ import annotations

import re

_QUALITY = re.compile(
    r"\b(4K|2160[pP]|1080[pP]|720[pP]|480[pP]|BluRay|Blu-ray|WEB-?DL|WEBRip|"
    r"HDR|REMUX|x264|x265|HEVC|H\.?264|H\.?265|DTS|AAC|HD|BD|DVD)\b",
    re.I,
)
_LANG = re.compile(r"(国语|粤语|中字|英字|双语|简繁|无水印|内嵌|外挂|字幕)")
_BRACKETS = re.compile(r"[\[\(（【].*?[\]\)）】]")
_SEASON = re.compile(
    r"(第\s*[0-9一二三四五六七八九十百]+\s*季|Season\s*\d+|S\d{1,2}(?:E\d{1,2})?)",
    re.I,
)
_YEAR_SUFFIX = re.compile(r"(?:^|[\s_\-])((?:19|20)\d{2})(?:$|[\s_\-])")
_MULTI_SPACE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    t = (title or "").strip()
    if not t:
        return ""
    t = _BRACKETS.sub(" ", t)
    t = _QUALITY.sub(" ", t)
    t = _LANG.sub(" ", t)
    # keep season info lightly: collapse to space (matching is loose)
    t = _SEASON.sub(" ", t)
    t = t.replace("：", " ").replace(":", " ").replace("/", " ")
    t = _MULTI_SPACE.sub(" ", t).strip(" -_.")
    return t


def extract_year_hint(title: str, year: int | None = None) -> int | None:
    if year is not None:
        return year
    m = _YEAR_SUFFIX.search(title or "")
    if m:
        return int(m.group(1))
    return None


def strip_year_from_title(title: str) -> str:
    t = normalize_title(title)
    t = re.sub(r"(?:^|[\s_\-])((?:19|20)\d{2})$", "", t).strip(" -_")
    return t
