"""Pure parsers for DYTT latest-movie pages."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from magnet.resource_index.domain.movie_models import (
    MovieDetail,
    MovieListingCandidate,
    MovieResource,
)
from magnet.resource_index.normalize.magnets import normalize_magnet_uri
from magnet.resource_index.normalize.text import normalize_whitespace

SOURCE_ID = "dytt8899"
PARSER_VERSION = "dytt-parser/1.1.0"
ORIGIN = "https://www.dytt8899.com"

_FIELD_ALIASES = {
    "标题": "标题",
    "中文名": "标题",
    "译名": "译名",
    "片名": "片名",
    "年代": "年代",
    "产地": "产地",
    "类别": "类别",
    "语言": "语言",
    "上映日期": "上映日期",
    "IMDb评分": "IMDb评分",
    "IMDb链接": "IMDb链接",
    "豆瓣评分": "豆瓣评分",
    "豆瓣链接": "豆瓣链接",
    "片长": "片长",
    "导演": "导演",
    "主演": "演员",
    "演员": "演员",
    "简介": "简介",
}

_QUALITY_PATTERNS = (
    (re.compile(r"(?i)(?:2160p|4k)"), "4K"),
    (re.compile(r"(?i)1080p"), "1080p"),
    (re.compile(r"(?i)720p"), "720p"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])BD(?![A-Za-z0-9])"), "BD"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])HD(?![A-Za-z0-9])"), "HD"),
    (re.compile(r"蓝光"), "蓝光"),
    (re.compile(r"国粤(?:英)?(?:三|双)语|国粤双语"), "国粤双语"),
    (re.compile(r"国英双语"), "国英双语"),
    (re.compile(r"国语"), "国语"),
    (re.compile(r"粤语"), "粤语"),
    (re.compile(r"中英双字"), "中英双字"),
    (re.compile(r"中字"), "中字"),
    (re.compile(r"TC"), "TC"),
)

_CLOUD_PROVIDERS = {
    "pan.baidu.com": "baidu",
    "pan.quark.cn": "quark",
    "pan.xunlei.com": "xunlei",
    "www.alipan.com": "alipan",
    "www.aliyundrive.com": "aliyun",
}


def decode_dytt_html(content: bytes) -> str:
    head = content[:4096]
    match = re.search(br"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)", head, re.I)
    encoding = match.group(1).decode("ascii", errors="ignore") if match else "gb18030"
    if encoding.casefold() in {"gb2312", "gbk", "x-gbk"}:
        encoding = "gb18030"
    try:
        return content.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return content.decode("gb18030", errors="replace")


def extract_quality_tags(*values: str | None) -> tuple[str, ...]:
    text = " ".join(value for value in values if value)
    labels: list[str] = []
    for pattern, label in _QUALITY_PATTERNS:
        if pattern.search(text) and label not in labels:
            labels.append(label)
    return tuple(labels)


def _content_code(detail_url: str) -> str:
    match = re.search(r"/(\d+)\.html$", urlparse(detail_url).path)
    return match.group(1) if match else hashlib.sha256(detail_url.encode("utf-8")).hexdigest()[:16]


def parse_latest_listing(
    html: str,
    *,
    page_url: str,
    rank_offset: int = 0,
) -> list[MovieListingCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[MovieListingCandidate] = []
    for table in soup.select("table.tbspan"):
        anchor = table.select_one("a.ulink[href]")
        if anchor is None:
            continue
        detail_url = urljoin(page_url, str(anchor["href"]))
        path = urlparse(detail_url).path
        if not path.startswith("/i/") or not path.endswith(".html"):
            continue
        listing_title = normalize_whitespace(
            str(anchor.get("title") or anchor.get_text(" ", strip=True))
        )
        if not listing_title:
            continue
        date_match = re.search(r"日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})", table.get_text(" ", strip=True))
        update_date = None
        if date_match:
            try:
                update_date = date.fromisoformat(date_match.group(1))
            except ValueError:
                update_date = None
        candidates.append(
            MovieListingCandidate(
                rank=rank_offset + len(candidates) + 1,
                detail_url=detail_url,
                source_item_key=path,
                content_code=_content_code(detail_url),
                listing_title=listing_title,
                update_date=update_date,
                recommended=False,
                highlight_labels=(),
                quality_tags=extract_quality_tags(listing_title),
            )
        )
    return candidates


def _normalized_field_line(value: str) -> str:
    value = value.replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def _field_match(line: str) -> tuple[str, str] | None:
    normalized = _normalized_field_line(line)
    if not normalized.startswith("◎"):
        return None
    body = normalized[1:].strip()
    for source_label, target_label in sorted(_FIELD_ALIASES.items(), key=lambda item: -len(item[0])):
        pattern = r"^" + r"\s*".join(re.escape(ch) for ch in source_label) + r"\s*[:：]?\s*(.*)$"
        match = re.match(pattern, body, re.I)
        if match:
            return target_label, normalize_whitespace(match.group(1))
    return None


def _metadata_lines(container: Tag) -> list[str]:
    fragment = BeautifulSoup(str(container), "html.parser")
    for marker in fragment.select(".player_list, #downlist, #downlist_info"):
        marker.decompose()
    for anchor in fragment.select("a[href]"):
        href = str(anchor.get("href") or "").strip().casefold()
        if href.startswith(("magnet:", "jianpian:", "thunder:", "ftp:", "ed2k:")):
            anchor.decompose()
        elif _cloud_provider(href) is not None:
            anchor.decompose()
    text = fragment.get_text("\n", strip=False)
    lines: list[str] = []
    for raw_line in text.splitlines():
        for part in re.split(r"(?=◎)", raw_line):
            cleaned = _normalized_field_line(part)
            if cleaned:
                lines.append(cleaned)
    return lines


def _metadata(container: Tag) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    current: str | None = None
    for line in _metadata_lines(container):
        if "【下载地址】" in line:
            break
        matched = _field_match(line)
        if matched is not None:
            current, value = matched
            result.setdefault(current, [])
            if value:
                result[current].append(value)
            continue
        if current is not None:
            result.setdefault(current, []).append(line)
    return result


def _first(values: list[str] | None) -> str | None:
    return values[0] if values else None


def _split_values(values: list[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    output: list[str] = []
    for value in values:
        for part in re.split(r"\s*/\s*|\s*／\s*|\s*,\s*|\s*，\s*", value):
            cleaned = normalize_whitespace(part)
            if cleaned and cleaned not in output:
                output.append(cleaned)
    return tuple(output)


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


def _title_from_heading(value: str) -> str:
    match = re.search(r"《([^》]+)》", value)
    return normalize_whitespace(match.group(1)) if match else normalize_whitespace(value)


def _cloud_provider(url: str) -> str | None:
    host = (urlparse(url).hostname or "").casefold()
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


def unwrap_jianpian_url(url: str) -> str | None:
    marker = "&path="
    index = url.casefold().find(marker)
    if not url.casefold().startswith("jianpian://") or index < 0:
        return None
    target = unquote(url[index + len(marker) :]).strip()
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https", "ftp"} or not parsed.hostname:
        return None
    return target


def _embedded_media_target(url: str) -> str | None:
    candidates = [url]
    if "$" in url:
        candidates.insert(0, url.rsplit("$", 1)[-1])
    for candidate in candidates:
        target = unquote(candidate).strip()
        parsed = urlparse(target)
        if parsed.scheme in {"http", "https", "ftp"} and parsed.hostname:
            return target
    return None


def direct_resource_kind(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    path = parsed.path.casefold()
    if path.endswith(".m3u8"):
        return "player", "m3u8"
    if parsed.scheme.casefold() == "ftp":
        return "download", "ftp"
    if path.endswith((".mp4", ".mkv", ".avi", ".ts", ".mov", ".wmv")):
        return "download", "direct"
    return "player", "direct"


def _resources(soup: BeautifulSoup, container: Tag) -> tuple[MovieResource, ...]:
    resources: list[MovieResource] = []
    seen: set[str] = set()
    nodes = list(container.select("a[href]"))
    downlist = soup.select_one("#downlist")
    if downlist is not None:
        nodes.extend(downlist.select("a[href]"))
    for anchor in nodes:
        raw_url = str(anchor.get("href") or "").strip()
        display_title = normalize_whitespace(anchor.get_text(" ", strip=True)) or raw_url
        lower = raw_url.casefold()
        if lower.startswith("magnet:?"):
            try:
                normalized, info_hash = normalize_magnet_uri(raw_url, fallback_dn=display_title)
            except Exception:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            resources.append(
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
        scheme = urlparse(raw_url).scheme.casefold()
        if scheme == "jianpian":
            target = unwrap_jianpian_url(raw_url)
            normalized_url = target or raw_url
            resource_type, provider_name = (
                direct_resource_kind(target) if target else ("player", "jianpian")
            )
            if normalized_url in seen:
                continue
            seen.add(normalized_url)
            resources.append(
                MovieResource(
                    resource_type=resource_type,
                    provider=provider_name,
                    resource_url=normalized_url,
                    info_hash=None,
                    display_title=display_title,
                    extraction_code=None,
                    quality_tags=extract_quality_tags(display_title),
                )
            )
            continue
        embedded = _embedded_media_target(raw_url)
        if embedded is not None and embedded != raw_url:
            resource_type, provider_name = direct_resource_kind(embedded)
            if embedded in seen:
                continue
            seen.add(embedded)
            resources.append(
                MovieResource(
                    resource_type=resource_type,
                    provider=provider_name,
                    resource_url=embedded,
                    info_hash=None,
                    display_title=display_title,
                    extraction_code=None,
                    quality_tags=extract_quality_tags(display_title),
                )
            )
            continue
        if scheme in {"thunder", "ftp", "ed2k"}:
            if raw_url in seen:
                continue
            seen.add(raw_url)
            resources.append(
                MovieResource(
                    resource_type="download",
                    provider=scheme,
                    resource_url=raw_url,
                    info_hash=None,
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
        resources.append(
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
    return tuple(resources)


def parse_movie_detail(
    html: str,
    *,
    candidate: MovieListingCandidate,
    raw_content: bytes | None = None,
) -> MovieDetail:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("#Zoom")
    if container is None:
        raise ValueError("DYTT detail page is missing #Zoom")
    metadata = _metadata(container)
    heading_node = soup.select_one("h1")
    heading = normalize_whitespace(
        heading_node.get_text(" ", strip=True) if heading_node else candidate.listing_title
    )
    title = _first(metadata.get("片名")) or _first(metadata.get("标题")) or _title_from_heading(heading)
    original_title = _first(metadata.get("译名"))
    year_text = _first(metadata.get("年代"))
    year_match = re.search(r"(19\d{2}|20\d{2})", year_text or candidate.listing_title)
    duration_text = _first(metadata.get("片长"))
    duration_match = re.search(r"(\d{1,4})\s*分钟", duration_text or "")
    douban_text = _first(metadata.get("豆瓣评分"))
    douban_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:/\s*10)?", douban_text or "")
    douban_rating = float(douban_match.group(1)) if douban_match else None
    if douban_rating is not None and douban_rating <= 0:
        douban_rating = None
    combined_text = " ".join(value for values in metadata.values() for value in values)
    imdb_match = re.search(r"tt\d+", combined_text, re.I)
    cover = None
    image = container.select_one("img[src]")
    if image is not None:
        cover = urljoin(candidate.detail_url, str(image["src"]))
    synopsis = normalize_whitespace(" ".join(metadata.get("简介") or ())) or None
    resources = _resources(soup, container)
    quality_tags = list(candidate.quality_tags)
    for resource in resources:
        for label in resource.quality_tags:
            if label not in quality_tags:
                quality_tags.append(label)
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
        release_date=_parse_date(_first(metadata.get("上映日期"))),
        duration_minutes=int(duration_match.group(1)) if duration_match else None,
        countries=_split_values(metadata.get("产地")),
        genres=_split_values(metadata.get("类别")),
        languages=_split_values(metadata.get("语言")),
        directors=_split_values(metadata.get("导演")),
        actors=_split_values(metadata.get("演员")),
        imdb_id=imdb_match.group(0).lower() if imdb_match else None,
        douban_rating=douban_rating,
        douban_rating_text=douban_text,
        douban_url=_first(metadata.get("豆瓣链接")),
        cover_source_url=cover,
        synopsis=synopsis,
        recommended=candidate.recommended,
        highlight_labels=candidate.highlight_labels,
        quality_tags=tuple(quality_tags),
        parser_version=PARSER_VERSION,
        raw_document_hash=raw_hash,
        resources=resources,
    )
