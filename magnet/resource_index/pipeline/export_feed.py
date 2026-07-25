"""Adult-isolated test feed export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from magnet.resource_index.errors import CLI_ERROR, ResourceIndexError
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

Clock = Callable[[], datetime]


def default_clock() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def build_adult_feed(
    repo: SqliteResourceRepository,
    *,
    limit: int = 100,
    include_review_fixtures: bool = False,
    clock: Clock = default_clock,
) -> dict[str, Any]:
    rows = repo.export_adult_rows(limit=limit, include_review=include_review_fixtures)
    items = []
    for row in rows:
        if not row.get("adult"):
            continue
        items.append(
            {
                "content_id": row["content_id"],
                "content_type": row["content_type"],
                "content_code": row["content_code"],
                "title": row["title"],
                "release_date": row.get("release_date"),
                "duration_minutes": row.get("duration_minutes"),
                "maker": row.get("maker_name"),
                "series": row.get("series_name"),
                "people": list(row.get("people") or []),
                "tags": list(row.get("tags") or []),
                "cover": None,
                "resource_count": int(row.get("resource_count") or 0),
                "latest_resource_at": row.get("latest_resource_at"),
                "adult": True,
                "search_query": row["content_code"],
            }
        )
    # stable sort
    items.sort(key=lambda x: x["content_code"])
    generated = clock()
    if generated.tzinfo is None:
        gen_s = generated.isoformat() + "Z"
    else:
        gen_s = generated.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0",
        "scope": "adult",
        "generated_at": gen_s,
        "source": "resource_index_test",
        "items": items,
    }


def export_adult_feed(
    repo: SqliteResourceRepository,
    output: str | Path,
    *,
    scope: str,
    limit: int = 100,
    include_review_fixtures: bool = False,
    clock: Clock = default_clock,
) -> Path:
    if scope != "adult":
        raise ResourceIndexError(
            CLI_ERROR,
            "only --scope adult is allowed; general scope cannot export adult content",
            {"scope": scope},
        )
    feed = build_adult_feed(
        repo,
        limit=limit,
        include_review_fixtures=include_review_fixtures,
        clock=clock,
    )
    # Verify isolation
    for item in feed["items"]:
        if item.get("adult") is not True:
            raise ResourceIndexError(CLI_ERROR, "feed item missing adult=true", {})
        if "magnet" in item or "magnet_uri" in item or "gid" in item or "uc" in item:
            raise ResourceIndexError(CLI_ERROR, "feed leaked internal fields", {})

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(feed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return path
