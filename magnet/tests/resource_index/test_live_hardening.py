from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import magnet.resource_index.pipeline.ingest_live as ingest_live_module
from magnet.resource_index.acquisition.fixture_reader import sha256_file
from magnet.resource_index.acquisition.http_client import LiveHttpClient
from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.javbus.live_crawler import CrawlItemResult, JavBusLiveCrawler
from magnet.resource_index.domain.models import ParseProvenance, ParseWarning
from magnet.resource_index.errors import (
    AGE_GATE_PAGE,
    CONFIG_ERROR,
    LIVE_EMPTY_RESULT,
    LIVE_FETCH_DISABLED,
    LIVE_HTTP_ERROR,
    LIVE_RATE_LIMITED,
    LIVE_URL_REJECTED,
    LivePolicyError,
    ResourceIndexError,
)
from magnet.resource_index.pipeline.ingest_live import ingest_live
from magnet.resource_index.store.migrations import file_checksum
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository, _iso
from magnet.tests.resource_index.test_sqlite_repository import NOW, _bundle


class _SequenceSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.cookies = {}

    def request(self, *_args, **_kwargs):
        self.calls += 1
        item = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


class _NoopClient:
    def __init__(self):
        self.calls: list[str] = []

    def cookies_snapshot(self):
        return {}

    def clear_cookies(self):
        return None

    def get(self, url: str, **_kwargs):
        self.calls.append(url)
        return SimpleNamespace(url=url, status_code=200, text='<a class="movie-box"></a>', headers={})

    def post(self, url: str, **_kwargs):
        self.calls.append(url)
        return SimpleNamespace(url=url, status_code=200, text='<a class="movie-box"></a>', headers={})


def _response(status: int, body: str, url: str = "https://www.javbus.com/"):
    return SimpleNamespace(status_code=status, text=body, url=url, headers={})


def _public_resolver(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34"]


def _allowed_policy(*, max_pages: int = 20, delay: float = 10.0) -> LiveFetchPolicy:
    return LiveFetchPolicy(
        enabled=True,
        acknowledged=True,
        max_pages=max_pages,
        request_delay_seconds=delay,
        concurrency=1,
    )


def test_text_hashes_are_line_ending_stable(tmp_path: Path):
    lf = tmp_path / "a.html"
    crlf = tmp_path / "b.html"
    lf.write_bytes(b"<html>\n<body>x</body>\n</html>\n")
    crlf.write_bytes(b"<html>\r\n<body>x</body>\r\n</html>\r\n")
    assert sha256_file(lf) == sha256_file(crlf)
    assert file_checksum(lf) == file_checksum(crlf)


def test_library_crawler_defaults_to_disabled():
    client = _NoopClient()
    crawler = JavBusLiveCrawler(client=client)  # type: ignore[arg-type]
    with pytest.raises(LivePolicyError) as exc:
        crawler.ensure_session()
    assert exc.value.error_code == LIVE_FETCH_DISABLED
    assert client.calls == []


def test_policy_rejects_invalid_limits_without_clamping():
    with pytest.raises(LivePolicyError) as exc:
        _allowed_policy(max_pages=0).assert_allowed()
    assert exc.value.error_code == LIVE_RATE_LIMITED
    with pytest.raises(LivePolicyError) as exc:
        _allowed_policy(delay=1.5).assert_allowed()
    assert exc.value.error_code == LIVE_RATE_LIMITED


def test_limit_zero_rejected_before_network():
    client = _NoopClient()
    crawler = JavBusLiveCrawler(policy=_allowed_policy(), client=client)  # type: ignore[arg-type]
    with pytest.raises(ResourceIndexError) as exc:
        crawler.crawl_query("TST", limit=0)
    assert exc.value.error_code == CONFIG_ERROR
    assert client.calls == []


def test_page_budget_counts_session_requests():
    class AgeGateClient(_NoopClient):
        def get(self, url: str, **_kwargs):
            self.calls.append(url)
            return SimpleNamespace(
                url="https://www.javbus.com/doc/driver-verify",
                status_code=200,
                text="<html>driver-verify Age Verification 確認</html>",
                headers={},
            )

    client = AgeGateClient()
    crawler = JavBusLiveCrawler(policy=_allowed_policy(max_pages=1), client=client)  # type: ignore[arg-type]
    with pytest.raises(LivePolicyError) as exc:
        crawler.ensure_session()
    assert exc.value.error_code == LIVE_RATE_LIMITED
    assert len(client.calls) == 1


def test_http_retries_5xx_then_succeeds():
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=2,
        allowed_origins={"https://www.javbus.com:443"},
        dns_resolver=_public_resolver,
    )
    client._session = _SequenceSession([
        _response(500, "server error"),
        _response(503, "busy"),
        _response(200, "ok"),
    ])
    response = client.get("https://www.javbus.com/")
    assert response.status_code == 200
    assert client._session.calls == 3


def test_http_5xx_exhaustion_is_structured_error():
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=1,
        allowed_origins={"https://www.javbus.com:443"},
        dns_resolver=_public_resolver,
    )
    client._session = _SequenceSession([_response(500, "server error")])
    with pytest.raises(ResourceIndexError) as exc:
        client.get("https://www.javbus.com/")
    assert exc.value.error_code == LIVE_HTTP_ERROR
    assert client._session.calls == 2


def test_mid_crawl_age_gate_hard_stops_client():
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=0,
        allowed_origins={"https://www.javbus.com:443"},
        dns_resolver=_public_resolver,
    )
    client._session = _SequenceSession([
        _response(200, '<html>driver-verify Age Verification 確認</html>')
    ])
    with pytest.raises(LivePolicyError) as exc:
        client.get("https://www.javbus.com/search/TST")
    assert exc.value.error_code == AGE_GATE_PAGE
    assert client.stopped_reason == "age_gate"


def test_url_allowlist_rejects_private_or_foreign_hosts_before_request():
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=0,
        allowed_origins={"https://www.javbus.com:443"},
        dns_resolver=_public_resolver,
    )
    client._session = _SequenceSession([_response(200, "ok")])
    with pytest.raises(LivePolicyError) as exc:
        client.get("http://127.0.0.1:8080/admin")
    assert exc.value.error_code == LIVE_URL_REJECTED
    assert client._session.calls == 0


def test_redirect_target_is_revalidated():
    client = LiveHttpClient(
        request_delay_seconds=0,
        max_retries=0,
        allowed_origins={"https://www.javbus.com:443"},
        dns_resolver=_public_resolver,
    )
    client._session = _SequenceSession([
        _response(200, "ok", url="http://127.0.0.1/admin")
    ])
    with pytest.raises(LivePolicyError) as exc:
        client.get("https://www.javbus.com/")
    assert exc.value.error_code == LIVE_URL_REJECTED


def test_unexpected_crawl_exception_finishes_run(monkeypatch, tmp_path: Path):
    class BoomCrawler:
        source_id = "fake"

        def __init__(self, **_kwargs):
            pass

        def crawl_query(self, _query: str, *, limit: int):
            raise RuntimeError("boom")

    monkeypatch.setattr(ingest_live_module, "get_crawler_factory", lambda _source: BoomCrawler)
    repo = SqliteResourceRepository(tmp_path / "unexpected.db")
    repo.init_schema()
    result = ingest_live(
        repo=repo,
        source_id="fake",
        query="x",
        limit=1,
        policy=_allowed_policy(),
        run_id="unexpected-run",
    )
    row = repo.conn.execute(
        "SELECT status, finished_at, errors, error_summary_json FROM ingest_runs WHERE run_id = ?",
        ("unexpected-run",),
    ).fetchone()
    assert result.status == "failed"
    assert row["status"] == "failed"
    assert row["finished_at"] is not None
    assert row["errors"] == 1
    assert "UNEXPECTED" in row["error_summary_json"]
    repo.close()


def test_empty_live_result_is_not_success(monkeypatch, tmp_path: Path):
    class EmptyCrawler:
        source_id = "fake"

        def __init__(self, **_kwargs):
            pass

        def crawl_query(self, _query: str, *, limit: int):
            return []

    monkeypatch.setattr(ingest_live_module, "get_crawler_factory", lambda _source: EmptyCrawler)
    repo = SqliteResourceRepository(tmp_path / "empty.db")
    repo.init_schema()
    result = ingest_live(
        repo=repo,
        source_id="fake",
        query="x",
        limit=1,
        policy=_allowed_policy(),
    )
    assert result.status == "failed"
    assert result.error_summary == {LIVE_EMPTY_RESULT: 1}
    repo.close()


def test_partial_relation_parse_does_not_erase_existing(repo: SqliteResourceRepository):
    full = _bundle()
    repo.upsert_bundle(full, now=NOW)
    partial = replace(
        full,
        people=(),
        tags=(),
        provenance=replace(
            full.provenance,
            internal={"relation_presence": {"people": False, "tags": False}},
        ),
    )
    repo.upsert_bundle(partial, now=NOW + timedelta(minutes=1))
    counts = repo.counts()
    assert counts.content_people == 1
    assert counts.content_tags == 1


def test_explicit_observed_empty_relations_can_clear(repo: SqliteResourceRepository):
    full = _bundle()
    repo.upsert_bundle(full, now=NOW)
    explicit_empty = replace(
        full,
        people=(),
        tags=(),
        provenance=replace(
            full.provenance,
            internal={"relation_presence": {"people": True, "tags": True}},
        ),
    )
    repo.upsert_bundle(explicit_empty, now=NOW + timedelta(minutes=1))
    counts = repo.counts()
    assert counts.content_people == 0
    assert counts.content_tags == 0


def test_registry_listing_path_is_not_javbus_type_coupled(monkeypatch, tmp_path: Path):
    bundle = _bundle(code="TST-777")

    class GenericCrawler:
        source_id = "generic"

        def __init__(self, **_kwargs):
            pass

        def crawl_listing_page(self, page_url=None, *, limit: int):
            return [
                CrawlItemResult(
                    content_code="TST-777",
                    detail_url="https://generic.invalid/TST-777",
                    bundle=bundle,
                )
            ]

    monkeypatch.setattr(ingest_live_module, "get_crawler_factory", lambda _source: GenericCrawler)
    repo = SqliteResourceRepository(tmp_path / "generic.db")
    repo.init_schema()
    result = ingest_live(
        repo=repo,
        source_id="generic",
        listing_url="https://generic.invalid/list",
        limit=1,
        policy=_allowed_policy(),
    )
    assert result.status == "success"
    assert result.contents_created == 1
    repo.close()


def test_live_warnings_are_persisted_and_summarized(monkeypatch, tmp_path: Path):
    base = _bundle(code="TST-888")
    bundle = replace(
        base,
        warnings=(ParseWarning("TEST_WARNING", "warning", {}),),
    )

    class WarningCrawler:
        source_id = "fake"

        def __init__(self, **_kwargs):
            pass

        def crawl_query(self, _query: str, *, limit: int):
            return [
                CrawlItemResult(
                    content_code="TST-888",
                    detail_url="https://fake.invalid/TST-888",
                    bundle=bundle,
                )
            ]

    monkeypatch.setattr(ingest_live_module, "get_crawler_factory", lambda _source: WarningCrawler)
    repo = SqliteResourceRepository(tmp_path / "warning.db")
    repo.init_schema()
    result = ingest_live(
        repo=repo,
        source_id="fake",
        query="x",
        limit=1,
        policy=_allowed_policy(),
    )
    assert result.status == "success"
    assert result.warnings == 1
    assert result.error_summary == {"TEST_WARNING": 1}
    assert repo.warning_counts() == {"TEST_WARNING": 1}
    repo.close()


def test_iso_serializes_aware_datetime_as_utc():
    local = datetime(2026, 7, 25, 10, 0, tzinfo=timezone(timedelta(hours=8)))
    assert _iso(local) == "2026-07-25T02:00:00Z"
