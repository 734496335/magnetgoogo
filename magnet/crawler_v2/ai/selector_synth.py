"""LLM-driven selector synthesis (Crawl4AI + reasoning LLM).

OFFLINE-ONLY. Never invoked from real-time search path; only by batch
verification (`magnet/scripts/ai_reverify.py`) or interactive single-source
debugging.

Public API
----------
- fetch_page_html(url, proxy, ...): StealthyFetcher wrapper, returns dict
- expand_search_url(template, query): renders {query} / {query_raw} / {query_b64}
- synthesize_selectors_for_html(html, llm_choice): one LLM call, returns
  selectors dict {list_item, title, magnet, detail_link}
- synthesize_selectors_for_url(url_template, query, llm_choice, proxy):
  full pipeline (fetch → LLM → validate → render rule draft)
- validate_selectors(html, selectors): runs selectors against HTML, returns
  {list_items, magnets_found, titles_found, samples, ...}
- render_rule_draft(...): produces a sources.json-shaped dict with
  `_ai_proposal` provenance metadata
"""

import re
import json
import base64
import asyncio
from typing import Optional, Dict, Any, List
from urllib.parse import quote

MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}", re.I)


_LLM_INSTRUCTION = """You are analysing a search-results page from a BitTorrent / magnet-link
indexing site. Your job is to output CSS selectors that can be used to
extract the search-result rows from this page.

Return ONE JSON object, exactly this shape, no extra prose:

{
  "list_item":   "<CSS selector that matches each individual search-result row>",
  "title":       "<CSS selector RELATIVE TO list_item that matches the title element>",
  "magnet":      "<CSS selector RELATIVE TO list_item for the <a> whose href starts with 'magnet:'>",
  "detail_link": "<CSS selector RELATIVE TO list_item for the <a> linking to the detail/info page>"
}

Rules:
  - Only use CSS selectors that BeautifulSoup's .select() understands.
  - If the magnet link is on the detail page rather than this listing,
    set "magnet" to "" (empty string) and make sure "detail_link" is correct.
  - Prefer stable, semantic selectors (class names) over brittle nth-child indexing.
  - Do not invent class names — only use ones that actually appear in the HTML.
  - If you cannot identify any list rows, return an object with all four
    fields set to "" (empty string)."""


# ──────────────────────────────────────────────────────────────────────
# URL + fetch helpers (mirror production extractor's {query} semantics)
# ──────────────────────────────────────────────────────────────────────

def expand_search_url(url_template: str, query: str) -> str:
    """Render `{query}` / `{query_raw}` / `{query_b64}` placeholders the same
    way the production extractor does. Some Chinese magnet sites (sobt21,
    laowangcili) base64-encode their search keyword."""
    q_encoded = quote(query)
    q_b64 = base64.b64encode(query.encode("utf-8")).decode("ascii")
    return (
        url_template
        .replace("{query_b64}", q_b64)
        .replace("{query}", q_encoded)
        .replace("{query_raw}", query)
    )


def fetch_page_html(url: str, proxy: Optional[str] = None, timeout: int = 30,
                    use_stealth: bool = True) -> Dict[str, Any]:
    """Fetch a page, returning {html, status, final_url, fetcher, [error]}.

    Uses Scrapling's StealthyFetcher (Playwright-based, already a project dep)
    for WAF resistance. Falls back to plain Fetcher when use_stealth=False.
    """
    try:
        if use_stealth:
            from scrapling.fetchers import StealthyFetcher
            page = StealthyFetcher.fetch(
                url, headless=True, network_idle=True,
                google_search=False, timeout=timeout * 1000,
                proxy=proxy,
            )
            return {
                "html": page.html_content if hasattr(page, "html_content") else str(page),
                "status": getattr(page, "status", 0),
                "final_url": getattr(page, "url", url),
                "fetcher": "StealthyFetcher",
            }
        from scrapling.fetchers import Fetcher
        page = Fetcher.get(url, timeout=timeout, proxy=proxy)
        return {
            "html": page.html_content if hasattr(page, "html_content") else str(page),
            "status": getattr(page, "status", 0),
            "final_url": getattr(page, "url", url),
            "fetcher": "Fetcher",
        }
    except Exception as e:
        return {"html": "", "status": 0, "final_url": url, "fetcher": "error", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────
# LLM extraction (Crawl4AI, async — we wrap with asyncio.run)
# ──────────────────────────────────────────────────────────────────────

def _strip_fences_and_parse(text: str):
    """LLMs (esp. reasoning ones like MiMo) often wrap JSON in ```json fences."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def _run_crawl4ai_extraction(html: str, llm_choice) -> Dict[str, str]:
    """One Crawl4AI call with raw:// HTML input. Returns selectors dict."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, LLMConfig
    from crawl4ai.extraction_strategy import LLMExtractionStrategy

    llm_config = LLMConfig(
        provider=llm_choice.provider,
        api_token=llm_choice.api_token,
        base_url=llm_choice.base_url,
        max_tokens=llm_choice.max_tokens,
        temperature=0.0,
    )
    strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        instruction=_LLM_INSTRUCTION,
        extraction_type="block",
        chunk_token_threshold=8000,
        apply_chunking=False,
        input_format="html",
        force_json_response=True,
    )
    browser_cfg = BrowserConfig(headless=True, verbose=False)
    run_cfg = CrawlerRunConfig(
        extraction_strategy=strategy,
        cache_mode=None,
        verbose=False,
    )

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        result = await crawler.arun(url=f"raw://{html}", config=run_cfg)

    raw_content = ""
    if result and getattr(result, "extracted_content", None):
        raw_content = result.extracted_content
    elif result and getattr(result, "markdown", None):
        raw_content = str(result.markdown)

    parsed = _strip_fences_and_parse(raw_content)
    if parsed is None:
        return {"list_item": "", "title": "", "magnet": "", "detail_link": ""}
    # Normalise: make sure all 4 keys exist as strings
    return {k: (parsed.get(k) or "") for k in ("list_item", "title", "magnet", "detail_link")}


def synthesize_selectors_for_html(html: str, llm_choice) -> Dict[str, str]:
    """Sync wrapper around the async Crawl4AI call. Returns selectors dict."""
    return asyncio.run(_run_crawl4ai_extraction(html, llm_choice))


# ──────────────────────────────────────────────────────────────────────
# Validation (run selectors against actual HTML)
# ──────────────────────────────────────────────────────────────────────

def validate_selectors(html: str, selectors: Dict[str, str], max_items: int = 30) -> Dict[str, Any]:
    """Run candidate selectors against the actual HTML.

    Returns metrics dict with `magnets_found / list_items / titles_found /
    detail_links_found / samples / regex_magnets_on_page`. The
    `regex_magnets_on_page` is a sanity number: total magnets the regex
    sees anywhere on the page (banner / sidebar / etc.) — if selector
    found 30 and regex sees 43, ~13 magnets are outside the list.
    """
    from bs4 import BeautifulSoup

    out: Dict[str, Any] = {
        "list_items": 0, "magnets_found": 0, "titles_found": 0,
        "detail_links_found": 0, "samples": [],
        "regex_magnets_on_page": 0,
    }
    if not html:
        return out

    out["regex_magnets_on_page"] = len(set(MAGNET_RE.findall(html)))

    soup = BeautifulSoup(html, "html.parser")
    list_sel = (selectors.get("list_item") or "").strip()
    title_sel = (selectors.get("title") or "").strip()
    magnet_sel = (selectors.get("magnet") or "").strip()
    detail_sel = (selectors.get("detail_link") or "").strip()

    if not list_sel:
        return out

    items = soup.select(list_sel)
    out["list_items"] = len(items)

    for item in items[:max_items]:
        magnet_href = ""
        if magnet_sel:
            mag_el = item.select_one(magnet_sel)
            if mag_el and mag_el.get("href", "").startswith("magnet:"):
                magnet_href = mag_el["href"]
        if not magnet_href:
            for a in item.find_all("a", href=True):
                if a["href"].startswith("magnet:"):
                    magnet_href = a["href"]
                    break

        title = ""
        if title_sel:
            t_el = item.select_one(title_sel)
            if t_el:
                title = t_el.get_text(strip=True)[:120]

        detail_href = ""
        if detail_sel:
            d_el = item.select_one(detail_sel)
            if d_el and d_el.get("href"):
                detail_href = d_el["href"]

        if magnet_href:
            out["magnets_found"] += 1
        if title:
            out["titles_found"] += 1
        if detail_href:
            out["detail_links_found"] += 1
        if len(out["samples"]) < 3 and (title or magnet_href or detail_href):
            out["samples"].append({
                "title": title,
                "magnet": magnet_href[:80] + "..." if len(magnet_href) > 80 else magnet_href,
                "detail": detail_href,
            })

    return out


# ──────────────────────────────────────────────────────────────────────
# Full pipeline + rule draft rendering
# ──────────────────────────────────────────────────────────────────────

def render_rule_draft(name: str, origin: str, request_template: str,
                      selectors: Dict[str, str], tags: List[str],
                      validation: Dict[str, Any], llm_label: str) -> Dict[str, Any]:
    """Produce a sources.json-compatible rule object.

    Output uses `_ai_proposal` (not `_ai_bootstrap`) per CRAWLER-ARCHITECTURE.md
    v0.3.5+: the synthesized selectors go into `_ai_proposal.selectors` (a
    PROPOSAL), not directly into `parse_metadata.selectors`. Human or scripted
    review then promotes them to the canonical location.
    """
    confidence = 0.0
    if validation["list_items"] > 0:
        confidence = round(validation["magnets_found"] / max(validation["list_items"], 1), 2)
    cleaned = {k: v for k, v in selectors.items() if v}
    return {
        "site": {"name": name, "origin": origin},
        "search": {
            "request_template": request_template,
            # Note: proposal does NOT auto-populate parse_metadata.selectors —
            # the live extractor must keep using whatever's already there until
            # a human/script promotes the proposal.
        },
        "quality": {"score": 50, "tags": list(tags) + ["ai_bootstrap"]},
        "health": {"status": "yellow", "status_detail": "parsing_failed"},
        "_ai_proposal": {
            "generator": llm_label,
            "confidence": confidence,
            "selectors": cleaned,
            "validation": validation,
            "reviewer_note": "Promote _ai_proposal.selectors → search.parse_metadata.selectors only after verifying.",
        },
    }


def synthesize_selectors_for_url(url_template: str, query: str, llm_choice,
                                 proxy: Optional[str] = None,
                                 site_name: str = "", tags: List[str] = None,
                                 use_stealth: bool = True) -> Dict[str, Any]:
    """End-to-end: fetch page → call LLM → validate → return rule draft.

    Returns a dict with either:
      - `rule_draft`: the sources.json-shaped output (success path)
      - `error`: short description (failure path)
    Always includes `fetcher`, `bytes`, `bait_used` metadata for logging.
    """
    from urllib.parse import urlparse

    full_url = expand_search_url(url_template, query)
    page = fetch_page_html(full_url, proxy=proxy, use_stealth=use_stealth)
    if not page.get("html"):
        return {
            "error": f"fetch failed: {page.get('error', 'empty html')}",
            "fetcher": page.get("fetcher", "?"),
            "bait_used": query,
            "url": full_url,
        }

    try:
        selectors = synthesize_selectors_for_html(page["html"], llm_choice)
    except Exception as e:
        return {
            "error": f"LLM synthesis failed: {e}",
            "fetcher": page.get("fetcher"),
            "bytes": len(page["html"]),
            "bait_used": query,
            "url": full_url,
        }

    validation = validate_selectors(page["html"], selectors)

    parsed = urlparse(url_template)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    request_template = url_template[len(origin):] if url_template.startswith(origin) else url_template
    rule_draft = render_rule_draft(
        name=site_name or parsed.netloc,
        origin=origin,
        request_template=request_template,
        selectors=selectors,
        tags=tags or [],
        validation=validation,
        llm_label=f"crawl4ai+{llm_choice.label}",
    )
    return {
        "rule_draft": rule_draft,
        "fetcher": page.get("fetcher"),
        "bytes": len(page["html"]),
        "bait_used": query,
        "url": full_url,
    }
