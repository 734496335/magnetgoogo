"""Pure parsers for MJF latest-series pages."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import date, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate, MovieResource
from magnet.resource_index.normalize.magnets import normalize_magnet_uri
from magnet.resource_index.normalize.text import normalize_whitespace

SOURCE_ID = "mjf-series"
ORIGIN = "https://www.mjf2020.com"
PARSER_VERSION = "mjf-series-parser/1.1.0"

_UK_NETWORK_PREFIXES = (
    "bbc",
    "itv",
    "channel 4",
    "channel 5",
    "sky",
    "britbox",
    "stv",
    "e4",
    "itvx",
    "uktv",
)

_QUALITY_PATTERNS = (
    (re.compile(r"(?i)(?:2160p|4k)"), "4K"),
    (re.compile(r"(?i)1080p"), "1080p"),
    (re.compile(r"(?i)720p"), "720p"),
    (re.compile(r"(?i)HDR"), "HDR"),
    (re.compile(r"(?i)(?:DV|Dolby Vision|杜比视界)"), "杜比视界"),
)


def extract_quality_tags(*values: str | None) -> tuple[str, ...]:
    text = " ".join(value for value in values if value)
    output: list[str] = []
    for pattern, label in _QUALITY_PATTERNS:
        if pattern.search(text) and label not in output:
            output.append(label)
    return tuple(output)


def _content_code(detail_url: str) -> str:
    match = re.search(r"/jianjie/(\d+)\.html$", urlparse(detail_url).path)
    return match.group(1) if match else hashlib.sha256(detail_url.encode("utf-8")).hexdigest()[:16]


def _series_title(value: str) -> str:
    return normalize_whitespace(re.sub(r"\s*\([^()]+\)\s*$", "", value))


def _relative_date(value: str, *, reference_date: date) -> date | None:
    text = normalize_whitespace(value)
    if not text:
        return None
    if any(marker in text for marker in ("刚刚", "分钟前", "小时前", "今天")):
        return reference_date
    if "昨天" in text:
        return reference_date - timedelta(days=1)
    match = re.search(r"(\d+)\s*天前", text)
    if match:
        return reference_date - timedelta(days=int(match.group(1)))
    match = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def _season_number(value: str) -> int | None:
    values = [int(item) for item in re.findall(r"第\s*(\d{1,2})\s*季", value)]
    values.extend(int(item) for item in re.findall(r"(?i)\bS(\d{1,2})(?:E\d+)?\b", value))
    return max(values) if values else None


def _episode_number(value: str) -> int | None:
    values = [int(item) for item in re.findall(r"第\s*0*(\d{1,4})\s*集", value)]
    values.extend(int(item) for item in re.findall(r"(?i)\bS\d{1,2}E0*(\d{1,4})\b", value))
    return max(values) if values else None


def parse_latest_listing(
    html: str,
    *,
    page_url: str,
    reference_date: date,
    rank_offset: int = 0,
) -> list[MovieListingCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    page_origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    output: list[MovieListingCandidate] = []
    seen: set[str] = set()
    for row in soup.select("li.list-group-item"):
        anchor = row.select_one('a[href*="/jianjie/"]')
        if anchor is None:
            continue
        detail_url = urljoin(page_url, str(anchor.get("href") or ""))
        path = urlparse(detail_url).path
        if not re.fullmatch(r"/jianjie/\d+\.html", path) or detail_url in seen:
            continue
        seen.add(detail_url)
        title = normalize_whitespace(str(anchor.get("title") or anchor.get_text(" ", strip=True)))
        if not title:
            continue
        row_text = normalize_whitespace(row.get_text(" ", strip=True))
        update_match = re.search(r"更新时间\s*[:：]\s*(.+)$", row_text)
        update_status = normalize_whitespace(update_match.group(1)) if update_match else None
        output.append(
            MovieListingCandidate(
                rank=rank_offset + len(output) + 1,
                detail_url=detail_url,
                source_item_key=path,
                content_code=_content_code(detail_url),
                listing_title=title,
                update_date=_relative_date(update_status or "", reference_date=reference_date),
                recommended=False,
                highlight_labels=(),
                quality_tags=extract_quality_tags(title),
                content_kind="series",
                series_title=_series_title(title),
                season_number=_season_number(title),
                episode_number=_episode_number(title),
                episode_label=None,
                update_status=update_status,
                brand_id="mjf",
                endpoint_origin=page_origin,
            )
        )
    return output


def latest_resource_page_url(html: str, *, page_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select('a[href*="/bt/"]'):
        target = urljoin(page_url, str(anchor.get("href") or ""))
        if re.fullmatch(r"/bt/\d+\.html", urlparse(target).path):
            return target
    return None


def _field(text: str, label: str) -> str | None:
    pattern = rf"(?:^|\n)\s*{re.escape(label)}\s*[:：]\s*(.*?)\s*(?=\n|$)"
    match = re.search(pattern, text, re.I)
    return normalize_whitespace(match.group(1)) if match else None


def _app_country_from_network(value: str | None) -> str:
    network = normalize_whitespace(value or "").casefold()
    if any(network.startswith(prefix) for prefix in _UK_NETWORK_PREFIXES):
        return "英国"
    return "美国"


def _split_values(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    output: list[str] = []
    for item in re.split(r"\s*/\s*|\s*[，,]\s*", value):
        cleaned = normalize_whitespace(item)
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return tuple(output)


def _date(value: str | None) -> date | None:
    if not value:
        return None
    match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", value)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def parse_resource_page(html: str) -> MovieResource | None:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("textarea#link-input")
    raw = normalize_whitespace(node.get_text() if node is not None else "")
    if not raw.startswith("magnet:?"):
        match = re.search(r"magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\s<'\"]*", html, re.I)
        raw = match.group(0) if match else ""
    if not raw:
        return None
    heading = soup.select_one("h1")
    title = normalize_whitespace(heading.get_text(" ", strip=True) if heading is not None else raw)
    try:
        magnet, info_hash = normalize_magnet_uri(raw, fallback_dn=title)
    except Exception:
        return None
    return MovieResource(
        resource_type="magnet",
        provider="magnet",
        resource_url=magnet,
        info_hash=info_hash,
        display_title=title,
        extraction_code=None,
        quality_tags=extract_quality_tags(title),
    )


def parse_series_detail(
    html: str,
    *,
    candidate: MovieListingCandidate,
    resource_html: str,
    raw_content: bytes | None = None,
) -> MovieDetail:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    heading = soup.select_one("h1")
    title = normalize_whitespace(
        heading.get_text(" ", strip=True) if heading is not None else candidate.series_title or candidate.listing_title
    )
    english_title = _field(text, "英文名字")
    aliases = _field(text, "别名")
    imdb_id = _field(text, "IMDB")
    if imdb_id and not re.fullmatch(r"tt\d+", imdb_id, re.I):
        match = re.search(r"tt\d+", imdb_id, re.I)
        imdb_id = match.group(0) if match else None
    status = _field(text, "状态") or candidate.update_status
    network = _field(text, "电视台")
    release_date = _date(_field(text, "首播"))
    first_bt = soup.select_one('a[href*="/bt/"]')
    episode_label = normalize_whitespace(first_bt.get_text(" ", strip=True)) if first_bt is not None else status
    season_number = _season_number(" ".join(value for value in (status, episode_label, candidate.listing_title) if value))
    episode_number = _episode_number(" ".join(value for value in (status, episode_label, candidate.listing_title) if value))
    meta_image = soup.select_one('meta[property="og:image"][content]')
    image = str(meta_image.get("content") or "").strip() if meta_image is not None else ""
    resource = parse_resource_page(resource_html)
    resources = (resource,) if resource is not None else ()
    quality_tags = list(candidate.quality_tags)
    if resource is not None:
        for label in resource.quality_tags:
            if label not in quality_tags:
                quality_tags.append(label)
    description = soup.select_one('meta[name="description"][content]')
    synopsis = normalize_whitespace(str(description.get("content") or "")) if description is not None else None
    raw_hash = hashlib.sha256(raw_content if raw_content is not None else html.encode("utf-8")).hexdigest()
    return MovieDetail(
        source_id=SOURCE_ID,
        source_item_key=candidate.source_item_key,
        content_code=candidate.content_code,
        detail_url=candidate.detail_url,
        listing_title=candidate.listing_title,
        title=title,
        original_title=english_title or aliases,
        year=release_date.year if release_date is not None else None,
        update_date=candidate.update_date,
        release_date=release_date,
        duration_minutes=None,
        countries=(_app_country_from_network(network),),
        genres=_split_values(_field(text, "类型")),
        languages=(),
        directors=(),
        actors=(),
        imdb_id=imdb_id.lower() if imdb_id else None,
        douban_rating=None,
        douban_rating_text=None,
        douban_url=None,
        cover_source_url=image or None,
        synopsis=synopsis,
        recommended=False,
        highlight_labels=(),
        quality_tags=tuple(quality_tags),
        parser_version=PARSER_VERSION,
        raw_document_hash=raw_hash,
        resources=resources,
        content_kind="series",
        series_title=title,
        season_number=season_number or candidate.season_number,
        episode_number=episode_number or candidate.episode_number,
        episode_label=episode_label,
        update_status=status,
        brand_id="mjf",
        endpoint_origin=candidate.endpoint_origin or ORIGIN,
    )
