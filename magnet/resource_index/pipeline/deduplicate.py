"""Deterministic dedup helpers."""

from __future__ import annotations

from magnet.resource_index.domain.models import ResourceRelease


def dedupe_resources_by_hash(resources: list[ResourceRelease]) -> list[ResourceRelease]:
    best: dict[str, ResourceRelease] = {}
    for r in resources:
        prev = best.get(r.info_hash)
        if prev is None:
            best[r.info_hash] = r
            continue
        score_new = sum(1 for v in (r.size_bytes, r.published_at, r.display_title) if v)
        score_old = sum(1 for v in (prev.size_bytes, prev.published_at, prev.display_title) if v)
        if score_new >= score_old:
            best[r.info_hash] = r
    return list(best.values())
