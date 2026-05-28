"""Brand-family domain rediscovery.

Triggered when a brand family (clb, 磁力猫, sobt, ...) collapses en masse —
typically all 10 mirrors return HTTP 404 simultaneously, indicating the
operator migrated to a new main domain.

Approach: query DuckDuckGo (through the local HTTP proxy if available) with
2-3 Chinese-language phrasings ("最新网址", "最新地址", "备用域名") + the
brand keyword. Harvest hosts both from result `href`s and from `body`
text. Filter against the known-dead list and the live sources.json hosts.
Probe survivors with a quick HTTP GET, scoring by:

  - any magnet hash on the page (highest)
  - brand keyword in HTML text (medium)
  - merely-reachable (lowest, last-resort signal)

Public API
----------
- BrandFamily, BrandCandidate dataclasses
- DEFAULT_FAMILIES: pre-baked list of the 4 collapsed families seen in v0.3.4
- find_brand_domains(family, proxy=None) -> list[BrandCandidate]
- find_all_collapsed(families, proxy=None) -> list[(family, [candidate])]

This is `discovery/`-level: it returns CANDIDATES; promoting a candidate
into sources.json `rules[]` is the caller's job (script `brand_rediscover.py`
or a future automated `verify_and_heal` integration).
"""

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Iterable, Dict
from urllib.parse import urlparse

# ── Regexes & blacklists ──────────────────────────────────────────────

HOST_RE = re.compile(
    r"\b((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:com|net|org|cc|me|top|xyz|biz|info|app|im|cn|io|tv|pw|to|li|club|wiki|so|do|fun))\b",
    re.I,
)

MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}", re.I)

# Generic platforms that show up in SERPs but are not the brand site
DOMAIN_BLACKLIST = {
    "github.com", "github.io", "zhihu.com", "yandex.com", "google.com",
    "bing.com", "duckduckgo.com", "baidu.com", "wikipedia.org",
    "zhanlian.net", "online.yandex.com", "163.com", "stackoverflow.com",
    "youtube.com", "twitter.com", "facebook.com", "weibo.com",
    "quark.cn", "uc.cn", "csdn.net", "jianshu.com", "sohu.com",
}


# ── Data shapes ───────────────────────────────────────────────────────

@dataclass
class BrandFamily:
    """A logical brand whose domains are interchangeable (clb, 磁力猫, ...)."""
    id: str
    label: str
    queries: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    dead_hosts: List[str] = field(default_factory=list)


@dataclass
class BrandCandidate:
    """A single host candidate produced by domain rediscovery."""
    host: str
    reachable: bool = False
    status: int = 0
    scheme: str = ""
    magnets_on_home: int = 0
    brand_hit: bool = False
    title: str = ""
    first_seen_query: str = ""
    sample_url: str = ""
    error: str = ""

    def rank_key(self) -> tuple:
        """Tuple ordering: magnets > brand_hit > reachable > magnets_count."""
        return (
            self.magnets_on_home > 0,
            self.brand_hit,
            self.reachable,
            self.magnets_on_home,
        )


# ── Default families (current state, v0.3.4) ─────────────────────────
# These mirror the collapsed families surfaced by the v0.3.4 health report.
# Update `dead_hosts` as new domains die.

DEFAULT_FAMILIES: List[BrandFamily] = [
    BrandFamily(
        id="clb",
        label="clb (磁力宝/磁力吧)",
        queries=["磁力宝 最新网址", "磁力宝 最新地址", "clb 磁力宝 备用域名"],
        keywords=["磁力宝", "磁力吧", "cilibao", "clb"],
        dead_hosts=[
            "clb13.xyz", "clb17.xyz", "clb16.top", "clb3.me", "clb1.xyz",
            "clb2.cc", "clb6.me", "clb6.cc", "clb17.top", "clb15.top",
            "clb12.top", "clb19.top", "clb13.top", "clb13.cc", "clb20.top",
            "clb18.top", "clb21.top", "clb22.top", "clb23.top", "clb24.top",
            "clb25.top", "clb26.top",
        ],
    ),
    BrandFamily(
        id="clm",
        label="磁力猫 (clm)",
        queries=["磁力猫 最新网址", "磁力猫 最新地址", "magnetcat 磁力猫"],
        keywords=["磁力猫", "magnetcat", "clm"],
        dead_hosts=[
            "magnetcatcat.com",
            "clm50.top", "clm51.top", "clm52.top", "clm53.top", "clm54.top",
            "clm56.top", "clm57.top", "clm58.top", "clm59.top",
        ],
    ),
    BrandFamily(
        id="sobt",
        label="SOBT",
        queries=["SOBT 最新网址", "sobt 磁力 最新地址"],
        keywords=["SOBT", "sobt", "搜BT", "搜磁力"],
        dead_hosts=[
            "sobt19.top", "sobt22.top", "sobt23.top", "sobt24.top", "sobt21.top",
        ],
    ),
    BrandFamily(
        id="52bt",
        label="52BT",
        queries=["52BT 最新网址", "52bt 磁力 最新地址"],
        keywords=["52BT", "52bt"],
        dead_hosts=["529072.xyz", "529073.xyz"],
    ),
]


# ── Internals ─────────────────────────────────────────────────────────

def _harvest_hosts(text: str) -> set:
    """Find domain-like tokens in arbitrary text."""
    return {m.lower() for m in HOST_RE.findall(text or "")}


def _ddg_search(query: str, proxy: Optional[str], max_results: int = 8) -> list:
    """Run a single DDG text search. Returns [{title, href, body}, ...] or []."""
    try:
        from ddgs import DDGS
    except ImportError:
        return []
    try:
        return list(DDGS(proxy=proxy, timeout=20).text(query, max_results=max_results))
    except Exception:
        return []


def _probe_host(host: str, brand_keywords: List[str], proxy: Optional[str],
                timeout: int = 12) -> BrandCandidate:
    """HEAD-style probe with magnets + brand-keyword detection."""
    import requests

    cand = BrandCandidate(host=host)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    for scheme in ("https", "http"):
        url = f"{scheme}://{host}/"
        try:
            r = requests.get(
                url, timeout=timeout, allow_redirects=True,
                proxies=proxies, verify=False,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            cand.status = r.status_code
            cand.scheme = scheme
            if r.status_code >= 400:
                continue
            cand.reachable = True
            html = r.text or ""
            cand.magnets_on_home = len(set(MAGNET_RE.findall(html)))
            for kw in brand_keywords:
                if kw and kw.lower() in html.lower():
                    cand.brand_hit = True
                    break
            tm = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            if tm:
                cand.title = tm.group(1).strip()[:80]
            return cand
        except requests.exceptions.RequestException as e:
            cand.error = str(e)[:80]
    return cand


def _live_hosts_in_sources_json(sources_json_path: str) -> set:
    """Hosts present in sources.json — never propose these as new candidates."""
    import json, os
    if not sources_json_path or not os.path.exists(sources_json_path):
        return set()
    try:
        with open(sources_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    hosts = set()
    for rs in data.get("rulesets") or []:
        for r in rs.get("rules") or []:
            origin = (r.get("site") or {}).get("origin", "")
            try:
                h = urlparse(origin).hostname
                if h:
                    hosts.add(h.lower())
            except Exception:
                pass
    return hosts


# ── Public API ────────────────────────────────────────────────────────

def find_brand_domains(family: BrandFamily, proxy: Optional[str] = None,
                       sources_json_path: str = "",
                       polite_sleep: float = 1.0) -> List[BrandCandidate]:
    """Find replacement domain candidates for one brand family.

    Pipeline: DDG search × N queries → harvest hosts → filter known-dead /
    blacklist / already-live → probe survivors → rank.
    """
    candidate_meta = {}  # host -> {first_seen_query, sample_url}
    for q in family.queries:
        for r in _ddg_search(q, proxy=proxy):
            blob = " ".join([r.get("title", ""), r.get("body", ""), r.get("href", "")])
            for h in _harvest_hosts(blob):
                h = h.lower().lstrip(".")
                if h not in candidate_meta:
                    candidate_meta[h] = {
                        "first_seen_query": q,
                        "sample_url": r.get("href", "")[:200],
                    }
        if polite_sleep:
            time.sleep(polite_sleep)

    dead_set = {d.lower() for d in family.dead_hosts}
    known = _live_hosts_in_sources_json(sources_json_path)

    filtered = []
    for h, meta in candidate_meta.items():
        if h in dead_set or h in known or h in DOMAIN_BLACKLIST:
            continue
        if any(h.endswith("." + b) for b in DOMAIN_BLACKLIST):
            continue
        filtered.append((h, meta))

    probed: List[BrandCandidate] = []
    for host, meta in filtered:
        cand = _probe_host(host, family.keywords, proxy=proxy)
        cand.first_seen_query = meta["first_seen_query"]
        cand.sample_url = meta["sample_url"]
        probed.append(cand)

    probed.sort(key=lambda c: c.rank_key(), reverse=True)
    return probed


def find_all_collapsed(families: Iterable[BrandFamily] = DEFAULT_FAMILIES,
                       proxy: Optional[str] = None,
                       sources_json_path: str = "",
                       polite_sleep: float = 1.0) -> list:
    """Run rediscovery for multiple families. Returns list of (family, [candidates])."""
    out = []
    for family in families:
        cands = find_brand_domains(family, proxy=proxy,
                                   sources_json_path=sources_json_path,
                                   polite_sleep=polite_sleep)
        out.append((family, cands))
    return out


# ── sources.json patching ────────────────────────────────────────────

# Family-id → name patterns (substring, case-insensitive) we use to attribute
# an existing sources.json rule to a brand family. Patterns are checked in
# order against `site.name`; first match wins. The host-based attribution
# (via `family.dead_hosts` matching `urlparse(origin).hostname`) is also
# considered — both must agree to tag the rule, to be conservative.
# IMPORTANT: do NOT use the short prefixes "clb" or "clm" alone — they
# false-positive match neighbouring brands like "磁力妹妹 (CLMM)" or any
# string containing those 3 characters. Use only the unambiguous brand
# spellings; host-based attribution via family.dead_hosts handles the
# numbered domain variants (clb13.xyz, clm50.top, etc.) on its own.
_FAMILY_NAME_PATTERNS = {
    "clb":  ["磁力宝", "磁力吧", "cilibao"],
    "clm":  ["磁力猫", "magnetcat", "cilimao"],
    "sobt": ["sobt", "SOBT", "搜BT"],
    "52bt": ["52bt", "52BT"],
}


def _attribute_rule_to_family(rule: dict, families: Iterable[BrandFamily]) -> Optional[str]:
    """Return the family.id this rule belongs to (or None).

    A rule is attributed if EITHER its name matches a family name pattern OR
    its hostname is in that family's dead_hosts list. We accept either signal
    because patterns alone can be too broad (e.g. "sobt" matches both SOBT
    proper and any neighbour using "sobt" in their name).
    """
    site = rule.get("site") or {}
    name = (site.get("name") or "").lower()
    origin = site.get("origin", "") or ""
    try:
        host = (urlparse(origin).hostname or "").lower()
    except Exception:
        host = ""

    # Try host-based attribution first (more reliable)
    for f in families:
        if any(host == d.lower() for d in f.dead_hosts):
            return f.id

    # Then name-pattern attribution (only when unambiguous)
    name_matches = []
    for f in families:
        patterns = _FAMILY_NAME_PATTERNS.get(f.id, [f.id])
        if any(p.lower() in name for p in patterns):
            name_matches.append(f.id)
    if len(name_matches) == 1:
        return name_matches[0]
    return None


def tag_existing_sources(sources_json_path: str,
                         families: Iterable[BrandFamily] = DEFAULT_FAMILIES,
                         dry_run: bool = True) -> dict:
    """Walk sources.json, attribute each rule to a brand family (if any),
    and set `capabilities.brand_family = <family.id>`.

    Returns a dict {family_id: [tagged_rule_names]} for inspection.
    When dry_run=True (default), nothing is written — caller can preview.
    """
    import json
    with open(sources_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tagged: Dict[str, List[str]] = {f.id: [] for f in families}
    for rs in data.get("rulesets") or []:
        for rule in rs.get("rules") or []:
            fid = _attribute_rule_to_family(rule, families)
            if not fid:
                continue
            existing = (rule.get("capabilities") or {}).get("brand_family")
            if existing == fid:
                continue  # already tagged correctly
            tagged[fid].append((rule.get("site") or {}).get("name", ""))
            if not dry_run:
                rule.setdefault("capabilities", {})
                rule["capabilities"]["brand_family"] = fid

    if not dry_run:
        with open(sources_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return tagged
