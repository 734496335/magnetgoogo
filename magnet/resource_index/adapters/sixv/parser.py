"""Parsers for the 6V latest-movie listing and detail pages."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from magnet.resource_index.adapters.sixv.models import (
    SixVListingCandidate,
    SixVMovieDetail,
    SixVMovieResource,
)
from magnet.resource_index.errors import DETAIL_DOM_DRIFT, ResourceIndexError
from magnet.resource_index.normalize.magnets import normalize_magnet_uri
from magnet.resource_index.normalize.text import normalize_whitespace

SOURCE_ID = "sixv"
PARSER_VERSION = "sixv-parser/1.0.1"
ORIGIN = "https://www.6v520.com"

_FIELD_LABELS = (
    "IMDb链接",
    "IMDb评分",
    "豆瓣评分",
    "豆瓣链接",
    "上映日期",
    "中文名",
    "标题",
    "译名",
    "片名",
    "年代",
    "产地",
    "类别",
    "语言",
    "片长",
    "导演",
    "编剧",
    "主演",
    "演员",
    "简介",
)
_SYNOPSIS_STOP_RE = re.compile(
    r"(?:【?\s*下载地址\s*】?|磁力\s*[:：]|上一篇|下一篇|下载帮助|网友评论)"
)

_FIELD_ALIASES = {
    "中文名": "标题",
    "主演": "演员",
}
_CLOUD_PROVIDERS = {
    "pan.quark.cn": "quark",
    "pan.baidu.com": "baidu",
    "pan.xunlei.com": "xunlei",
    "www.aliyundrive.com": "aliyun",
    "www.alipan.com": "alipan",
    "115.com": "115",
    "115cdn.com": "115",
}
_LISTING_GENRES = (
    "纪录片",
    "真人秀",
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
    "家庭",
    "运动",
    "灾难",
    "古装",
    "武侠",
)
_LISTING_GENRE_PATTERN = re.compile(
    "|".join(re.escape(label) for label in _LISTING_GENRES)
)
_QUALITY_PATTERNS = (
    (re.compile(r"(?i)(?:2160p|4k)"), "4K"),
    (re.compile(r"(?i)1080p"), "1080p"),
    (re.compile(r"(?i)720p"), "720p"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])BD(?![A-Za-z0-9])"), "BD"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])HD(?![A-Za-z0-9])"), "HD"),
    (re.compile(r"国粤双语"), "国粤双语"),
    (re.compile(r"国英双语"), "国英双语"),
    (re.compile(r"国语"), "国语"),
    (re.compile(r"中英双字"), "中英双字"),
    (re.compile(r"中字"), "中字"),
    (re.compile(r"无水印"), "无水印"),
)


def decode_sixv_html(content: bytes) -> str:
    head = content[:4096]
    match = re.search(br"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)", head, re.I)
    encoding = match.group(1).decode("ascii", errors="ignore") if match else "gb18030"
    if encoding.casefold() in {"gb2312", "gbk", "x-gbk"}:
        encoding = "gb18030"
    try:
        return content.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return content.decode("gb18030", errors="replace")


def extract_listing_genres(listing_title: str) -> tuple[str, ...]:
    prefix = listing_title.split("《", 1)[0]
    prefix = re.sub(r"^(?:19|20)\d{2}", "", prefix)
    result: list[str] = []
    for match in _LISTING_GENRE_PATTERN.finditer(prefix):
        label = match.group(0)
        if label not in result:
            result.append(label)
    return tuple(result)


def extract_quality_tags(*values: str | None) -> tuple[str, ...]:
    text = " ".join(value for value in values if value)
    result: list[str] = []
    for pattern, label in _QUALITY_PATTERNS:
        if pattern.search(text) and label not in result:
            result.append(label)
    return tuple(result)


def normalize_movie_genres(
    genres: tuple[str, ...] | list[str],
    listing_title: str | None = None,
) -> tuple[str, ...]:
    """Join malformed adjacent genre fragments and retain stable source order."""
    values = [normalize_whitespace(value) for value in genres if normalize_whitespace(value)]
    output: list[str] = []
    index = 0
    while index < len(values):
        current = values[index]
        if index + 1 < len(values):
            combined = current + values[index + 1]
            if combined in _LISTING_GENRES:
                current = combined
                index += 1
        if current not in output:
            output.append(current)
        index += 1
    if not output and listing_title:
        output.extend(extract_listing_genres(listing_title))
    return tuple(output)


def normalize_movie_title(title: str, listing_title: str | None = None) -> str:
    """Return a product-facing title without list prefixes or quality suffixes."""
    normalized = normalize_whitespace(title)
    listing = normalize_whitespace(listing_title or "")
    looks_like_listing = normalized == listing or bool(
        re.match(r"^(?:19|20)\d{2}[^《]{0,20}《", normalized)
    )
    bracket_source = normalized if "《" in normalized else listing
    bracket_match = re.search(r"《\s*([^》]+?)\s*》", bracket_source)
    if looks_like_listing and bracket_match:
        normalized = normalize_whitespace(bracket_match.group(1))
    normalized = re.sub(
        r"(?<=[\u3400-\u9fff0-9]):(?=[\u3400-\u9fff])",
        "：",
        normalized,
    )
    return normalized


def _is_red(element: Tag) -> bool:
    for node in [element, *element.find_all(True)]:
        color = str(node.get("color") or "").replace(" ", "").casefold()
        style = str(node.get("style") or "").replace(" ", "").casefold()
        if color in {"#ff0000", "#f00", "red"}:
            return True
        if re.search(r"color:(?:#ff0000|#f00|red)(?:;|$)", style):
            return True
    return False


def parse_latest_listing(
    html: str,
    *,
    page_url: str,
    rank_offset: int = 0,
) -> list[SixVListingCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("#main ul.list > li")
    page_host = (urlparse(page_url).hostname or "").casefold()
    if not page_host:
        return []
    candidates: list[SixVListingCandidate] = []
    for row in rows:
        anchor = row.find("a", href=True)
        if anchor is None:
            continue
        detail_url = urljoin(page_url, str(anchor["href"]))
        parsed = urlparse(detail_url)
        if (parsed.hostname or "").casefold() != page_host:
            continue
        code_match = re.search(r"/(\d+)\.html$", parsed.path)
        if code_match is None:
            continue
        listing_title = normalize_whitespace(anchor.get_text(" ", strip=True))
        if not listing_title:
            continue
        date_text = normalize_whitespace(
            row.find("span").get_text(" ", strip=True) if row.find("span") else ""
        )
        try:
            update_date = date.fromisoformat(date_text)
        except ValueError:
            update_date = None
        recommended = _is_red(anchor)
        rank = rank_offset + len(candidates) + 1
        candidates.append(
            SixVListingCandidate(
                rank=rank,
                detail_url=detail_url,
                source_item_key=parsed.path,
                content_code=code_match.group(1),
                listing_title=listing_title,
                update_date=update_date,
                recommended=recommended,
                highlight_labels=("推荐",) if recommended else (),
                quality_tags=extract_quality_tags(listing_title),
            )
        )
    return candidates


def _field_match(text: str) -> tuple[str, str] | None:
    normalized = text.replace("\u3000", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized.startswith("◎"):
        return None
    for label in _FIELD_LABELS:
        pattern = r"^◎\s*" + r"\s*".join(re.escape(ch) for ch in label) + r"\s*(.*)$"
        match = re.match(pattern, normalized, re.I)
        if match:
            value = normalize_whitespace(match.group(1))
            value = re.sub(r"^[：:]+\s*", "", value)
            value = re.sub(r'\s+片">\s*', " / ", value)
            return _FIELD_ALIASES.get(label, label), value
    return None


def _metadata(end_text: Tag) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    current: str | None = None
    for child in end_text.children:
        if not isinstance(child, Tag):
            continue
        if child.name == "hr":
            break
        if child.name not in {"div", "p"}:
            continue
        child_classes = set(child.get("class") or ())
        if child_classes & {"fl", "fr", "cr"}:
            continue
        if current == "简介" and child_classes & {"tps", "downtps"}:
            break
        raw_text = child.get_text("\n", strip=True)
        if child.find("img") is not None and not raw_text.strip():
            continue
        for raw_line in raw_text.splitlines():
            line = normalize_whitespace(raw_line)
            if not line:
                continue
            segments = [
                normalize_whitespace(segment)
                for segment in re.split(r"(?=◎)", line)
                if normalize_whitespace(segment)
            ]
            for text in segments:
                if current == "简介":
                    stop_match = _SYNOPSIS_STOP_RE.search(text)
                    if stop_match is not None:
                        prefix = normalize_whitespace(text[: stop_match.start()])
                        if prefix:
                            result.setdefault(current, []).append(prefix)
                        return result
                matched = _field_match(text)
                if matched is not None:
                    current, value = matched
                    result.setdefault(current, [])
                    if value:
                        result[current].append(value)
                    continue
                if current is not None:
                    result.setdefault(current, []).append(text)
    return result


def _split_values(values: list[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    output: list[str] = []
    for value in values:
        for part in re.split(r"\s*/\s*|\s*／\s*|\s*,\s*|\s*，\s*", value):
            cleaned = normalize_whitespace(part)
            cleaned = normalize_whitespace(re.sub(r'\s*片">\s*', " ", cleaned))
            if cleaned and cleaned not in output:
                output.append(cleaned)
    return tuple(output)


def _first(values: list[str] | None) -> str | None:
    return values[0] if values else None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    match = re.search(r"(19\d{2}|20\d{2})-(\d{2})-(\d{2})", value)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def _normalize_external_url(url: str) -> str:
    value = url.strip()
    if value.casefold().startswith("ttps://"):
        return "h" + value
    if value.casefold().startswith("ttp://"):
        return "h" + value
    return value


def _provider_for(url: str) -> str | None:
    host = (urlparse(url).hostname or "").casefold()
    if host in _CLOUD_PROVIDERS:
        return _CLOUD_PROVIDERS[host]
    for known, provider in _CLOUD_PROVIDERS.items():
        if host.endswith("." + known):
            return provider
    return None


def _extraction_code(anchor: Tag, url: str, provider: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    for key in ("pwd", "password", "code"):
        values = query.get(key)
        if values and values[0]:
            return values[0]
    if provider != "baidu" or anchor.parent is None:
        return None
    parent_text = normalize_whitespace(anchor.parent.get_text(" ", strip=True))
    anchor_text = normalize_whitespace(anchor.get_text(" ", strip=True))
    tail = parent_text.split(anchor_text, 1)[-1] if anchor_text in parent_text else parent_text
    match = re.search(r"提取码\s*[:：]?\s*([A-Za-z0-9]{4,12})", tail)
    return match.group(1) if match else None


def _resources(end_text: Tag) -> tuple[SixVMovieResource, ...]:
    resources: list[SixVMovieResource] = []
    seen: set[str] = set()
    for anchor in end_text.find_all("a", href=True):
        raw_url = _normalize_external_url(str(anchor["href"]))
        display_title = normalize_whitespace(anchor.get_text(" ", strip=True)) or raw_url
        if raw_url.startswith("magnet:?"):
            try:
                normalized, info_hash = normalize_magnet_uri(
                    raw_url,
                    fallback_dn=display_title,
                )
            except Exception:
                continue
            identity = f"hash:{info_hash}"
            if identity in seen:
                continue
            seen.add(identity)
            resources.append(
                SixVMovieResource(
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
        provider = _provider_for(raw_url)
        if provider is None or raw_url in seen:
            continue
        seen.add(raw_url)
        resources.append(
            SixVMovieResource(
                resource_type="cloud",
                provider=provider,
                resource_url=raw_url,
                info_hash=None,
                display_title=display_title,
                extraction_code=_extraction_code(anchor, raw_url, provider),
                quality_tags=extract_quality_tags(display_title),
            )
        )
    return tuple(resources)


def parse_movie_detail(
    html: str,
    *,
    candidate: SixVListingCandidate,
    raw_content: bytes | None = None,
) -> SixVMovieDetail:
    soup = BeautifulSoup(html, "html.parser")
    end_text = soup.select_one("#endText")
    if end_text is None:
        raise ResourceIndexError(
            DETAIL_DOM_DRIFT,
            "6V detail page is missing the expected content root",
            {"detail_url": candidate.detail_url, "selector": "#endText"},
        )
    metadata = _metadata(end_text)
    h1 = soup.find("h1")
    heading = normalize_whitespace(h1.get_text(" ", strip=True)) if h1 else candidate.listing_title
    title = normalize_movie_title(
        _first(metadata.get("标题")) or heading,
        candidate.listing_title,
    )
    original_title = _first(metadata.get("片名")) or _first(metadata.get("译名"))
    year_text = _first(metadata.get("年代"))
    year_match = re.search(r"(19\d{2}|20\d{2})", year_text or "")
    if year_match is None:
        year_match = re.match(r"^\s*(19\d{2}|20\d{2})(?!\d)", candidate.listing_title)
    duration_text = _first(metadata.get("片长"))
    duration_match = re.search(r"(\d{1,4})\s*分钟", duration_text or "")
    rating_text = _first(metadata.get("豆瓣评分"))
    rating_match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", rating_text or "")
    imdb_text = _first(metadata.get("IMDb链接"))
    imdb_match = re.search(r"tt\d+", imdb_text or "", re.I)
    cover = None
    first_image = end_text.find("img", src=True)
    if first_image is not None:
        cover = urljoin(candidate.detail_url, str(first_image["src"]))
    synopsis_values = metadata.get("简介") or []
    synopsis = normalize_whitespace(" ".join(synopsis_values)) or None
    resources = _resources(end_text)
    combined_quality = list(candidate.quality_tags)
    for resource in resources:
        for label in resource.quality_tags:
            if label not in combined_quality:
                combined_quality.append(label)
    raw_hash = hashlib.sha256(
        raw_content if raw_content is not None else html.encode("utf-8")
    ).hexdigest()
    return SixVMovieDetail(
        source_id=SOURCE_ID,
        source_item_key=candidate.source_item_key,
        content_code=candidate.content_code,
        detail_url=candidate.detail_url,
        listing_title=candidate.listing_title,
        title=title,
        original_title=original_title,
        year=int(year_match.group(1)) if year_match else None,
        update_date=candidate.update_date,
        release_date=_parse_date(_first(metadata.get("上映日期"))),
        duration_minutes=int(duration_match.group(1)) if duration_match else None,
        countries=_split_values(metadata.get("产地")),
        genres=normalize_movie_genres(
            _split_values(metadata.get("类别")),
            candidate.listing_title,
        ),
        languages=_split_values(metadata.get("语言")),
        directors=_split_values(metadata.get("导演")),
        actors=_split_values(metadata.get("演员")),
        imdb_id=imdb_match.group(0).lower() if imdb_match else None,
        douban_rating=float(rating_match.group(1)) if rating_match else None,
        douban_rating_text=rating_text,
        douban_url=_first(metadata.get("豆瓣链接")),
        cover_source_url=cover,
        synopsis=synopsis,
        recommended=candidate.recommended,
        highlight_labels=candidate.highlight_labels,
        quality_tags=tuple(combined_quality),
        parser_version=PARSER_VERSION,
        raw_document_hash=raw_hash,
        resources=resources,
    )
