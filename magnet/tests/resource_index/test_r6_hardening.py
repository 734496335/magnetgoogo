from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import magnet.resource_index.pipeline.ingest_live as ingest_live_module
from magnet.resource_index.acquisition.http_client import LiveHttpClient
from magnet.resource_index.acquisition.policy import LiveFetchPolicy, PhysicalRequestBudget
from magnet.resource_index.cli import _crawl_exit_code
from magnet.resource_index.domain.enums import IngestRunStatus
from magnet.resource_index.errors import (
    INGEST_CANCELLED,
    LIVE_HTTP_ERROR,
    LIVE_RATE_LIMITED,
    LIVE_URL_REJECTED,
    STALE_INGEST_RECOVERED,
    LivePolicyError,
    ResourceIndexError,
)
from magnet.resource_index.pipeline.ingest_live import ingest_live
from magnet.resource_index.store.migrations import file_checksum
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository
from magnet.tests.resource_index.test_sqlite_repository import NOW, _bundle


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class _SequenceSession:
    def __init__(self, responses, *, clock: _Clock | None = None) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.cookies = {}
        self.clock = clock
        self.started_at: list[float] = []
        self.allow_redirects: list[bool] = []

    def request(self, *_args, **kwargs):
        self.calls += 1
        if self.clock is not None:
            self.started_at.append(self.clock.value)
        self.allow_redirects.append(bool(kwargs.get("allow_redirects")))
        item = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item


def _response(
    status: int,
    body: str = "ok",
    *,
    url: str = "https://www.javbus.com/",
    headers: dict[str, str] | None = None,
):
    return SimpleNamespace(status_code=status, text=body, url=url, headers=headers or {})


def _resolver(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34"]


def _policy(max_pages: int = 20) -> LiveFetchPolicy:
    return LiveFetchPolicy(
        enabled=True,
        acknowledged=True,
        max_pages=max_pages,
        request_delay_seconds=10.0,
        concurrency=1,
    )


def test_live_http_requires_explicit_origin_allowlist() -> None:
    with pytest.raises(Exception) as exc:
        LiveHttpClient(request_delay_seconds=0)
    assert getattr(exc.value, "error_code", None) == "CONFIG_ERROR"


def test_physical_request_budget_counts_retries() -> None:
    budget = PhysicalRequestBudget(limit=1)
    session = _SequenceSession([_response(500), _response(200)])
    client = LiveHttpClient(
        request_delay_seconds=10.0,
        max_retries=1,
        allowed_origins={"https://www.javbus.com:443"},
        request_budget=budget,
        dns_resolver=_resolver,
    )
    client._session = session

    with pytest.raises(LivePolicyError) as exc:
        client.get("https://www.javbus.com/")

    assert exc.value.error_code == LIVE_RATE_LIMITED
    assert session.calls == 1
    assert budget.used == 1


def test_transport_retries_respect_minimum_spacing() -> None:
    clock = _Clock()
    session = _SequenceSession(
        [OSError("one"), OSError("two"), _response(200)],
        clock=clock,
    )
    client = LiveHttpClient(
        request_delay_seconds=10.0,
        max_retries=2,
        allowed_origins={"https://www.javbus.com:443"},
        request_budget=PhysicalRequestBudget(limit=3),
        dns_resolver=_resolver,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    client._session = session

    assert client.get("https://www.javbus.com/").status_code == 200
    assert session.calls == 3
    assert all(
        later - earlier >= 10.0
        for earlier, later in zip(session.started_at, session.started_at[1:])
    )


def test_cancel_during_retry_wait_does_not_increment_request_count() -> None:
    budget = PhysicalRequestBudget(limit=3)
    session = _SequenceSession([OSError("one")])

    def interrupt_sleep(_seconds: float) -> None:
        raise KeyboardInterrupt()

    client = LiveHttpClient(
        request_delay_seconds=10.0,
        max_retries=2,
        allowed_origins={"https://www.javbus.com:443"},
        request_budget=budget,
        dns_resolver=_resolver,
        sleep=interrupt_sleep,
    )
    client._session = session

    with pytest.raises(KeyboardInterrupt):
        client.get("https://www.javbus.com/")

    assert session.calls == 1
    assert budget.used == 1


def test_unhandled_3xx_is_not_treated_as_success() -> None:
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=0,
        allowed_origins={"https://www.javbus.com:443"},
        request_budget=PhysicalRequestBudget(limit=1),
        dns_resolver=_resolver,
    )
    client._session = _SequenceSession([_response(304)])

    with pytest.raises(ResourceIndexError) as exc:
        client.get("https://www.javbus.com/")

    assert exc.value.error_code == LIVE_HTTP_ERROR


def test_redirect_is_validated_before_following() -> None:
    session = _SequenceSession(
        [
            _response(
                302,
                url="https://www.javbus.com/start",
                headers={"Location": "http://127.0.0.1/admin"},
            )
        ]
    )
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=0,
        allowed_origins={"https://www.javbus.com:443"},
        request_budget=PhysicalRequestBudget(limit=5),
        dns_resolver=_resolver,
    )
    client._session = session

    with pytest.raises(LivePolicyError) as exc:
        client.get("https://www.javbus.com/start")

    assert exc.value.error_code == LIVE_URL_REJECTED
    assert session.calls == 1
    assert session.allow_redirects == [False]


def test_same_origin_redirect_counts_as_physical_request() -> None:
    session = _SequenceSession(
        [
            _response(
                302,
                url="https://www.javbus.com/start",
                headers={"location": "/next"},
            ),
            _response(200, url="https://www.javbus.com/next"),
        ]
    )
    budget = PhysicalRequestBudget(limit=2)
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=0,
        allowed_origins={"https://www.javbus.com:443"},
        request_budget=budget,
        dns_resolver=_resolver,
    )
    client._session = session

    response = client.get("https://www.javbus.com/start")

    assert response.url == "https://www.javbus.com/next"
    assert session.calls == 2
    assert budget.used == 2
    assert session.allow_redirects == [False, False]


def test_nonstandard_port_rejected_before_request() -> None:
    session = _SequenceSession([_response(200)])
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=0,
        allowed_origins={"https://www.javbus.com:443"},
        request_budget=PhysicalRequestBudget(limit=1),
        dns_resolver=_resolver,
    )
    client._session = session

    with pytest.raises(LivePolicyError) as exc:
        client.get("https://www.javbus.com:8443/x")

    assert exc.value.error_code == LIVE_URL_REJECTED
    assert session.calls == 0


def test_keyboard_interrupt_finishes_run_as_cancelled(monkeypatch, tmp_path: Path) -> None:
    class InterruptCrawler:
        source_id = "fake"

        def __init__(self, **_kwargs) -> None:
            pass

        def crawl_query(self, _query: str, *, limit: int):
            raise KeyboardInterrupt()

    monkeypatch.setattr(
        ingest_live_module,
        "get_crawler_factory",
        lambda _source: InterruptCrawler,
    )
    repo = SqliteResourceRepository(tmp_path / "cancelled.db")
    repo.init_schema()

    result = ingest_live(
        repo=repo,
        source_id="fake",
        query="x",
        limit=1,
        policy=_policy(),
        run_id="cancelled-run",
    )
    row = repo.conn.execute(
        "SELECT status, finished_at, errors, error_summary_json FROM ingest_runs WHERE run_id = ?",
        ("cancelled-run",),
    ).fetchone()

    assert result.status == IngestRunStatus.CANCELLED.value
    assert row["status"] == IngestRunStatus.CANCELLED.value
    assert row["finished_at"] is not None
    assert row["errors"] == 1
    assert json.loads(row["error_summary_json"]) == {INGEST_CANCELLED: 1}
    repo.close()


def test_stale_running_runs_are_recovered(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "stale.db")
    repo.init_schema()
    old = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)
    recovered_at = old + timedelta(hours=3)
    repo.start_ingest_run("stale-run", "javbus", "live_one_shot", old)

    recovered = repo.recover_stale_ingest_runs(
        stale_before=old + timedelta(hours=1),
        recovered_at=recovered_at,
    )
    row = repo.conn.execute(
        "SELECT status, finished_at, errors, error_summary_json FROM ingest_runs WHERE run_id = ?",
        ("stale-run",),
    ).fetchone()
    event = repo.conn.execute(
        "SELECT error_code FROM ingest_events WHERE run_id = ?",
        ("stale-run",),
    ).fetchone()

    assert recovered == 1
    assert row["status"] == IngestRunStatus.FAILED.value
    assert row["finished_at"] is not None
    assert row["errors"] == 1
    assert json.loads(row["error_summary_json"]) == {STALE_INGEST_RECOVERED: 1}
    assert event["error_code"] == STALE_INGEST_RECOVERED
    repo.close()


def _source_bundle(
    source_id: str,
    *,
    title: str,
    detail_url: str,
    parser_version: str,
    priority: int,
):
    base = _bundle(resources=[])
    content = replace(
        base.content,
        title=title,
        detail_url=detail_url,
        source_id=source_id,
        source_item_key=f"/{source_id}/TST-001",
        parser_version=parser_version,
    )
    return replace(
        base,
        content=content,
        provenance=replace(
            base.provenance,
            source_id=source_id,
            source_item_key=content.source_item_key,
            detail_url=detail_url,
            parser_version=parser_version,
            internal={
                "source_priority": priority,
                "relation_presence": {"people": True, "tags": True},
            },
        ),
    )


def test_multi_source_observations_do_not_mix_canonical_fields(
    repo: SqliteResourceRepository,
) -> None:
    source_a = _source_bundle(
        "source-a",
        title="Source A",
        detail_url="https://a.example/TST-001",
        parser_version="a/1",
        priority=100,
    )
    source_b = _source_bundle(
        "source-b",
        title="Source B",
        detail_url="https://b.example/TST-001",
        parser_version="b/1",
        priority=10,
    )

    repo.upsert_bundle(source_a, now=NOW)
    repo.upsert_bundle(source_b, now=NOW + timedelta(minutes=1))
    row = repo.get_content_by_code("TST-001")

    assert row is not None
    assert row["title"] == "Source A"
    assert row["source_id"] == "source-a"
    assert row["source_item_key"] == "/source-a/TST-001"
    assert row["detail_url"] == "https://a.example/TST-001"
    assert row["parser_version"] == "a/1"
    assert {item["source_id"] for item in row["sources"]} == {"source-a", "source-b"}


def test_missing_priority_preserves_existing_source_priority(
    repo: SqliteResourceRepository,
) -> None:
    source = _source_bundle(
        "source-a",
        title="Source A",
        detail_url="https://a.example/TST-001",
        parser_version="a/1",
        priority=100,
    )
    repo.upsert_bundle(source, now=NOW)
    without_priority = replace(
        source,
        provenance=replace(
            source.provenance,
            internal={"relation_presence": {"people": True, "tags": True}},
        ),
    )

    repo.upsert_bundle(without_priority, now=NOW + timedelta(minutes=1))
    priority = repo.conn.execute(
        "SELECT source_priority FROM content_observations WHERE source_id = 'source-a'"
    ).fetchone()[0]

    assert priority == 100


def test_search_matches_noncanonical_source_title(
    repo: SqliteResourceRepository,
) -> None:
    source_a = _source_bundle(
        "source-a",
        title="Canonical Alpha",
        detail_url="https://a.example/TST-001",
        parser_version="a/1",
        priority=100,
    )
    source_b = _source_bundle(
        "source-b",
        title="Alternative Bravo",
        detail_url="https://b.example/TST-001",
        parser_version="b/1",
        priority=10,
    )
    repo.upsert_bundle(source_a, now=NOW)
    repo.upsert_bundle(source_b, now=NOW + timedelta(minutes=1))

    rows = repo.search_contents("Bravo")

    assert [row["content_code"] for row in rows] == ["TST-001"]


def test_higher_priority_source_switches_canonical_as_a_whole(
    repo: SqliteResourceRepository,
) -> None:
    source_a = _source_bundle(
        "source-a",
        title="Source A",
        detail_url="https://a.example/TST-001",
        parser_version="a/1",
        priority=10,
    )
    source_b = _source_bundle(
        "source-b",
        title="Source B",
        detail_url="https://b.example/TST-001",
        parser_version="b/1",
        priority=200,
    )

    repo.upsert_bundle(source_a, now=NOW)
    repo.upsert_bundle(source_b, now=NOW + timedelta(minutes=1))
    row = repo.get_content_by_code("TST-001")

    assert row is not None
    assert (
        row["title"],
        row["source_id"],
        row["source_item_key"],
        row["detail_url"],
        row["parser_version"],
    ) == (
        "Source B",
        "source-b",
        "/source-b/TST-001",
        "https://b.example/TST-001",
        "b/1",
    )


def test_schema_v2_backfills_content_observations(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "schema.db")
    assert repo.init_schema() == "0006"
    repo.upsert_bundle(_bundle(resources=[]), now=NOW)

    count = repo.conn.execute("SELECT COUNT(*) FROM content_observations").fetchone()[0]

    assert count == 1
    repo.close()


def test_dns_resolution_to_private_address_is_rejected_before_request() -> None:
    session = _SequenceSession([_response(200)])
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=0,
        allowed_origins={"https://www.javbus.com:443"},
        request_budget=PhysicalRequestBudget(limit=1),
        dns_resolver=lambda _host, _port: ["127.0.0.1"],
    )
    client._session = session

    with pytest.raises(LivePolicyError) as exc:
        client.get("https://www.javbus.com/")

    assert exc.value.error_code == LIVE_URL_REJECTED
    assert session.calls == 0


def test_proxy_fake_ip_range_is_allowed_for_exact_origin() -> None:
    session = _SequenceSession([_response(200)])
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=0,
        allowed_origins={"https://www.javbus.com:443"},
        request_budget=PhysicalRequestBudget(limit=1),
        dns_resolver=lambda _host, _port: ["198.18.0.10"],
    )
    client._session = session

    assert client.get("https://www.javbus.com/").status_code == 200
    assert session.calls == 1


def test_ingest_live_recovers_stale_run_on_start(monkeypatch, tmp_path: Path) -> None:
    class EmptyCrawler:
        source_id = "fake"

        def __init__(self, **_kwargs) -> None:
            pass

        def crawl_query(self, _query: str, *, limit: int):
            return []

    monkeypatch.setattr(
        ingest_live_module,
        "get_crawler_factory",
        lambda _source: EmptyCrawler,
    )
    repo = SqliteResourceRepository(tmp_path / "automatic-recovery.db")
    repo.init_schema()
    old = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)
    now = old + timedelta(hours=2)
    repo.start_ingest_run("old-run", "javbus", "live_one_shot", old)

    ingest_live(
        repo=repo,
        source_id="fake",
        query="x",
        limit=1,
        policy=_policy(),
        run_id="new-run",
        clock=lambda: now,
        stale_run_after_seconds=3600,
    )
    old_row = repo.conn.execute(
        "SELECT status, error_summary_json FROM ingest_runs WHERE run_id = 'old-run'"
    ).fetchone()

    assert old_row["status"] == IngestRunStatus.FAILED.value
    assert json.loads(old_row["error_summary_json"]) == {STALE_INGEST_RECOVERED: 1}
    repo.close()


def test_noncanonical_source_does_not_replace_canonical_relations(
    repo: SqliteResourceRepository,
) -> None:
    source_a = _source_bundle(
        "source-a",
        title="Source A",
        detail_url="https://a.example/TST-001",
        parser_version="a/1",
        priority=100,
    )
    source_b = _source_bundle(
        "source-b",
        title="Source B",
        detail_url="https://b.example/TST-001",
        parser_version="b/1",
        priority=10,
    )
    source_b = replace(source_b, people=(), tags=())

    repo.upsert_bundle(source_a, now=NOW)
    repo.upsert_bundle(source_b, now=NOW + timedelta(minutes=1))
    counts = repo.counts()

    assert counts.content_people == 1
    assert counts.content_tags == 1


def test_ingest_run_persists_physical_request_count(monkeypatch, tmp_path: Path) -> None:
    class BudgetCrawler:
        source_id = "fake"

        def __init__(self, **_kwargs) -> None:
            self.fetcher = SimpleNamespace(
                request_budget=SimpleNamespace(used=7)
            )

        def crawl_query(self, _query: str, *, limit: int):
            return []

    monkeypatch.setattr(
        ingest_live_module,
        "get_crawler_factory",
        lambda _source: BudgetCrawler,
    )
    repo = SqliteResourceRepository(tmp_path / "request-count.db")
    repo.init_schema()

    result = ingest_live(
        repo=repo,
        source_id="fake",
        query="x",
        limit=1,
        policy=_policy(),
        run_id="request-count-run",
    )
    stored = repo.conn.execute(
        "SELECT http_requests FROM ingest_runs WHERE run_id = ?",
        ("request-count-run",),
    ).fetchone()[0]

    assert result.http_requests == 7
    assert stored == 7
    repo.close()


def test_crawl_exit_codes_distinguish_partial_and_cancelled() -> None:
    assert _crawl_exit_code("success") == 0
    assert _crawl_exit_code("failed") == 1
    assert _crawl_exit_code("partial") == 2
    assert _crawl_exit_code("cancelled") == 130


def test_existing_v1_database_upgrades_and_backfills(tmp_path: Path) -> None:
    db = tmp_path / "upgrade.db"
    sql_path = (
        Path(__file__).resolve().parents[2]
        / "resource_index"
        / "store"
        / "sql"
        / "0001_resource_index.sql"
    )
    conn = sqlite3.connect(db)
    conn.executescript(sql_path.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT OR REPLACE INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
        ("0001", "2026-07-25T00:00:00Z", file_checksum(sql_path)),
    )
    conn.execute(
        """
        INSERT INTO content_items(
            content_id, content_type, content_code, raw_content_code, title,
            original_title, release_date, duration_minutes, maker_name,
            publisher_name, label_name, series_name, cover_source_url,
            detail_url, adult, source_id, source_item_key, parser_version,
            risk_status, first_seen_at, last_seen_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "adult_video:TST-001",
            "adult_video",
            "TST-001",
            "TST-001",
            "Legacy Title",
            None,
            "2026-07-01",
            120,
            "Maker",
            None,
            None,
            None,
            None,
            "https://legacy.example/TST-001",
            "legacy",
            "/TST-001",
            "legacy/1",
            "manual_review",
            "2026-07-25T00:00:00Z",
            "2026-07-25T00:00:00Z",
            "2026-07-25T00:00:00Z",
            "2026-07-25T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()

    repo = SqliteResourceRepository(db)
    assert repo.init_schema() == "0006"
    row = repo.conn.execute(
        "SELECT source_id, source_title, detail_url FROM content_observations"
    ).fetchone()

    assert dict(row) == {
        "source_id": "legacy",
        "source_title": "Legacy Title",
        "detail_url": "https://legacy.example/TST-001",
    }
    repo.close()
