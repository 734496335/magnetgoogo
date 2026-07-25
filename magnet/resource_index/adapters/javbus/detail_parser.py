"""JavBus detail page parser."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from magnet.resource_index.adapters.javbus import selectors as sel
from magnet.resource_index.config import RISK_MANUAL_REVIEW
from magnet.resource_index.domain.enums import ContentType, MediaStatus, MediaType, PersonRole
from magnet.resource_index.domain.identity import (
    content_id_for,
    media_id_for,
    person_id_for,
    tag_id_for,
)
from magnet.resource_index.domain.models import (
    ContentItem,
    MediaAssetRef,
    ParseProvenance,
    ParseWarning,
    ParsedContentBundle,
    PersonRef,
    RawDocumentEnvelope,
    ResourceRequestDescriptor,
    TagRef,
)
from magnet.resource_index.errors import (
    ACCESS_CHALLENGE,
    AGE_GATE_PAGE,
    CONTENT_CODE_MISSING,
    DETAIL_DOM_DRIFT,
    TITLE_MISSING,
    ParseError,
    ResourceIndexError,
)
from magnet.resource_index.normalize.content_code import normalize_content_code
from magnet.resource_index.normalize.dates import parse_date, parse_duration_minutes
from magnet.resource_index.normalize.text import normalize_person_name, normalize_title, normalize_whitespace
from magnet.resource_index.normalize.urls import absolutize, external_key_from_path, path_key


def _is_blocked(body: str) -> str | None:
    lower = body.lower()
    for marker in sel.AGE_GATE_MARKERS:
        if marker.lower() in lower or marker in body:
            return AGE_GATE_PAGE
    for marker in sel.CHALLENGE_MARKERS:
        if marker in lower:
            return ACCESS_CHALLENGE
    return None


def _label_matches(header_text: str, keys: tuple[str, ...]) -> bool:
    text = normalize_whitespace(header_text).rstrip("：:").strip()
    for key in keys:
        if text == key or text.startswith(key):
            return True
    return False


def _field_value_from_p(p: Tag) -> str:
    header = p.select_one("span.header")
    if header is not None:
        header.extract()
    return normalize_whitespace(p.get_text(" ", strip=True))


def _extract_labeled_fields(soup: BeautifulSoup) -> dict[str, Any]:
    result: dict[str, Any] = {}
    info = soup.select_one(sel.DETAIL_INFO) or soup
    for p in info.select("p"):
        header = p.select_one("span.header")
        if header is None:
            continue
        header_text = header.get_text(" ", strip=True)
        if _label_matches(header_text, sel.FIELD_LABELS["content_code"]):
            # Prefer red span / first non-header text
            code_span = p.select_one("span[style], span")
            raw = ""
            if code_span is not None and "header" not in (code_span.get("class") or []):
                raw = normalize_whitespace(code_span.get_text())
            if not raw:
                raw = _field_value_from_p(p)
            result["raw_content_code"] = raw
        elif _label_matches(header_text, sel.FIELD_LABELS["release_date"]):
            result["release_date_raw"] = _field_value_from_p(p)
        elif _label_matches(header_text, sel.FIELD_LABELS["duration"]):
            result["duration_raw"] = _field_value_from_p(p)
        elif _label_matches(header_text, sel.FIELD_LABELS["director"]):
            links = p.select("a")
            result["directors"] = [
                (normalize_person_name(a.get_text()), absolutize(sel.ORIGIN, a.get("href")))
                for a in links
            ]
        elif _label_matches(header_text, sel.FIELD_LABELS["maker"]):
            a = p.select_one("a")
            result["maker"] = normalize_whitespace(a.get_text()) if a else _field_value_from_p(p)
        elif _label_matches(header_text, sel.FIELD_LABELS["publisher"]):
            a = p.select_one("a")
            result["publisher"] = normalize_whitespace(a.get_text()) if a else _field_value_from_p(p)
        elif _label_matches(header_text, sel.FIELD_LABELS["series"]):
            a = p.select_one("a")
            result["series"] = normalize_whitespace(a.get_text()) if a else _field_value_from_p(p)
        elif _label_matches(header_text, sel.FIELD_LABELS["genre"]):
            tags = []
            for a in p.select("a"):
                tags.append((normalize_whitespace(a.get_text()), absolutize(sel.ORIGIN, a.get("href"))))
            result["tags"] = tags
        elif _label_matches(header_text, sel.FIELD_LABELS["actors"]):
            actors = []
            for a in p.select("a"):
                actors.append(
                    (normalize_person_name(a.get_text()), absolutize(sel.ORIGIN, a.get("href")))
                )
            result["actors"] = actors
    return result


def extract_gid_uc(body: str) -> tuple[str | None, str | None]:
    gid_m = re.search(sel.GID_RE, body)
    uc_m = re.search(sel.UC_RE, body)
    gid = gid_m.group(1) if gid_m else None
    uc = uc_m.group(1) if uc_m else None
    return gid, uc


def parse_detail(document: RawDocumentEnvelope) -> ParsedContentBundle:
    blocked = _is_blocked(document.body)
    if blocked == AGE_GATE_PAGE:
        raise ParseError(AGE_GATE_PAGE, "age verification page", {})
    if blocked == ACCESS_CHALLENGE:
        raise ParseError(ACCESS_CHALLENGE, "access challenge page", {})

    soup = BeautifulSoup(document.body, "html.parser")
    title_el = soup.select_one(sel.DETAIL_TITLE) or soup.select_one("title")
    if title_el is None:
        raise ParseError(DETAIL_DOM_DRIFT, "title element missing", {})
    raw_title = normalize_whitespace(title_el.get_text(" ", strip=True))
    if not raw_title:
        raise ParseError(TITLE_MISSING, "title empty", {})

    fields = _extract_labeled_fields(soup)
    raw_code = fields.get("raw_content_code")
    if not raw_code:
        # path fallback
        path = path_key(document.source_url)
        tail = path.rsplit("/", 1)[-1]
        if normalize_content_code(tail):
            raw_code = tail
        else:
            m = re.match(r"^([A-Za-z0-9]+[-_][0-9A-Za-z]+)", raw_title)
            if m:
                raw_code = m.group(1)
    if not raw_code:
        raise ParseError(CONTENT_CODE_MISSING, "content code not found", {})

    content_code = normalize_content_code(raw_code)
    if not content_code:
        raise ParseError(CONTENT_CODE_MISSING, "content code invalid", {"raw": raw_code})

    title = normalize_title(raw_title, content_code=content_code)
    if not title:
        raise ParseError(TITLE_MISSING, "title empty after normalize", {})

    warnings: list[ParseWarning] = []
    release_date = None
    if fields.get("release_date_raw"):
        try:
            release_date = parse_date(fields["release_date_raw"])
        except ResourceIndexError as exc:
            warnings.append(
                ParseWarning(exc.error_code, exc.message, {"raw": fields["release_date_raw"]})
            )
    duration = None
    if fields.get("duration_raw"):
        try:
            duration = parse_duration_minutes(fields["duration_raw"])
        except ResourceIndexError as exc:
            warnings.append(
                ParseWarning(exc.error_code, exc.message, {"raw": fields["duration_raw"]})
            )

    cover_url = None
    cover_a = soup.select_one(sel.DETAIL_COVER)
    if cover_a is not None:
        cover_url = absolutize(document.source_url, cover_a.get("href"))
        if not cover_url:
            img = cover_a.find("img")
            if img is not None:
                cover_url = absolutize(document.source_url, img.get("src"))

    source_item_key = path_key(document.source_url)
    content_id = content_id_for(ContentType.ADULT_VIDEO, content_code)

    # Fallback: site often puts genres/actors outside labeled <p> blocks
    if not fields.get("tags"):
        tags_fb = []
        for a in soup.select("span.genre a, .genre a"):
            href = absolutize(document.source_url, a.get("href"))
            name = normalize_whitespace(a.get_text())
            if name and href and "/genre/" in (href or ""):
                tags_fb.append((name, href))
        if tags_fb:
            fields["tags"] = tags_fb
    if not fields.get("actors"):
        actors_fb = []
        for a in soup.select('a[href*="/star/"]'):
            href = absolutize(document.source_url, a.get("href"))
            name = normalize_person_name(a.get_text())
            if name and href:
                actors_fb.append((name, href))
        if actors_fb:
            fields["actors"] = actors_fb

    people: list[PersonRef] = []
    seen_people: set[tuple[str, str]] = set()
    sort_i = 0

    def _add_person(
        name: str,
        url: str | None,
        role: PersonRole,
        slug_prefixes: tuple[str, ...],
    ) -> None:
        nonlocal sort_i
        if not name:
            return
        slug = external_key_from_path(url or "", slug_prefixes) if url else None
        pid = person_id_for(slug=slug, display_name=name, source_prefix=sel.SOURCE_ID)
        key = (pid, role.value)
        if key in seen_people:
            return
        seen_people.add(key)
        people.append(
            PersonRef(
                person_id=pid,
                display_name=name,
                role=role,
                source_profile_url=url,
                source_external_key=slug,
                sort_order=sort_i,
            )
        )
        sort_i += 1

    for name, url in fields.get("directors") or []:
        _add_person(name, url, PersonRole.DIRECTOR, ("/director", "/directors"))
    for name, url in fields.get("actors") or []:
        _add_person(name, url, PersonRole.ACTOR, ("/star", "/actress", "/actor"))

    tags: list[TagRef] = []
    seen_tags: set[str] = set()
    for name, url in fields.get("tags") or []:
        if not name:
            continue
        key = external_key_from_path(url or "", ("/genre", "/genres", "/tag")) if url else None
        tid = tag_id_for(external_key=key, display_name=name, source_prefix=sel.SOURCE_ID)
        if tid in seen_tags:
            continue
        seen_tags.add(tid)
        tags.append(
            TagRef(
                tag_id=tid,
                display_name=name,
                source_url=url,
                source_external_key=key,
            )
        )

    media: list[MediaAssetRef] = []
    if cover_url:
        media.append(
            MediaAssetRef(
                media_id=media_id_for(content_id, MediaType.COVER, cover_url),
                media_type=MediaType.COVER,
                source_url=cover_url,
                stored_url=None,
                content_hash=None,
                width=None,
                height=None,
                adult=True,
                status=MediaStatus.REMOTE_REFERENCE_ONLY,
            )
        )
    for a in soup.select(sel.DETAIL_SAMPLE):
        sample = absolutize(document.source_url, a.get("href"))
        if not sample:
            continue
        media.append(
            MediaAssetRef(
                media_id=media_id_for(content_id, MediaType.SAMPLE, sample),
                media_type=MediaType.SAMPLE,
                source_url=sample,
                stored_url=None,
                content_hash=None,
                width=None,
                height=None,
                adult=True,
                status=MediaStatus.REMOTE_REFERENCE_ONLY,
            )
        )

    gid, uc = extract_gid_uc(document.body)
    internal: dict[str, Any] = {"gid": gid, "uc": uc, "risk_status": RISK_MANUAL_REVIEW}
    if gid is None:
        warnings.append(
            ParseWarning("RESOURCE_DESCRIPTOR_MISSING", "gid not found on detail page", {})
        )
    if uc is None:
        warnings.append(
            ParseWarning("RESOURCE_DESCRIPTOR_MISSING", "uc missing; default 0 may apply", {})
        )
        internal["uc"] = "0"

    content = ContentItem(
        content_id=content_id,
        content_type=ContentType.ADULT_VIDEO,
        content_code=content_code,
        raw_content_code=raw_code,
        title=title,
        original_title=raw_title if raw_title != title else None,
        release_date=release_date,
        duration_minutes=duration,
        maker_name=fields.get("maker"),
        publisher_name=fields.get("publisher"),
        label_name=None,
        series_name=fields.get("series"),
        cover_source_url=cover_url,
        detail_url=document.source_url,
        adult=True,
        source_id=sel.SOURCE_ID,
        source_item_key=source_item_key,
        parser_version=sel.PARSER_VERSION,
    )

    return ParsedContentBundle(
        content=content,
        aliases=(),
        people=tuple(people),
        tags=tuple(tags),
        media=tuple(media),
        resources=(),
        warnings=tuple(warnings),
        provenance=ParseProvenance(
            source_id=sel.SOURCE_ID,
            source_item_key=source_item_key,
            detail_url=document.source_url,
            parser_version=sel.PARSER_VERSION,
            document_sha256=document.sha256,
            internal=internal,
        ),
    )


def derive_resource_request(document: RawDocumentEnvelope) -> ResourceRequestDescriptor | None:
    gid, uc = extract_gid_uc(document.body)
    if not gid:
        return None
    if uc is None:
        uc = "0"
    return ResourceRequestDescriptor(
        method="GET",
        url_template=f"{sel.ORIGIN}/ajax/uncledatoolsbyajax.php?gid={{gid}}&lang=zh&uc={{uc}}&floor={{floor}}",
        headers={"Referer": document.source_url},
        query={"gid": gid, "uc": uc, "lang": "zh"},
        referer=document.source_url,
        notes="floor is random client-side; parser does not generate it",
    )
