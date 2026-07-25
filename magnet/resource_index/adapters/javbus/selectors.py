"""JavBus DOM selectors and field-label maps (adapter-local only)."""

from __future__ import annotations

PARSER_VERSION = "javbus-parser/1.0.0"
SOURCE_ID = "javbus"
ORIGIN = "https://www.javbus.com"

LISTING_ITEM = "a.movie-box"
DETAIL_TITLE = "h3"
DETAIL_INFO = "div.info, div.col-md-3.info, .movie .info"
DETAIL_COVER = "a.bigImage"
DETAIL_SAMPLE = "#sample-waterfall a.sample-box, .sample-box"

# Label text variants (zh-CN / zh-TW / en)
FIELD_LABELS = {
    "content_code": ("識別碼", "识别码", "品番", "ID", "Code"),
    "release_date": ("發行日期", "发行日期", "発売日", "Release Date", "日期"),
    "duration": ("長度", "长度", "収録時間", "Duration", "时长"),
    "director": ("導演", "导演", "監督", "Director"),
    "maker": ("製作商", "制作商", "メーカー", "Studio", "Maker"),
    "publisher": ("發行商", "发行商", "レーベル", "Label", "Publisher"),
    "series": ("系列", "シリーズ", "Series"),
    "genre": ("類別", "类别", "ジャンル", "Genre", "Tags", "類別："),
    "actors": ("演員", "演员", "女優", "Actor", "Cast"),
}

AGE_GATE_MARKERS = (
    "driver-verify",
    "age-check",
    "age verify",
    "成年",
    "已满18",
    "已滿18",
    "I am 18",
    "over 18",
)

CHALLENGE_MARKERS = (
    "cf-challenge",
    "just a moment",
    "turnstile",
    "checking your browser",
    "cf-browser-verification",
)

GID_RE = r"var\s+gid\s*=\s*(\d+)"
UC_RE = r"var\s+uc\s*=\s*(\d+)"
