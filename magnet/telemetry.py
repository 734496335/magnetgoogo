#!/usr/bin/env python3
"""
Telemetry-driven bait & health-guard utilities.

Reads `admin-server/cache/batches.json` (3-month rolling user analytics) and
produces two artefacts consumed by `verify_and_heal.py`:

  1. `top_queries_by_lang(stats)` — high-frequency, high-hit-rate user queries
     split by Chinese/Latin script. Used as bait corpus so the verifier searches
     for the same things real users search for (≈ guaranteed to return results
     on a live source).

  2. `host_active(stats, host)` — boolean predicate: did real users get magnets
     from this host in the last N days? Used as a downgrade guard in
     `update_health` so a healthy-with-real-users source is never silently
     demoted to gray by a verifier false-negative.

Cache file is optional. Missing/corrupt → all helpers degrade to "no-op"
(empty bait override, host_active always False) so verify_and_heal stays
runnable on a fresh checkout with no telemetry yet.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', 'admin-server', 'cache', 'batches.json',
)

# An event timestamp (ms since epoch) older than this many days is ignored.
DEFAULT_LOOKBACK_DAYS = 30

_HAN_RE = re.compile(r'[\u4e00-\u9fff]')


def _has_chinese(s: str) -> bool:
    return bool(_HAN_RE.search(s or ''))


def _host_of(url_or_host: str) -> str:
    """Normalise to bare hostname (lowercase, strip leading www.)."""
    if not url_or_host:
        return ''
    s = url_or_host.strip().lower()
    if '://' in s:
        s = urlparse(s).hostname or ''
    if s.startswith('www.'):
        s = s[4:]
    return s


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_telemetry(
    path: Optional[str] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> Optional[Dict]:
    """Load and aggregate analytics batches. Returns None if cache is missing.

    NB: the frontend reports the `src` field inconsistently — some clients
    send the bare hostname (`u3c3.com`), others send the human site.name
    (`种子吧(zzb04)`). We index by the literal `src` value (post-strip,
    case-preserving) and let `host_active()` try multiple lookup keys.

    Returns dict with keys:
      - `host_stats`: {src_key: {'ok': int, 'fail': int, 'last_ok_ts': int}}
      - `query_stats`: {q: {'count': int, 'hits': int, 'lang': 'zh'|'en'}}
                       where `hits` = times the search returned >0 results.
      - `meta`: {'batches': int, 'events': int, 'cutoff_ms': int, 'path': str}
    """
    target = path or _CACHE_PATH
    if not os.path.exists(target):
        return None
    try:
        with open(target, 'r', encoding='utf-8') as f:
            batches = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(batches, list):
        return None

    cutoff_ms = int((time.time() - lookback_days * 86400) * 1000)

    host_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {'ok': 0, 'fail': 0, 'last_ok_ts': 0}
    )
    query_stats: Dict[str, Dict] = defaultdict(
        lambda: {'count': 0, 'hits': 0, 'lang': 'en'}
    )

    ev_count = 0
    for b in batches:
        for e in b.get('events', []):
            ts = e.get('ts', 0)
            if ts and ts < cutoff_ms:
                continue
            kind = e.get('e')
            ev_count += 1
            if kind == 'src_ok':
                # Index by literal src (could be hostname or site.name).
                # Lookup-time logic in host_active() tries both forms.
                src = (e.get('src') or '').strip()
                if src:
                    host_stats[src]['ok'] += 1
                    if ts > host_stats[src]['last_ok_ts']:
                        host_stats[src]['last_ok_ts'] = ts
            elif kind == 'src_fail':
                src = (e.get('src') or '').strip()
                if src:
                    host_stats[src]['fail'] += 1
            elif kind == 'search':
                q = (e.get('q') or '').strip()
                if not q or len(q) > 40:
                    continue
                n = e.get('n', 0)
                rec = query_stats[q]
                rec['count'] += 1
                if n and n > 0:
                    rec['hits'] += 1
                rec['lang'] = 'zh' if _has_chinese(q) else 'en'

    return {
        'host_stats': dict(host_stats),
        'query_stats': dict(query_stats),
        'meta': {
            'batches': len(batches),
            'events': ev_count,
            'cutoff_ms': cutoff_ms,
            'path': target,
        },
    }


# ---------------------------------------------------------------------------
# Bait corpus derivation
# ---------------------------------------------------------------------------

def top_queries_by_lang(
    stats: Dict,
    per_lang: int = 6,
    min_count: int = 3,
    min_hit_rate: float = 0.6,
) -> Dict[str, List[str]]:
    """Pick the queries most likely to return results from a live source.

    Strategy:
      1. Filter queries seen ≥ `min_count` times (≥1 also possible, but 3
         de-dups one-off typos).
      2. Keep only those with hit_rate (`hits/count`) ≥ `min_hit_rate` —
         i.e. queries that **historically returned results most of the
         time** are the safest bait for a verifier.
      3. Rank by total frequency, take top-N per language bucket.

    Returns `{'zh': [...], 'en': [...]}`. Empty lists if telemetry is sparse.
    """
    buckets: Dict[str, List[Tuple[str, int]]] = {'zh': [], 'en': []}
    for q, rec in (stats.get('query_stats') or {}).items():
        c = rec['count']
        if c < min_count:
            continue
        hit_rate = rec['hits'] / c if c else 0
        if hit_rate < min_hit_rate:
            continue
        buckets[rec['lang']].append((q, c))

    out = {}
    for lang, items in buckets.items():
        items.sort(key=lambda x: -x[1])
        out[lang] = [q for q, _ in items[:per_lang]]
    return out


# ---------------------------------------------------------------------------
# Health guard
# ---------------------------------------------------------------------------

def _candidate_keys(origin_or_host: str, name: Optional[str] = None):
    """Yield lookup keys we should try against host_stats. Order matters:
    most-specific first. Frontend sends `src` as either bare hostname or
    site.name, so we accept both.
    """
    keys = []
    if origin_or_host:
        h = _host_of(origin_or_host)
        if h:
            keys.append(h)
            # Some clients prepend www. — tolerate both directions.
            keys.append('www.' + h)
    if name:
        n = name.strip()
        if n:
            keys.append(n)
    # De-dup preserving order.
    seen = set()
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            yield k


def host_active(
    stats: Dict,
    origin_or_host: str,
    min_ok: int = 10,
    name: Optional[str] = None,
) -> bool:
    """True iff real users got ≥ `min_ok` successful magnet results from this
    host in the lookback window. Tries `origin` host first, then `name` —
    necessary because the frontend reports `src` inconsistently.
    """
    hs = stats.get('host_stats') or {}
    for k in _candidate_keys(origin_or_host, name):
        rec = hs.get(k)
        if rec and rec['ok'] >= min_ok:
            return True
    return False


def host_ok_count(stats: Dict, origin_or_host: str,
                  name: Optional[str] = None) -> int:
    hs = stats.get('host_stats') or {}
    best = 0
    for k in _candidate_keys(origin_or_host, name):
        rec = hs.get(k)
        if rec and rec['ok'] > best:
            best = rec['ok']
    return best


# ---------------------------------------------------------------------------
# CLI: quick inspect
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    s = load_telemetry()
    if not s:
        print('No telemetry cache found at', _CACHE_PATH)
        raise SystemExit(0)
    print(f"events={s['meta']['events']}  hosts={len(s['host_stats'])}  "
          f"queries={len(s['query_stats'])}")
    tq = top_queries_by_lang(s)
    print('top zh:', tq['zh'])
    print('top en:', tq['en'])
    active = sum(1 for h in s['host_stats'] if host_active(s, h))
    print(f"active hosts (≥10 ok / {DEFAULT_LOOKBACK_DAYS}d): {active}")
