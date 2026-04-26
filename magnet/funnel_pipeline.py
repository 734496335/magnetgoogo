#!/usr/bin/env python3
"""
Funnel pipeline: faster discovery of reachable working magnet sources (CN no-proxy).

Stages:
- Stage0: reachability probe (cheap)
- Stage1: homepage signals (keywords/form/parking)
- Stage2: HTTP search (form-infer first, then small fallback template set)
- Stage3: optional browser verify (selenium) with strict budget (only for high-potential)
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from threading import Semaphore
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from funnel_config import FunnelConfig
from funnel_report_summary import print_summary, write_summary
from funnel_sources import load_sources, save_sources, upsert_rule_from_green_verdict


MAGNET_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(MAGNET_DIR)
DEFAULT_SOURCES_PATH = os.path.join(ROOT_DIR, "sources.json")
DEFAULT_VALIDATE_PATH = os.path.join(ROOT_DIR, "validate_enum.py")
LOG_PATH = os.path.join(MAGNET_DIR, "run.log")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:[A-Za-z0-9]{32,40}", re.I)
HASH_RE = re.compile(r"\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b")
BTIH_RE = re.compile(r"btih[:=]([A-Za-z2-7]{32}|[0-9A-Fa-f]{40})", re.I)
BASE32_HASH_RE = re.compile(r"\b[A-Z2-7]{32}\b")
DETAIL_PATH_RE = re.compile(r"/(torrent|view|info|detail|show|movie|resource|hash|files?)/", re.I)
DETAIL_SKIP_RE = re.compile(r"/(favorites|tags?|category|categories|nav|sites?|about|contact|help|policy|terms|login|register|user|forum|topics?)/", re.I)

PARKING_SIGS = (
    "domain for sale",
    "buy this domain",
    "hugedomains",
    "sedo.com",
    "afternic",
    "dan.com",
    "parking",
    "this domain has expired",
    "domain has expired",
)

MAGNET_KWS = ("magnet:", "btih", "torrent", "磁力", "种子", "bt搜索", "bt search")
META_MAGNET_KWS = ("torrent", "magnet", "bt", "btsow", "nyaa", "kitty", "搜", "种子", "磁力", "cili")


@dataclass
class SearchCandidate:
    method: str
    template: str
    query_param_name: str = ""
    fields: Dict[str, str] = None


@dataclass
class CandidateInput:
    origin: str
    name: str = ""
    reason: str = ""
    desc: str = ""
    brand: str = ""


@dataclass
class SiteSignals:
    origin: str
    final_url: str = ""
    http_status: int | None = None
    html_len: int = 0
    has_keywords: bool = False
    has_form: bool = False
    is_parking: bool = False
    note: str = ""


@dataclass
class Evidence:
    magnets: List[Dict[str, str]]
    hashes: List[str]


@dataclass
class SiteVerdict:
    origin: str
    status: str
    status_detail: str
    note: str = ""
    chosen_template: str = ""
    chosen_query: str = ""
    magnets_found: int = 0
    sample_title: str = ""
    last_checked_at: str = ""


def normalize_origin(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    p = urlparse(url)
    if not p.netloc:
        return ""
    scheme = p.scheme if p.scheme in ("http", "https") else "http"
    return f"{scheme}://{p.netloc}"


def decode_btih_hash(raw: str) -> str:
    raw = urllib.parse.unquote((raw or "").strip()).upper()
    if not raw:
        return ""
    if re.fullmatch(r"[0-9A-F]{40}", raw):
        return raw
    if re.fullmatch(r"[A-Z2-7]{32}", raw):
        try:
            return base64.b32decode(raw).hex().upper()
        except Exception:
            return ""
    return ""


def build_headers(cfg: FunnelConfig) -> Dict[str, str]:
    return {
        "User-Agent": cfg.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        "Connection": "keep-alive",
    }


def http_get(session: requests.Session, url: str, timeout_s: float, headers: Dict[str, str]) -> Optional[requests.Response]:
    try:
        return session.get(url, timeout=timeout_s, headers=headers, allow_redirects=True)
    except requests.RequestException:
        return None


def stage0_probe(origin: str, cfg: FunnelConfig) -> Tuple[str, Optional[requests.Response], float, str]:
    t0 = time.time()
    headers = build_headers(cfg)
    session = requests.Session()
    attempts = max(1, int(cfg.budgets.stage0_retries) + 1)
    last_resp: Optional[requests.Response] = None
    last_verdict = "unreachable"

    for attempt in range(attempts):
        resp = http_get(session, origin, cfg.budgets.stage0_timeout_s, headers)
        last_resp = resp
        if not resp:
            last_verdict = "unreachable"
        elif resp.status_code == 404:
            dt = time.time() - t0
            return origin, resp, dt, "404"
        elif resp.status_code in (403, 503):
            lower = (resp.text or "")[:3000].lower()
            if "cloudflare" in lower or "just a moment" in lower or "challenge-platform" in lower:
                dt = time.time() - t0
                return origin, resp, dt, "waf"
            last_verdict = "unreachable"
        elif resp.status_code >= 500:
            last_verdict = "unreachable"
        else:
            dt = time.time() - t0
            return origin, resp, dt, "reachable"

        if attempt + 1 < attempts:
            time.sleep(cfg.budgets.stage0_retry_backoff_s * (attempt + 1))

    dt = time.time() - t0
    return origin, last_resp, dt, last_verdict


def stage1_signals(origin: str, resp: requests.Response, cfg: FunnelConfig) -> SiteSignals:
    html = resp.text or ""
    lower = html[:20000].lower()
    has_kw = any(kw in lower for kw in MAGNET_KWS)
    is_parking = any(sig in lower for sig in PARKING_SIGS)
    has_form = "<form" in lower and ("search" in lower or "q=" in lower or "keyword" in lower)
    return SiteSignals(
        origin=origin,
        final_url=resp.url or origin,
        http_status=resp.status_code,
        html_len=len(html),
        has_keywords=has_kw,
        has_form=has_form,
        is_parking=is_parking,
        note="",
    )


def candidate_has_magnet_signal(candidate: CandidateInput) -> bool:
    haystack = " ".join(
        part.strip().lower()
        for part in (candidate.name, candidate.reason, candidate.desc, candidate.brand)
        if part and part.strip()
    )
    if not haystack:
        return False
    return any(kw in haystack for kw in META_MAGNET_KWS)


def extract_evidence(html: str) -> Evidence:
    soup = BeautifulSoup(html or "", "lxml")
    magnets: List[Dict[str, str]] = []
    seen_hash = set()
    hashes: List[str] = []

    def push_magnet(raw: str, title: str = "") -> None:
        if not raw:
            return
        raw = urllib.parse.unquote(raw)
        m = MAGNET_RE.search(raw)
        if not m:
            return
        ih = re.search(r"btih:([A-Za-z2-7]{32}|[0-9A-Fa-f]{40})", raw, re.I)
        hh = ""
        if ih:
            hh = decode_btih_hash(ih.group(1))
            if not hh:
                return
            if hh in seen_hash:
                return
            seen_hash.add(hh)
            raw = f"magnet:?xt=urn:btih:{hh}"
        magnets.append({"title": title[:120], "magnet": raw[:200]})

    def push_hash(raw: str) -> None:
        hh = decode_btih_hash(raw)
        if not hh:
            return
        if hh in seen_hash:
            return
        seen_hash.add(hh)
        hashes.append(hh)

    for a in soup.find_all("a", href=lambda h: h and h.startswith("magnet:")):
        href = a.get("href", "")
        title = a.get_text(strip=True)[:120]
        push_magnet(href, title)

    if not magnets:
        for tag in soup.find_all(True):
            for attr_name, attr_value in list(tag.attrs.items()):
                values = attr_value if isinstance(attr_value, list) else [attr_value]
                for value in values:
                    if not isinstance(value, str):
                        continue
                    if "magnet:" in value or "btih" in value.lower():
                        push_magnet(value, tag.get_text(" ", strip=True))
                    for m in BTIH_RE.finditer(value):
                        push_hash(m.group(1))
                    for m in HASH_RE.finditer(value):
                        push_hash(m.group(0))
                    for m in BASE32_HASH_RE.finditer(value.upper()):
                        push_hash(m.group(0))

    if not magnets:
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            m = HASH_RE.search(href)
            if not m:
                btih = BTIH_RE.search(href)
                if btih:
                    push_hash(btih.group(1))
                continue
            push_hash(m.group(0))
    if not hashes and not magnets:
        text = soup.get_text(" ", strip=True)
        for m in HASH_RE.finditer(text):
            push_hash(m.group(0))
            if len(hashes) >= 50:
                break
    if not hashes and not magnets:
        text = urllib.parse.unquote(soup.get_text(" ", strip=True))
        for m in BTIH_RE.finditer(text):
            push_hash(m.group(1))
        for m in BASE32_HASH_RE.finditer(text.upper()):
            push_hash(m.group(0))
    if not magnets:
        for script in soup.find_all("script"):
            script_text = script.string or script.get_text(" ", strip=True)
            if not script_text:
                continue
            push_magnet(script_text)
            for m in BTIH_RE.finditer(script_text):
                push_hash(m.group(1))
            for m in HASH_RE.finditer(script_text):
                push_hash(m.group(0))

    return Evidence(magnets=magnets, hashes=hashes)


def extract_detail_urls(html: str, base_url: str, limit: int = 6) -> List[str]:
    soup = BeautifulSoup(html or "", "lxml")
    scored: List[Tuple[int, str]] = []
    seen = set()
    base_netloc = urlparse(base_url).netloc.lower()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = a.get_text(" ", strip=True).strip().lower()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        if abs_url in seen or parsed.netloc.lower() != base_netloc:
            continue
        if DETAIL_SKIP_RE.search(href) or DETAIL_SKIP_RE.search(abs_url):
            continue

        score = 0
        if DETAIL_PATH_RE.search(href) or DETAIL_PATH_RE.search(abs_url):
            score += 5
        if any(token in text for token in ("详情", "detail", "view", "查看", "资源", "打开", "进入")):
            score += 3
        if HASH_RE.search(href) or HASH_RE.search(abs_url):
            score += 4
        if re.search(r"/\d+(\.html)?$", parsed.path):
            score += 2
        if text and 4 <= len(text) <= 120:
            score += 1
        if score <= 0:
            query_keys = {k.lower() for k in urllib.parse.parse_qs(parsed.query).keys()}
            if query_keys.intersection({"id", "hash", "cid", "vid", "tid", "key"}):
                score += 3
        if score <= 0:
            continue

        seen.add(abs_url)
        scored.append((score, abs_url))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _, url in scored[:limit]]


def extract_interstitial_urls(html: str, base_url: str, limit: int = 3) -> List[str]:
    soup = BeautifulSoup(html or "", "lxml")
    urls: List[str] = []
    seen = set()
    base_netloc = urlparse(base_url).netloc.lower()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = a.get_text(" ", strip=True).strip().lower()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        abs_url = urljoin(base_url, href)
        if abs_url in seen:
            continue
        parsed = urlparse(abs_url)
        if parsed.netloc.lower() != base_netloc:
            continue
        if any(token in text for token in ("click here", "enter", "继续", "进入", "跳转", "go")) or "tr_uuid=" in abs_url:
            seen.add(abs_url)
            urls.append(abs_url)
        if len(urls) >= limit:
            break
    return urls


def follow_interstitial_http(
    session: requests.Session,
    html: str,
    base_url: str,
    cfg: FunnelConfig,
    headers: Dict[str, str],
    deadline: float | None = None,
) -> Tuple[Evidence, List[Dict[str, Any]]]:
    attempts: List[Dict[str, Any]] = []
    for jump_url in extract_interstitial_urls(html, base_url):
        if deadline is not None and time.time() >= deadline:
            break
        t0 = time.time()
        status = None
        try:
            resp = session.get(jump_url, timeout=cfg.budgets.stage2_timeout_s, headers=headers, allow_redirects=True)
            status = resp.status_code
            final_html = resp.text or ""
            ev = extract_evidence(final_html)
            attempts.append(
                {
                    "jump_url": jump_url,
                    "final_url": resp.url,
                    "http_status": status,
                    "dt_s": round(time.time() - t0, 2),
                    "magnets_found": len(ev.magnets),
                    "hashes_found": len(ev.hashes),
                }
            )
            if ev.magnets or len(ev.hashes) >= cfg.evidence.min_hashes_to_green:
                return ev, attempts
        except requests.RequestException:
            attempts.append({"jump_url": jump_url, "http_status": status, "dt_s": round(time.time() - t0, 2), "error": "request_exception"})
    return Evidence(magnets=[], hashes=[]), attempts


def follow_detail_evidence_http(
    session: requests.Session,
    html: str,
    base_url: str,
    cfg: FunnelConfig,
    headers: Dict[str, str],
    deadline: float | None = None,
) -> Tuple[Evidence, List[Dict[str, Any]]]:
    attempts: List[Dict[str, Any]] = []
    for detail_url in extract_detail_urls(html, base_url):
        if deadline is not None and time.time() >= deadline:
            break
        t0 = time.time()
        status = None
        try:
            resp = session.get(detail_url, timeout=cfg.budgets.stage2_timeout_s, headers=headers, allow_redirects=True)
            status = resp.status_code
            if status == 200 and len(resp.text or "") >= 200:
                ev = extract_evidence(resp.text)
                attempts.append(
                    {
                        "detail_url": detail_url,
                        "http_status": status,
                        "dt_s": round(time.time() - t0, 2),
                        "magnets_found": len(ev.magnets),
                        "hashes_found": len(ev.hashes),
                    }
                )
                if ev.magnets or len(ev.hashes) >= cfg.evidence.min_hashes_to_green:
                    return ev, attempts
            else:
                attempts.append({"detail_url": detail_url, "http_status": status, "dt_s": round(time.time() - t0, 2)})
        except requests.RequestException:
            attempts.append({"detail_url": detail_url, "http_status": status, "dt_s": round(time.time() - t0, 2), "error": "request_exception"})
    return Evidence(magnets=[], hashes=[]), attempts


def infer_search_templates_from_forms(origin: str, html: str, cfg: FunnelConfig) -> List[SearchCandidate]:
    soup = BeautifulSoup(html or "", "lxml")
    candidates: List[SearchCandidate] = []
    for form in soup.find_all("form"):
        method = (form.get("method") or "get").strip().upper()
        action = (form.get("action") or "").strip()
        inputs = form.find_all("input")

        fields: Dict[str, str] = {}
        query_param_name = ""

        # Collect all inputs to build a full form body/query
        for inp in inputs:
            itype = (inp.get("type") or "text").lower()
            name = (inp.get("name") or "").strip()
            val = (inp.get("value") or "").strip()
            if not name:
                continue

            # Identify the primary search input
            if not query_param_name:
                if itype in ("text", "search"):
                    query_param_name = name
                elif not itype and name.lower() in ("q", "s", "wd", "keyword", "query"):
                    query_param_name = name

            fields[name] = val

        if not query_param_name:
            # Fallback to the first input if no obvious search field found
            if fields:
                query_param_name = list(fields.keys())[0]
            else:
                continue

        if not action:
            action = "/"
        abs_action = urljoin(origin + "/", action)
        parsed = urlparse(abs_action)
        path = parsed.path or "/"

        if method == "GET":
            # Merge with existing query params in action
            qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            for k, v in fields.items():
                if k == query_param_name:
                    qs[k] = ["__QUERY_HOLDER__"]
                else:
                    qs[k] = [v]
            new_qs = urllib.parse.urlencode({k: v[0] for k, v in qs.items()}, doseq=False)
            tmpl = f"{path}?{new_qs.replace('__QUERY_HOLDER__', '{query}')}"
            candidates.append(SearchCandidate(method="GET", template=tmpl, query_param_name=query_param_name))
        else:
            # For POST, we keep track of the action path and all fields
            candidates.append(SearchCandidate(method="POST", template=path, query_param_name=query_param_name, fields=fields))

        if len(candidates) >= cfg.search.max_form_inferred_templates:
            break

    seen = set()
    uniq: List[SearchCandidate] = []
    for cand in candidates:
        key = (cand.method, cand.template, cand.query_param_name)
        if key not in seen:
            seen.add(key)
            uniq.append(cand)
    return uniq


def stage2_http_search(
    origin: str,
    resp: requests.Response,
    cfg: FunnelConfig,
    deadline: float | None = None,
) -> Tuple[Optional[SiteVerdict], Dict[str, Any]]:
    headers = build_headers(cfg)
    session = requests.Session()
    html0 = resp.text or ""

    inferred = infer_search_templates_from_forms(origin, html0, cfg)
    fallback = [SearchCandidate(method="GET", template=t) for t in cfg.search.fallback_templates[: cfg.search.max_fallback_templates]]
    templates = inferred + fallback

    debug: Dict[str, Any] = {"inferred": [asdict(c) for c in inferred], "attempts": [], "budget_hit": False}
    for bait in cfg.search.bait_words:
        q = urllib.parse.quote(bait)
        for cand in templates:
            method = cand.method
            tmpl = cand.template
            if deadline is not None and time.time() >= deadline:
                debug["budget_hit"] = True
                debug["budget_reason"] = "stage2_deadline_exceeded"
                return None, debug
            url = origin.rstrip("/") + tmpl.replace("{query}", q)
            t0 = time.time()
            ok = False
            status = None
            try:
                if method == "POST":
                    body = dict(cand.fields or {})
                    body[cand.query_param_name or "q"] = bait
                    r = session.post(url, data=body, timeout=cfg.budgets.stage2_timeout_s, headers=headers, allow_redirects=True)
                else:
                    r = session.get(url, timeout=cfg.budgets.stage2_timeout_s, headers=headers, allow_redirects=True)
                status = r.status_code
                if status == 200 and len(r.text or "") >= 300:
                    ev = extract_evidence(r.text)
                    if ev.magnets or len(ev.hashes) >= cfg.evidence.min_hashes_to_green:
                        magnets_found = len(ev.magnets) if ev.magnets else len(ev.hashes)
                        sample_title = ""
                        if ev.magnets:
                            sample_title = ev.magnets[0].get("title", "")[:80]
                        elif ev.hashes:
                            sample_title = f"Hash {ev.hashes[0][:8]}..."
                        return (
                            SiteVerdict(
                                origin=origin,
                                status="green",
                                status_detail="ok",
                                note="evidence_found_via_http_search",
                                chosen_template=tmpl,
                                chosen_query=bait,
                                magnets_found=magnets_found,
                                sample_title=sample_title,
                                last_checked_at=datetime.now(timezone.utc).isoformat(),
                            ),
                            debug,
                        )
                    jump_ev, jump_attempts = follow_interstitial_http(
                        session=session,
                        html=r.text,
                        base_url=r.url or url,
                        cfg=cfg,
                        headers=headers,
                        deadline=deadline,
                    )
                    if jump_attempts:
                        debug.setdefault("jump_attempts", []).extend(jump_attempts)
                    if jump_ev.magnets or len(jump_ev.hashes) >= cfg.evidence.min_hashes_to_green:
                        magnets_found = len(jump_ev.magnets) if jump_ev.magnets else len(jump_ev.hashes)
                        sample_title = ""
                        if jump_ev.magnets:
                            sample_title = jump_ev.magnets[0].get("title", "")[:80]
                        elif jump_ev.hashes:
                            sample_title = f"Hash {jump_ev.hashes[0][:8]}..."
                        return (
                            SiteVerdict(
                                origin=origin,
                                status="green",
                                status_detail="ok",
                                note="evidence_found_via_http_interstitial_follow",
                                chosen_template=tmpl,
                                chosen_query=bait,
                                magnets_found=magnets_found,
                                sample_title=sample_title,
                                last_checked_at=datetime.now(timezone.utc).isoformat(),
                            ),
                            debug,
                        )
                    detail_ev, detail_attempts = follow_detail_evidence_http(
                        session=session,
                        html=r.text,
                        base_url=r.url or url,
                        cfg=cfg,
                        headers=headers,
                        deadline=deadline,
                    )
                    if detail_attempts:
                        debug.setdefault("detail_attempts", []).extend(detail_attempts)
                    if detail_ev.magnets or len(detail_ev.hashes) >= cfg.evidence.min_hashes_to_green:
                        magnets_found = len(detail_ev.magnets) if detail_ev.magnets else len(detail_ev.hashes)
                        sample_title = ""
                        if detail_ev.magnets:
                            sample_title = detail_ev.magnets[0].get("title", "")[:80]
                        elif detail_ev.hashes:
                            sample_title = f"Hash {detail_ev.hashes[0][:8]}..."
                        return (
                            SiteVerdict(
                                origin=origin,
                                status="green",
                                status_detail="ok",
                                note="evidence_found_via_http_detail_follow",
                                chosen_template=tmpl,
                                chosen_query=bait,
                                magnets_found=magnets_found,
                                sample_title=sample_title,
                                last_checked_at=datetime.now(timezone.utc).isoformat(),
                            ),
                            debug,
                        )
                    ok = True
            except requests.RequestException:
                pass
            finally:
                debug["attempts"].append(
                    {
                        "method": method,
                        "template": tmpl,
                        "bait": bait,
                        "url": url,
                        "http_status": status,
                        "ok200": ok,
                        "dt_s": round(time.time() - t0, 2),
                    }
                )
    return None, debug


def build_non_green_verdict(origin: str, reason: str, detail: str, note: str) -> SiteVerdict:
    return SiteVerdict(
        origin=origin,
        status=reason,
        status_detail=detail,
        note=note,
        last_checked_at=datetime.now(timezone.utc).isoformat(),
    )


def stage3_selenium_verify(
    origin: str,
    html0: str,
    cfg: FunnelConfig,
    deadline: float | None = None,
) -> Tuple[Optional[SiteVerdict], Dict[str, Any]]:
    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except Exception as exc:
        return None, {"stage3_unavailable": True, "reason": f"selenium_import_failed:{type(exc).__name__}"}

    inferred = infer_search_templates_from_forms(origin, html0, cfg)
    fallback = [SearchCandidate(method="GET", template=t) for t in cfg.search.fallback_templates[: cfg.search.max_fallback_templates]]
    templates = inferred + fallback
    bait = cfg.search.bait_words[0]
    q = urllib.parse.quote(bait)

    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1366,900")
    opts.add_argument(f"--user-agent={cfg.user_agent}")

    debug: Dict[str, Any] = {
        "entered": True,
        "reason": "stage2_no_evidence_but_high_potential",
        "budget_hit": False,
        "attempts": [],
        "inferred": [asdict(c) for c in inferred],
    }

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(int(cfg.budgets.stage3_timeout_s))
    driver.implicitly_wait(1)

    t0 = time.time()

    def follow_detail_evidence_browser(limit: int = 4) -> Tuple[Evidence, List[Dict[str, Any]]]:
        attempts: List[Dict[str, Any]] = []
        soup = BeautifulSoup(driver.page_source or "", "lxml")
        detail_urls = extract_detail_urls(soup.decode() if hasattr(soup, "decode") else driver.page_source or "", driver.current_url, limit=limit)
        for detail_url in detail_urls:
            if deadline is not None and time.time() >= deadline:
                break
            nav_t0 = time.time()
            try:
                driver.get(detail_url)
                time.sleep(1.5)
                ev = extract_evidence(driver.page_source or "")
                attempts.append(
                    {
                        "method": "DETAIL",
                        "template": "detail_follow",
                        "url": detail_url,
                        "dt_s": round(time.time() - nav_t0, 2),
                        "magnets_found": len(ev.magnets),
                        "hashes_found": len(ev.hashes),
                    }
                )
                if ev.magnets or len(ev.hashes) >= cfg.evidence.min_hashes_to_green:
                    return ev, attempts
            except Exception as exc:
                attempts.append(
                    {
                        "method": "DETAIL",
                        "template": "detail_follow",
                        "url": detail_url,
                        "error": type(exc).__name__,
                        "dt_s": round(time.time() - nav_t0, 2),
                    }
                )
        return Evidence(magnets=[], hashes=[]), attempts

    def build_green(note: str, template: str, ev: Evidence) -> Tuple[SiteVerdict, Dict[str, Any]]:
        magnets_found = len(ev.magnets) if ev.magnets else len(ev.hashes)
        sample_title = ""
        if ev.magnets:
            sample_title = ev.magnets[0].get("title", "")[:80]
        elif ev.hashes:
            sample_title = f"Hash {ev.hashes[0][:8]}..."
        return (
            SiteVerdict(
                origin=origin,
                status="green",
                status_detail="ok",
                note=note,
                chosen_template=template,
                chosen_query=bait,
                magnets_found=magnets_found,
                sample_title=sample_title,
                last_checked_at=datetime.now(timezone.utc).isoformat(),
            ),
            debug,
        )

    try:
        for cand in templates[: max(4, len(inferred))]:
            method = cand.method
            tmpl = cand.template
            if deadline is not None and time.time() >= deadline:
                debug["budget_hit"] = True
                debug["budget_reason"] = "stage3_deadline_exceeded"
                break
            if time.time() - t0 > cfg.budgets.stage3_timeout_s:
                debug["budget_hit"] = True
                debug["budget_reason"] = "stage3_timeout_budget_exceeded"
                break
            if method != "GET":
                debug["attempts"].append({"method": method, "template": tmpl, "skipped": True, "reason": "post_not_supported_in_stage3"})
                continue
            url = origin.rstrip("/") + tmpl.replace("{query}", q)
            nav_t0 = time.time()
            try:
                driver.get(url)
                time.sleep(1.2)
            except TimeoutException:
                debug["attempts"].append(
                    {"method": method, "template": tmpl, "url": url, "timeout": True, "dt_s": round(time.time() - nav_t0, 2)}
                )
                continue
            except Exception as exc:
                debug["attempts"].append(
                    {"method": method, "template": tmpl, "url": url, "error": type(exc).__name__, "dt_s": round(time.time() - nav_t0, 2)}
                )
                continue
            html = driver.page_source or ""
            ev = extract_evidence(html)
            debug["attempts"].append(
                {
                    "method": method,
                    "template": tmpl,
                    "url": url,
                    "dt_s": round(time.time() - nav_t0, 2),
                    "magnets_found": len(ev.magnets),
                    "hashes_found": len(ev.hashes),
                }
            )
            if ev.magnets or len(ev.hashes) >= cfg.evidence.min_hashes_to_green:
                return build_green("evidence_found_via_selenium_stage3", tmpl, ev)
            detail_ev, detail_attempts = follow_detail_evidence_browser()
            if detail_attempts:
                debug["attempts"].extend(detail_attempts)
            if detail_ev.magnets or len(detail_ev.hashes) >= cfg.evidence.min_hashes_to_green:
                return build_green("evidence_found_via_browser_detail_follow", tmpl, detail_ev)

        if deadline is None or time.time() < deadline:
            home_t0 = time.time()
            try:
                driver.get(origin)
                time.sleep(1.5)
                input_selector = "input[type='search'], input[type='text'], input[name*='q'], input[name*='search'], input[name*='keyword'], input[placeholder*='搜'], input[placeholder*='Search'], input[placeholder*='search']"
                button_selector = "button[type='submit'], input[type='submit'], button[aria-label*='搜'], button[title*='搜'], button[class*='search'], a[class*='search'], .search-btn, .btn-search"
                inputs = driver.find_elements(By.CSS_SELECTOR, input_selector)
                debug["interactive_inputs"] = len(inputs)
                debug["interactive_buttons"] = len(driver.find_elements(By.CSS_SELECTOR, button_selector))
                for idx in range(min(4, len(inputs))):
                    if deadline is not None and time.time() >= deadline:
                        debug["budget_hit"] = True
                        debug["budget_reason"] = "stage3_deadline_exceeded_during_interactive_search"
                        break
                    try:
                        inputs = driver.find_elements(By.CSS_SELECTOR, input_selector)
                        if idx >= len(inputs):
                            continue
                        inp = inputs[idx]
                        if not inp.is_displayed() or not inp.is_enabled():
                            continue
                        inp.clear()
                        inp.send_keys(bait)
                        for action in ("enter", "click"):
                            if deadline is not None and time.time() >= deadline:
                                break
                            action_started = time.time()
                            if action == "enter":
                                inp.send_keys(Keys.ENTER)
                            else:
                                clicked = False
                                buttons = driver.find_elements(By.CSS_SELECTOR, button_selector)
                                for btn in buttons[:6]:
                                    try:
                                        if btn.is_displayed() and btn.is_enabled():
                                            driver.execute_script("arguments[0].click();", btn)
                                            clicked = True
                                            break
                                    except Exception:
                                        continue
                                if not clicked:
                                    continue
                            time.sleep(2.0)
                            ev = extract_evidence(driver.page_source or "")
                            debug["attempts"].append(
                                {
                                    "method": "INTERACTIVE",
                                    "template": f"interactive_input_{idx}_{action}",
                                    "url": driver.current_url,
                                    "dt_s": round(time.time() - action_started, 2),
                                    "magnets_found": len(ev.magnets),
                                    "hashes_found": len(ev.hashes),
                                }
                            )
                            if ev.magnets or len(ev.hashes) >= cfg.evidence.min_hashes_to_green:
                                return build_green("evidence_found_via_interactive_search", f"interactive_input_{idx}_{action}", ev)
                            detail_ev, detail_attempts = follow_detail_evidence_browser()
                            if detail_attempts:
                                debug["attempts"].extend(detail_attempts)
                            if detail_ev.magnets or len(detail_ev.hashes) >= cfg.evidence.min_hashes_to_green:
                                return build_green("evidence_found_via_interactive_detail_follow", f"interactive_input_{idx}_{action}", detail_ev)
                    except Exception as exc:
                        debug["attempts"].append(
                            {
                                "method": "INTERACTIVE",
                                "template": f"interactive_input_{idx}",
                                "url": origin,
                                "error": type(exc).__name__,
                            }
                        )
            except Exception as exc:
                debug["interactive_error"] = type(exc).__name__
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return None, debug


def run_funnel(candidates: Iterable[Any], cfg: FunnelConfig, enable_stage3: bool = False) -> Dict[str, Any]:
    candidate_inputs: List[CandidateInput] = []
    seen = set()
    for raw_candidate in candidates:
        if isinstance(raw_candidate, dict):
            origin = normalize_origin(
                raw_candidate.get("origin")
                or raw_candidate.get("real_url")
                or raw_candidate.get("url")
                or ""
            )
            candidate = CandidateInput(
                origin=origin,
                name=str(raw_candidate.get("name") or raw_candidate.get("title") or ""),
                reason=str(raw_candidate.get("reason") or raw_candidate.get("source_type") or ""),
                desc=str(raw_candidate.get("desc") or raw_candidate.get("description") or ""),
                brand=str(raw_candidate.get("brand") or ""),
            )
        else:
            origin = normalize_origin(str(raw_candidate))
            candidate = CandidateInput(origin=origin)
        if not origin or origin in seen:
            continue
        seen.add(origin)
        candidate_inputs.append(candidate)

    log.info(f"Candidates: {len(candidate_inputs)} unique origins")

    results: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_candidates": len(candidate_inputs),
        "green": [],
        "yellow": [],
        "gray": [],
        "debug": {},
    }

    stage0_reachable: List[Tuple[CandidateInput, requests.Response]] = []
    stage0_browser_recovery: List[CandidateInput] = []
    with ThreadPoolExecutor(max_workers=cfg.budgets.stage0_concurrency) as ex:
        futs = {ex.submit(stage0_probe, candidate.origin, cfg): candidate for candidate in candidate_inputs}
        for fut in as_completed(futs):
            candidate = futs[fut]
            origin, resp, dt, verdict = fut.result()
            results["debug"][origin] = {
                "stage": "stage0",
                "stage0_ms": int(dt * 1000),
                "stage0_verdict": verdict,
                "candidate": asdict(candidate),
            }
            if verdict == "reachable" and resp is not None:
                stage0_reachable.append((candidate, resp))
                log.info(f"[S0] reachable {origin} {resp.status_code} {int(dt * 1000)}ms")
            elif verdict == "waf":
                results["yellow"].append(build_non_green_verdict(origin, "yellow", "waf", "stage0_waf").__dict__)
                log.info(f"[S0] waf {origin} {int(dt * 1000)}ms")
            elif verdict == "404":
                results["gray"].append(build_non_green_verdict(origin, "gray", "404", "stage0_404").__dict__)
                log.info(f"[S0] 404 {origin} {int(dt * 1000)}ms")
            else:
                if enable_stage3 and candidate_has_magnet_signal(candidate):
                    stage0_browser_recovery.append(candidate)
                    log.info(f"[S0] unreachable->browser_recovery {origin} {int(dt * 1000)}ms")
                else:
                    results["gray"].append(build_non_green_verdict(origin, "gray", "unreachable", "stage0_unreachable").__dict__)
                    log.info(f"[S0] unreachable {origin} {int(dt * 1000)}ms")

    stage3_sem = Semaphore(cfg.budgets.stage3_concurrency)

    def worker(candidate: CandidateInput, resp: requests.Response) -> Tuple[str, SiteVerdict, Dict[str, Any]]:
        origin = candidate.origin
        site_started_at = time.time()
        deadline = site_started_at + cfg.budgets.max_seconds_per_site_total
        sig = stage1_signals(origin, resp, cfg)
        metadata_signal = candidate_has_magnet_signal(candidate)
        meta: Dict[str, Any] = {
            "stage": "stage1",
            "site_budget_s": cfg.budgets.max_seconds_per_site_total,
            "signals": asdict(sig),
            "candidate": asdict(candidate),
            "metadata_signal": metadata_signal,
        }
        if sig.is_parking:
            verdict = SiteVerdict(
                origin=origin,
                status="gray",
                status_detail="expired",
                note="parking_or_for_sale",
                last_checked_at=datetime.now(timezone.utc).isoformat(),
            )
            meta["finished_at_stage"] = "stage1"
            meta["site_elapsed_s"] = round(time.time() - site_started_at, 2)
            return origin, verdict, meta

        strong = sig.has_keywords or sig.has_form or metadata_signal
        if not strong:
            verdict = SiteVerdict(
                origin=origin,
                status="yellow",
                status_detail="parsing_failed",
                note="weak_homepage_signal_needs_manual_or_adapter",
                last_checked_at=datetime.now(timezone.utc).isoformat(),
            )
            meta["finished_at_stage"] = "stage1"
            meta["site_elapsed_s"] = round(time.time() - site_started_at, 2)
            return origin, verdict, meta

        stage2_deadline = deadline
        if enable_stage3:
            reserved = max(0.0, min(cfg.budgets.stage3_reserve_s, cfg.budgets.max_seconds_per_site_total * 0.8))
            stage2_deadline = max(site_started_at, deadline - reserved)
        green, dbg = stage2_http_search(origin, resp, cfg, deadline=stage2_deadline)
        meta["stage"] = "stage2"
        meta["debug"] = dbg
        meta["stage2_budget_s"] = round(max(0.0, stage2_deadline - site_started_at), 2)
        if green:
            meta["finished_at_stage"] = "stage2"
            meta["site_elapsed_s"] = round(time.time() - site_started_at, 2)
            return origin, green, meta

        if enable_stage3 and time.time() < deadline:
            with stage3_sem:
                green3, dbg3 = stage3_selenium_verify(origin, resp.text or "", cfg, deadline=deadline)
            meta["stage3_attempted"] = True
            meta["stage3"] = dbg3
            if green3:
                meta["stage"] = "stage3"
                meta["finished_at_stage"] = "stage3"
                meta["site_elapsed_s"] = round(time.time() - site_started_at, 2)
                return origin, green3, meta
            if dbg3.get("budget_hit"):
                note = "stage3_budget_exceeded_needs_manual_or_site_adapter"
            else:
                note = "stage3_no_evidence_needs_manual_or_site_adapter"
        else:
            meta["stage3_attempted"] = bool(enable_stage3)
            if enable_stage3:
                meta["stage3"] = {"entered": False, "budget_hit": True, "budget_reason": "site_total_budget_exhausted_before_stage3"}
                note = "stage2_budget_exceeded_before_stage3"
            elif dbg.get("budget_hit"):
                note = "stage2_budget_exceeded_needs_browser_or_site_adapter"
            else:
                note = "stage2_no_evidence_needs_browser_or_site_adapter"

        verdict = SiteVerdict(
            origin=origin,
            status="yellow",
            status_detail="parsing_failed",
            note=note,
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )
        meta["finished_at_stage"] = "stage3" if meta.get("stage3_attempted") else "stage2"
        meta["site_elapsed_s"] = round(time.time() - site_started_at, 2)
        return origin, verdict, meta

    with ThreadPoolExecutor(max_workers=cfg.budgets.stage2_concurrency) as ex:
        futs = {ex.submit(worker, candidate, resp): candidate.origin for candidate, resp in stage0_reachable}
        for fut in as_completed(futs):
            origin, verdict, meta = fut.result()
            results["debug"][origin] = meta
            if verdict.status == "green":
                results["green"].append(verdict.__dict__)
                log.info(f"[GREEN] {origin} via {verdict.chosen_template} q={verdict.chosen_query} n={verdict.magnets_found}")
            elif verdict.status == "gray":
                results["gray"].append(verdict.__dict__)
                log.info(f"[GRAY] {origin} detail={verdict.status_detail} {verdict.note}")
            else:
                results["yellow"].append(verdict.__dict__)
                log.info(f"[YELLOW] {origin} {verdict.note}")

    def browser_recovery_worker(candidate: CandidateInput) -> Tuple[str, SiteVerdict, Dict[str, Any]]:
        origin = candidate.origin
        started = time.time()
        deadline = started + cfg.budgets.max_seconds_per_site_total
        green, dbg = stage3_selenium_verify(origin, "", cfg, deadline=deadline)
        meta: Dict[str, Any] = {
            "stage": "stage3_recovery",
            "candidate": asdict(candidate),
            "stage0_recovered_from": "unreachable",
            "site_budget_s": cfg.budgets.max_seconds_per_site_total,
            "stage3": dbg,
            "site_elapsed_s": round(time.time() - started, 2),
        }
        if green:
            meta["finished_at_stage"] = "stage3_recovery"
            return origin, green, meta
        verdict = SiteVerdict(
            origin=origin,
            status="yellow",
            status_detail="parsing_failed",
            note="stage0_unreachable_but_browser_recovery_no_evidence",
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )
        meta["finished_at_stage"] = "stage3_recovery"
        return origin, verdict, meta

    if stage0_browser_recovery:
        with ThreadPoolExecutor(max_workers=cfg.budgets.stage3_concurrency) as ex:
            futs = {ex.submit(browser_recovery_worker, candidate): candidate.origin for candidate in stage0_browser_recovery}
            for fut in as_completed(futs):
                origin, verdict, meta = fut.result()
                results["debug"][origin] = meta
                if verdict.status == "green":
                    results["green"].append(verdict.__dict__)
                    log.info(f"[GREEN] {origin} via recovery {verdict.chosen_template} q={verdict.chosen_query} n={verdict.magnets_found}")
                else:
                    results["yellow"].append(verdict.__dict__)
                    log.info(f"[YELLOW] {origin} {verdict.note}")

    return results


def load_candidates(path: str, start: int = 0, limit: int = 0) -> List[Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        values = data
    elif isinstance(data, dict):
        values = []
        for key in ("candidates", "urls", "results"):
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    values.append(item)
                break
        else:
            raise ValueError(f"Unsupported candidate file format: {path}")
    else:
        raise ValueError(f"Unsupported candidate file format: {path}")

    filtered: List[Any] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            filtered.append(value)
        elif isinstance(value, dict):
            if value.get("real_url") or value.get("url") or value.get("origin"):
                filtered.append(value)
    values = filtered
    if start > 0:
        values = values[start:]
    if limit > 0:
        values = values[:limit]
    return values


def build_runtime_config(args: argparse.Namespace) -> FunnelConfig:
    cfg = FunnelConfig()
    budgets = replace(
        cfg.budgets,
        stage0_concurrency=args.stage0_concurrency if args.stage0_concurrency is not None else cfg.budgets.stage0_concurrency,
        stage2_concurrency=args.stage2_concurrency if args.stage2_concurrency is not None else cfg.budgets.stage2_concurrency,
        stage3_concurrency=args.stage3_concurrency if args.stage3_concurrency is not None else cfg.budgets.stage3_concurrency,
        stage0_timeout_s=args.stage0_timeout if args.stage0_timeout is not None else cfg.budgets.stage0_timeout_s,
        stage2_timeout_s=args.stage2_timeout if args.stage2_timeout is not None else cfg.budgets.stage2_timeout_s,
        stage3_timeout_s=args.stage3_timeout if args.stage3_timeout is not None else cfg.budgets.stage3_timeout_s,
        max_seconds_per_site_total=args.max_seconds_per_site if args.max_seconds_per_site is not None else cfg.budgets.max_seconds_per_site_total,
        stage3_reserve_s=args.stage3_reserve if args.stage3_reserve is not None else cfg.budgets.stage3_reserve_s,
    )
    return replace(cfg, budgets=budgets)


def validate_sources(validate_script: str) -> None:
    proc = subprocess.run(
        [sys.executable, validate_script],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        log.info(proc.stdout.rstrip())
    if proc.stderr:
        log.info(proc.stderr.rstrip())
    if proc.returncode != 0 or "ALL VALID" not in proc.stdout:
        raise RuntimeError("validate_enum.py failed or did not report ALL VALID")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True, help="json file of candidate urls/origins")
    parser.add_argument("--out", default="funnel_report.json", help="output report path")
    parser.add_argument("--summary-out", default="funnel_summary.json", help="summary output path")
    parser.add_argument("--summary-top", type=int, default=30, help="max top items in funnel_summary.json")
    parser.add_argument("--sources", default=DEFAULT_SOURCES_PATH)
    parser.add_argument("--validate-script", default=DEFAULT_VALIDATE_PATH)
    parser.add_argument("--update-sources", action="store_true", help="upsert green results into sources.json")
    parser.add_argument("--no-validate", action="store_true", help="skip validate_enum.py after --update-sources")
    parser.add_argument("--stage3", action="store_true", help="enable strict-budget selenium stage3 for high-potential sites")
    parser.add_argument("--start", type=int, default=0, help="skip the first N candidates before running the funnel")
    parser.add_argument("--limit", type=int, default=0, help="only process the first N candidates after --start")
    parser.add_argument("--stage0-timeout", type=float, default=None)
    parser.add_argument("--stage2-timeout", type=float, default=None)
    parser.add_argument("--stage3-timeout", type=float, default=None)
    parser.add_argument("--max-seconds-per-site", type=float, default=None)
    parser.add_argument("--stage3-reserve", type=float, default=None)
    parser.add_argument("--stage0-concurrency", type=int, default=None)
    parser.add_argument("--stage2-concurrency", type=int, default=None)
    parser.add_argument("--stage3-concurrency", type=int, default=None)
    args = parser.parse_args()

    cfg = build_runtime_config(args)
    candidates = load_candidates(args.candidates, start=args.start, limit=args.limit)
    log.info("=" * 60)
    log.info("Funnel pipeline start")
    log.info(f"Input candidates: {args.candidates} ({len(candidates)}) start={args.start} limit={args.limit or 'all'}")
    log.info(
        "Budgets: stage0_timeout=%ss stage2_timeout=%ss stage3_timeout=%ss max_per_site=%ss stage3_reserve=%ss stage0_conc=%s stage2_conc=%s stage3_conc=%s stage0_retries=%s"
        % (
            cfg.budgets.stage0_timeout_s,
            cfg.budgets.stage2_timeout_s,
            cfg.budgets.stage3_timeout_s,
            cfg.budgets.max_seconds_per_site_total,
            cfg.budgets.stage3_reserve_s,
            cfg.budgets.stage0_concurrency,
            cfg.budgets.stage2_concurrency,
            cfg.budgets.stage3_concurrency,
            cfg.budgets.stage0_retries,
        )
    )
    log.info("=" * 60)

    report = run_funnel(candidates, cfg, enable_stage3=args.stage3)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"Wrote report: {args.out}")

    summary = write_summary(args.out, args.summary_out, args.summary_top)
    print_summary(summary, args.summary_out, args.summary_top)

    if args.update_sources and report.get("green"):
        data = load_sources(args.sources)
        for g in report["green"]:
            upsert_rule_from_green_verdict(
                data=data,
                origin=g.get("origin", ""),
                site_name=None,
                request_template=g.get("chosen_template", "") or "/search?q={query}",
                magnets_found=int(g.get("magnets_found") or 0),
                sample_title=g.get("sample_title", ""),
                note=g.get("note", "funnel_green"),
            )
        save_sources(data, args.sources)
        log.info(f"Updated sources.json with {len(report['green'])} green rules")
        if not args.no_validate:
            validate_sources(args.validate_script)
            log.info("validate_enum.py gate passed")
    elif args.update_sources and not args.no_validate:
        validate_sources(args.validate_script)
        log.info("validate_enum.py gate passed")

    log.info("=" * 60)
    log.info(
        f"Done: green={len(report['green'])} yellow={len(report['yellow'])} gray={len(report['gray'])} total={report['total_candidates']}"
    )
    log.info(f"Wrote summary: {args.summary_out}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
