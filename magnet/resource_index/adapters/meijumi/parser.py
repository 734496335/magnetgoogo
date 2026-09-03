"""Pure parsers for Meijumi latest-series pages."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from magnet.resource_index.domain.movie_models import (
    MovieDetail,
    MovieListingCandidate,
    MovieResource,
)
from magnet.resource_index.normalize.magnets import normalize_magnet_uri
from magnet.resource_index.normalize.text import normalize_whitespace

SOURCE_ID = "meijumi"
ORIGIN = "https://www.meijumi.net"
PARSER_VERSION = "meijumi-parser/1.0.0"

_CLOUD_PROVIDERS = {
    "pan.baidu.com": "baidu",
    "pan.quark.cn": "quark",
    "pan.xunlei.com": "xunlei",
    "www.alipan.com": "alipan",
    "www.aliyundrive.com": "aliyun",
}
_QUALITY_PATTERNS = (
    (re.compile(r"(?i)(?:2160p|4k)"), "4K"),
    (re.compile(r"(?i)1080p"), "1080p"),
    (re.compile(r"(?i)720p"), "720p"),
    (re.compile(r"中英(?:双)?字(?:幕)?"), "中英双字"),
    (re.compile(r"中字(?:幕)?"), "中字"),
    (re.compile(r"无字(?:幕)?"), "无字幕"),
)
_FIELD_ALIASES = {
    "中文译名": "title",
    "外语原名": "original_title",
    "制作地区": "countries",
    "类别": "genres",
    "语言": "languages",
    "首映时间": "release_date",
    "季数": "season_number",
    "集数": "episode_count",
    "单集片长": "duration_minutes",
    "主演": "actors",
    "导演": "directors",
    "IMDb评分": "imdb_rating",
    "豆瓣评分": "douban_rating",
    "更新": "update_status",
}


def extract_quality_tags(*values: str | None) -> tuple[str, ...]:
    text = " ".join(value for value in values if value)
    output: list[str] = []
    for pattern, label in _QUALITY_PATTERNS:
        if pattern.search(text) and label not in output:
            output.append(label)
    return tuple(output)


def _source_key(detail_url: str) -> str:
    return urlparse(detail_url).path


def _content_code(detail_url: str) -> str:
    match = re.fullmatch(r"/(\d+)\.html", urlparse(detail_url).path)
    return match.group(1) if match else hashlib.sha256(detail_url.encode("utf-8")).hexdigest()[:16]


def _chinese_number(value: str) -> int | None:
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if not value:
        return None
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        number = tens * 10 + ones
        return number if number > 0 else None
    if all(character in digits for character in value):
        number = int("".join(str(digits[character]) for character in value))
        return number if number > 0 else None
    return None


def _season_number(value: str) -> int | None:
    stripped = normalize_whitespace(value)
    if stripped.isdigit():
        number = int(stripped)
        return number if number > 0 else None
    patterns = (
        r"第\s*(\d+)\s*季",
        r"(?i)season\s*(\d+)",
        r"(?i)\bS(\d{1,2})(?:E\d+)?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, stripped)
        if match:
            number = int(match.group(1))
            return number if number > 0 else None
    match = re.search(r"第([零〇一二两三四五六七八九十]+)季", stripped)
    return _chinese_number(match.group(1)) if match else None


def _episode_number(value: str) -> int | None:
    for pattern in (
        r"第\s*(\d+)\s*集",
        r"全\s*(\d+)\s*集",
        r"更新至\s*(\d+)\s*集",
        r"(?i)\bS\d{1,2}E(\d{1,3})\b",
    ):
        matches = re.findall(pattern, value)
        if matches:
            number = max(int(item) for item in matches)
            return number if number > 0 else None
    return None


def parse_latest_listing(
    html: str,
    *,
    page_url: str,
    rank_offset: int = 0,
) -> list[MovieListingCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    output: list[MovieListingCandidate] = []
    for row in soup.select("li.news100"):
        anchor = row.select_one("span.zuo a[href]")
        if anchor is None:
            continue
        detail_url = urljoin(page_url, str(anchor.get("href") or ""))
        path = urlparse(detail_url).path
        if not re.fullmatch(r"/\d+\.html", path):
            continue
        title = normalize_whitespace(anchor.get_text(" ", strip=True))
        if not title:
            continue
        update_status = normalize_whitespace(
            row.select_one("span.zhong").get_text(" ", strip=True)
            if row.select_one("span.zhong")
            else ""
        ) or None
        date_text = normalize_whitespace(
            row.select_one("span.you").get_text(" ", strip=True)
            if row.select_one("span.you")
            else ""
        )
        update_date = None
        try:
            update_date = date.fromisoformat(date_text)
        except ValueError:
            pass
        category_labels = [
            normalize_whitespace(item.get_text(" ", strip=True))
            for item in row.select("span.buxianshi a")
        ]
        category_labels = [value for value in category_labels if value]
        episode_label = update_status
        episode_number = _episode_number(update_status or "")
        season_number = _season_number(update_status or "") or _season_number(title)
        listing_title = " ".join(
            value for value in (title, update_status, " / ".join(category_labels)) if value
        )
        output.append(
            MovieListingCandidate(
                rank=rank_offset + len(output) + 1,
                detail_url=detail_url,
                source_item_key=_source_key(detail_url),
                content_code=_content_code(detail_url),
                listing_title=listing_title,
                update_date=update_date,
                recommended=False,
                highlight_labels=(),
                quality_tags=extract_quality_tags(listing_title),
                content_kind="series",
                series_title=title,
                season_number=season_number,
                episode_number=episode_number,
                episode_label=episode_label,
                update_status=update_status,
                brand_id="meijumi",
                endpoint_origin=f"{urlparse(detail_url).scheme}://{urlparse(detail_url).netloc}",
            )
        )
    return output


def _field_values(container: Tag) -> dict[str, str]:
    text = container.get_text(" ", strip=True).replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    for label in sorted(_FIELD_ALIASES, key=len, reverse=True):
        flexible = r"\s*".join(re.escape(character) for character in label)
        text = re.sub(flexible, label, text, flags=re.I)
    labels = "|".join(re.escape(label) for label in sorted(_FIELD_ALIASES, key=len, reverse=True))
    result: dict[str, str] = {}
    for match in re.finditer(
        rf"(?:^|•)\s*({labels})\s*[:：]\s*(.*?)(?=\s*•\s*(?:{labels})\s*[:：]|$)",
        text,
        re.I,
    ):
        target = _FIELD_ALIASES[match.group(1)]
        value = normalize_whitespace(match.group(2))
        if value:
            result[target] = value
    return result


def _split_values(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    output: list[str] = []
    for part in re.split(r"\s*/\s*|\s*[，,]\s*|\s+\|\s+", value):
        cleaned = normalize_whitespace(part)
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return tuple(output)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    match = re.search(r"(19\d{2}|20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", value)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _cloud_provider(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not host:
        return None
    for known, provider in _CLOUD_PROVIDERS.items():
        if host == known or host.endswith("." + known):
            return provider
    return None


def _extraction_code(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    for key in ("pwd", "password", "code"):
        values = query.get(key)
        if values and values[0]:
            return values[0]
    return None


def _resource_title(anchor: Tag) -> str:
    text = normalize_whitespace(anchor.get_text(" ", strip=True))
    parent = anchor.parent
    if parent is not None:
        line = normalize_whitespace(parent.get_text(" ", strip=True))
        if line and len(line) <= 180:
            return line
    return text or str(anchor.get("href") or "")


def _resources(container: Tag) -> tuple[MovieResource, ...]:
    output: list[MovieResource] = []
    seen: set[str] = set()
    for anchor in container.select("a[href]"):
        raw_url = str(anchor.get("href") or "").strip()
        lower = raw_url.casefold()
        display_title = _resource_title(anchor)
        if lower.startswith("magnet:?"):
            try:
                normalized, info_hash = normalize_magnet_uri(raw_url, fallback_dn=display_title)
            except Exception:
                continue
            identity = f"hash:{info_hash}"
            if identity in seen:
                continue
            seen.add(identity)
            output.append(
                MovieResource(
                    resource_type="magnet",
                    provider="magnet",
                    resource_url=normalized,
                    info_hash=info_hash,
                    display_title=display_title,
                    extraction_code=None,
                    quality_tags=extract_quality_tags(display_title),
                )
            )
            continue
        provider = _cloud_provider(raw_url)
        if provider is None or raw_url in seen:
            continue
        seen.add(raw_url)
        output.append(
            MovieResource(
                resource_type="cloud",
                provider=provider,
                resource_url=raw_url,
                info_hash=None,
                display_title=display_title,
                extraction_code=_extraction_code(raw_url),
                quality_tags=extract_quality_tags(display_title),
            )
        )
    return tuple(output)


def parse_series_detail(
    html: str,
    *,
    candidate: MovieListingCandidate,
    raw_content: bytes | None = None,
) -> MovieDetail:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one(".single-content")
    if container is None:
        raise ValueError("Meijumi detail page is missing .single-content")
    upper = container.select_one(".shangbu") or container
    lower = container.select_one(".diibu") or container
    fields = _field_values(upper)
    heading_node = soup.select_one("h1")
    heading = normalize_whitespace(
        heading_node.get_text(" ", strip=True) if heading_node else candidate.series_title or candidate.listing_title
    )
    title = fields.get("title") or candidate.series_title or heading
    title = normalize_whitespace(title.split("/")[0])
    original_title = fields.get("original_title")
    if original_title:
        original_title = normalize_whitespace(original_title.split("/")[0])
    synopsis_node = upper.select_one("blockquote p, blockquote")
    synopsis = normalize_whitespace(synopsis_node.get_text(" ", strip=True)) if synopsis_node else None
    image = upper.select_one("img[src]")
    cover = urljoin(candidate.detail_url, str(image.get("src"))) if image else None
    release_date = _parse_date(fields.get("release_date"))
    year_match = re.search(r"(19\d{2}|20\d{2})", fields.get("release_date", "") + " " + candidate.listing_title)
    duration_match = re.search(r"(\d{1,4})\s*(?:min|分钟)", fields.get("duration_minutes", ""), re.I)
    season_number = candidate.season_number or _season_number(fields.get("season_number", "")) or _season_number(heading)
    resources = _resources(lower)
    quality_tags = list(candidate.quality_tags)
    for resource in resources:
        for label in resource.quality_tags:
            if label not in quality_tags:
                quality_tags.append(label)
    douban_text = fields.get("douban_rating")
    douban_match = re.search(r"(\d+(?:\.\d+)?)", douban_text or "")
    douban_rating = float(douban_match.group(1)) if douban_match else None
    if douban_rating is not None and douban_rating <= 0:
        douban_rating = None
    raw_hash = hashlib.sha256(
        raw_content if raw_content is not None else html.encode("utf-8")
    ).hexdigest()
    return MovieDetail(
        source_id=SOURCE_ID,
        source_item_key=candidate.source_item_key,
        content_code=candidate.content_code,
        detail_url=candidate.detail_url,
        listing_title=candidate.listing_title,
        title=title,
        original_title=original_title,
        year=int(year_match.group(1)) if year_match else None,
        update_date=candidate.update_date,
        release_date=release_date,
        duration_minutes=int(duration_match.group(1)) if duration_match else None,
        countries=_split_values(fields.get("countries")),
        genres=_split_values(fields.get("genres")),
        languages=_split_values(fields.get("languages")),
        directors=_split_values(fields.get("directors")),
        actors=_split_values(fields.get("actors")),
        imdb_id=None,
        douban_rating=douban_rating,
        douban_rating_text=douban_text,
        douban_url=None,
        cover_source_url=cover,
        synopsis=synopsis,
        recommended=candidate.recommended,
        highlight_labels=candidate.highlight_labels,
        quality_tags=tuple(quality_tags),
        parser_version=PARSER_VERSION,
        raw_document_hash=raw_hash,
        resources=resources,
        content_kind="series",
        series_title=candidate.series_title or title,
        season_number=season_number,
        episode_number=candidate.episode_number,
        episode_label=candidate.episode_label,
        update_status=candidate.update_status or fields.get("update_status"),
        brand_id="meijumi",
        endpoint_origin=candidate.endpoint_origin or ORIGIN,
    )
