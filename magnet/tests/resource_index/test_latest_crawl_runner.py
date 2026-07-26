from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import pytest

from magnet.resource_index.domain.models import ContentCandidate
from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError, StorageError
from magnet.resource_index.pipeline.ingest import IngestResult
from magnet.resource_index.pipeline.latest_crawl import (
    LatestCrawlPaths,
    LatestCrawlRunner,
    PortableRunLock,
    _pid_is_alive,
    read_latest_status,
    run_deployment_doctor,
    select_best_latest_database,
)
from magnet.resource_index.store.migrations import file_checksum
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository
from magnet.tests.resource_index.test_sqlite_repository import NOW, _bundle


class _FakeCrawler:
    def __init__(self, candidates: list[ContentCandidate], http_requests: int = 2) -> None:
        self._candidates = candidates
        self.fetcher = SimpleNamespace(request_budget=SimpleNamespace(used=http_requests))

    def crawl_latest_candidates(
        self,
        *,
        limit: int,
        max_listing_pages: int,
    ) -> list[ContentCandidate]:
        assert max_listing_pages > 0
        return self._candidates[:limit]


def _candidate(rank: int, code: str | None = None, *, url: str | None = None) -> ContentCandidate:
    value = code or f"TST-{rank:03d}"
    detail_url = url or f"https://www.javbus.com/{value}"
    return ContentCandidate(
        raw_title=f"Listing {rank}",
        raw_content_code=value,
        content_code=value,
        detail_url=detail_url,
        cover_source_url=None,
        list_position=rank - 1,
        source_item_key=urlparse(detail_url).path,
    )


def _bundle_for_url(url: str, *, info_seed: int) -> Any:
    code = Path(urlparse(url).path).name.split("_", 1)[0]
    base = _bundle(code=code, info_hash=f"{info_seed:040x}")
    source_key = urlparse(url).path
    return replace(
        base,
        content=replace(base.content, detail_url=url, source_item_key=source_key),
        provenance=replace(
            base.provenance,
            detail_url=url,
            source_item_key=source_key,
        ),
    )


class _CancelledResultIngest:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, **kwargs: Any) -> IngestResult:
        repo: SqliteResourceRepository = kwargs["repo"]
        urls = list(kwargs["detail_urls"])
        run_id = kwargs["run_id"]
        self.calls.append(urls)
        repo.start_ingest_run(run_id, kwargs["source_id"], "live_one_shot", NOW)
        first_url = urls[0]
        stats = repo.upsert_bundle(
            _bundle_for_url(
                first_url,
                info_seed=int(hashlib.sha256(first_url.encode("utf-8")).hexdigest()[:10], 16),
            ),
            now=NOW,
        )
        repo.finish_ingest_run(
            run_id,
            status="cancelled",
            finished_at=NOW,
            documents_seen=1,
            contents_created=int(stats.content_created),
            contents_updated=int(stats.content_updated),
            resources_created=1,
            resources_updated=0,
            warnings=0,
            errors=1,
            error_summary={"INGEST_CANCELLED": 1},
            http_requests=3,
        )
        return IngestResult(
            run_id=run_id,
            status="cancelled",
            documents_seen=1,
            contents_created=int(stats.content_created),
            contents_updated=int(stats.content_updated),
            resources_created=1,
            errors=1,
            error_summary={"INGEST_CANCELLED": 1},
            http_requests=3,
        )


class _FailingIngest:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, **kwargs: Any) -> IngestResult:
        repo: SqliteResourceRepository = kwargs["repo"]
        urls = list(kwargs["detail_urls"])
        run_id = kwargs["run_id"]
        self.calls.append(urls)
        repo.start_ingest_run(run_id, kwargs["source_id"], "live_one_shot", NOW)
        repo.finish_ingest_run(
            run_id,
            status="failed",
            finished_at=NOW,
            documents_seen=len(urls),
            contents_created=0,
            contents_updated=0,
            resources_created=0,
            resources_updated=0,
            warnings=0,
            errors=len(urls),
            error_summary={"LIVE_HTTP_ERROR": len(urls)},
            http_requests=1,
        )
        return IngestResult(
            run_id=run_id,
            status="failed",
            documents_seen=len(urls),
            errors=len(urls),
            error_summary={"LIVE_HTTP_ERROR": len(urls)},
            http_requests=1,
        )


class _RecordingIngest:
    def __init__(self, *, interrupt_first: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.interrupt_first = interrupt_first

    def __call__(self, **kwargs: Any) -> IngestResult:
        repo: SqliteResourceRepository = kwargs["repo"]
        urls = list(kwargs["detail_urls"])
        run_id = kwargs["run_id"]
        self.calls.append(urls)
        repo.start_ingest_run(run_id, kwargs["source_id"], "live_one_shot", NOW)
        created = 0
        for index, url in enumerate(urls):
            if self.interrupt_first and len(self.calls) == 1 and index == 1:
                raise KeyboardInterrupt
            seed = int(hashlib.sha256(url.encode("utf-8")).hexdigest()[:10], 16)
            stats = repo.upsert_bundle(
                _bundle_for_url(url, info_seed=seed),
                now=NOW,
            )
            created += int(stats.content_created)
        repo.finish_ingest_run(
            run_id,
            status="success",
            finished_at=NOW,
            documents_seen=len(urls),
            contents_created=created,
            contents_updated=len(urls) - created,
            resources_created=len(urls),
            resources_updated=0,
            warnings=0,
            errors=0,
            error_summary={},
            http_requests=1 + len(urls) * 2,
        )
        return IngestResult(
            run_id=run_id,
            status="success",
            documents_seen=len(urls),
            contents_created=created,
            contents_updated=len(urls) - created,
            resources_created=len(urls),
            http_requests=1 + len(urls) * 2,
        )


def _runner(
    tmp_path: Path,
    repo: SqliteResourceRepository,
    candidates: list[ContentCandidate],
    ingest: _RecordingIngest,
    *,
    target_count: int = 3,
    batch_size: int = 2,
) -> LatestCrawlRunner:
    return LatestCrawlRunner(
        repo=repo,
        source_id="javbus",
        paths=LatestCrawlPaths.for_output_dir(
            tmp_path / "out",
            source_id="javbus",
            target_count=target_count,
            db_path=repo.db_path,
        ),
        target_count=target_count,
        batch_size=batch_size,
        max_attempts=3,
        delay_seconds=10.0,
        snapshot_max_requests=20,
        batch_max_requests=20,
        crawler_builder=lambda _source, _policy: _FakeCrawler(candidates),
        ingest_fn=ingest,
    )


def test_paths_are_portable_and_deterministic(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "data",
        source_id="javbus",
        target_count=100,
    )
    assert paths.db_path.name == "javbus_latest_100.db"
    assert paths.snapshot_path.name == "javbus_latest_100_urls.json"
    assert paths.feed_path.name == "javbus_latest_100_feed.json"
    assert paths.lock_path.name == "javbus_latest_100.lock"
    assert paths.log_path.name == "javbus_latest_100.log"

    custom_db = tmp_path / "shared" / "portable.db"
    first = LatestCrawlPaths.for_output_dir(
        tmp_path / "one",
        source_id="javbus",
        target_count=100,
        db_path=custom_db,
    )
    second = LatestCrawlPaths.for_output_dir(
        tmp_path / "two",
        source_id="javbus",
        target_count=50,
        db_path=custom_db,
    )
    assert first.lock_path == second.lock_path
    assert first.lock_path.parent == custom_db.parent.resolve()


def test_windows_system_error_from_pid_probe_means_not_running(monkeypatch) -> None:
    def broken_kill(_pid: int, _signal: int) -> None:
        raise SystemError("invalid Windows PID")

    monkeypatch.setattr("os.kill", broken_kill)
    assert _pid_is_alive(99999999) is False


def test_lock_rejects_live_owner_and_recovers_stale_owner(tmp_path: Path) -> None:
    path = tmp_path / "crawl.lock"
    lock = PortableRunLock(path)
    lock.acquire()
    with pytest.raises(RuntimeError):
        PortableRunLock(path).acquire()
    lock.release()

    path.write_text(
        json.dumps(
            {
                "pid": 99999999,
                "hostname": socket.gethostname(),
                "created_at": "2026-07-25T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    recovered = PortableRunLock(path, pid_is_alive=lambda _pid: False)
    recovered.acquire()
    assert recovered.recovered_stale is True
    recovered.release()
    assert not path.exists()


def _write_latest_database(
    path: Path,
    *,
    source_id: str,
    target_count: int,
    covered_count: int,
    status: str,
) -> None:
    repo = SqliteResourceRepository(path)
    repo.init_schema()
    job_id = f"job-{path.stem}"
    now = "2026-07-26T00:00:00Z"
    repo.conn.execute(
        """
        INSERT INTO latest_crawl_jobs(
            job_id, source_id, target_count, batch_size, max_attempts,
            snapshot_hash, snapshot_json, snapshot_path, feed_path,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, 5, 3, ?, '{}', ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            source_id,
            target_count,
            path.stem,
            f"{path}.snapshot.json",
            f"{path}.feed.json",
            status,
            now,
            now,
        ),
    )
    repo.conn.executemany(
        """
        INSERT INTO latest_crawl_items(
            job_id, rank, detail_url, source_item_key, listing_title,
            status, attempts, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """,
        [
            (
                job_id,
                rank,
                f"https://example.test/{rank}",
                f"/{rank}",
                f"Item {rank}",
                "success" if rank <= covered_count else "pending",
                now,
            )
            for rank in range(1, target_count + 1)
        ],
    )
    repo.conn.commit()
    repo.close()


def test_database_selector_prefers_complete_legacy_over_incomplete_exact(tmp_path: Path) -> None:
    exact = tmp_path / "sixv_latest_100.db"
    legacy = tmp_path / "sixv_latest_50.db"
    _write_latest_database(
        exact,
        source_id="sixv",
        target_count=3,
        covered_count=1,
        status="paused",
    )
    _write_latest_database(
        legacy,
        source_id="sixv",
        target_count=3,
        covered_count=3,
        status="success",
    )

    selected = select_best_latest_database(
        [exact, legacy],
        source_id="sixv",
        target_count=3,
    )
    assert selected["selected_path"] == str(legacy.resolve())
    assert selected["selected_existing"] is True


def test_database_selector_prefers_first_candidate_when_evidence_ties(tmp_path: Path) -> None:
    exact = tmp_path / "sixv_latest_100.db"
    legacy = tmp_path / "sixv_latest_50.db"
    for path in (exact, legacy):
        _write_latest_database(
            path,
            source_id="sixv",
            target_count=2,
            covered_count=2,
            status="success",
        )

    selected = select_best_latest_database(
        [exact, legacy],
        source_id="sixv",
        target_count=2,
    )
    assert selected["selected_path"] == str(exact.resolve())


def test_database_selector_falls_back_from_corrupt_candidate(tmp_path: Path) -> None:
    corrupt = tmp_path / "sixv_latest_100.db"
    healthy = tmp_path / "sixv_latest_50.db"
    corrupt.write_bytes(b"not a sqlite database")
    _write_latest_database(
        healthy,
        source_id="sixv",
        target_count=2,
        covered_count=2,
        status="success",
    )

    selected = select_best_latest_database(
        [corrupt, healthy],
        source_id="sixv",
        target_count=2,
    )
    assert selected["selected_path"] == str(healthy.resolve())
    assert selected["candidates"][0]["healthy"] is False


def test_database_selector_rejects_any_live_candidate_lock(tmp_path: Path) -> None:
    exact = tmp_path / "sixv_latest_100.db"
    legacy = tmp_path / "sixv_latest_50.db"
    _write_latest_database(
        legacy,
        source_id="sixv",
        target_count=2,
        covered_count=2,
        status="success",
    )
    exact.with_suffix(".lock").write_text(
        json.dumps({"pid": os.getpid(), "hostname": socket.gethostname()}),
        encoding="utf-8",
    )

    with pytest.raises(ResourceIndexError, match="already in use"):
        select_best_latest_database(
            [exact, legacy],
            source_id="sixv",
            target_count=2,
        )


def test_snapshot_preserves_duplicate_codes_but_deduplicates_urls(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    repo.init_schema()
    candidates = [
        _candidate(1, "DUP-001", url="https://www.javbus.com/DUP-001"),
        _candidate(2, "DUP-001", url="https://www.javbus.com/DUP-001_2026-07-25"),
        _candidate(3, "DUP-001", url="https://www.javbus.com/DUP-001"),
    ]
    runner = _runner(tmp_path, repo, candidates, _RecordingIngest(), target_count=2)
    result = runner.run(refresh=True, max_batches=0)
    payload = json.loads(runner.paths.snapshot_path.read_text(encoding="utf-8"))
    assert result.status == "pending"
    assert [item["rank"] for item in payload["items"]] == [1, 2]
    assert len({item["detail_url"] for item in payload["items"]}) == 2
    assert len({item["content_code"] for item in payload["items"]}) == 1
    repo.close()


def test_interrupted_batch_resumes_only_missing_urls(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    repo.init_schema()
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    interrupted = _RecordingIngest(interrupt_first=True)
    runner = _runner(tmp_path, repo, candidates, interrupted)

    with pytest.raises(KeyboardInterrupt):
        runner.run(refresh=True)

    state = runner.job_store.get_job(runner.current_job_id)
    assert state["status"] == "paused"
    assert repo.conn.execute(
        "SELECT COUNT(*) FROM content_observations"
    ).fetchone()[0] == 1
    assert not runner.paths.lock_path.exists()

    resumed = _RecordingIngest()
    second = _runner(tmp_path, repo, candidates, resumed)
    result = second.run(refresh=False)
    assert result.status == "success"
    assert result.covered_count == 3
    assert resumed.calls == [
        [
            "https://www.javbus.com/TST-002",
            "https://www.javbus.com/TST-003",
        ]
    ]
    assert repo.conn.execute(
        "SELECT COUNT(*) FROM ingest_runs WHERE status = 'running'"
    ).fetchone()[0] == 0
    repo.close()


def test_cancelled_result_pauses_immediately_and_resumes_missing_urls(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    repo.init_schema()
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    cancelled = _CancelledResultIngest()
    runner = LatestCrawlRunner(
        repo=repo,
        source_id="javbus",
        paths=LatestCrawlPaths.for_output_dir(
            tmp_path / "out",
            source_id="javbus",
            target_count=3,
            db_path=repo.db_path,
        ),
        target_count=3,
        batch_size=2,
        max_attempts=3,
        delay_seconds=10.0,
        snapshot_max_requests=20,
        batch_max_requests=20,
        crawler_builder=lambda _source, _policy: _FakeCrawler(candidates),
        ingest_fn=cancelled,
    )
    with pytest.raises(KeyboardInterrupt):
        runner.run(refresh=True)
    assert cancelled.calls == [[
        "https://www.javbus.com/TST-001",
        "https://www.javbus.com/TST-002",
    ]]
    job = runner.job_store.get_job(runner.current_job_id)
    assert job["status"] == "paused"
    assert runner.job_store.summary(runner.current_job_id)["covered_count"] == 1

    resumed = _RecordingIngest()
    second = LatestCrawlRunner(
        repo=repo,
        source_id="javbus",
        paths=runner.paths,
        target_count=3,
        batch_size=2,
        max_attempts=3,
        delay_seconds=10.0,
        snapshot_max_requests=20,
        batch_max_requests=20,
        crawler_builder=lambda _source, _policy: _FakeCrawler(candidates),
        ingest_fn=resumed,
    )
    result = second.run(refresh=False)
    assert result.status == "success"
    assert resumed.calls == [[
        "https://www.javbus.com/TST-002",
        "https://www.javbus.com/TST-003",
    ]]
    repo.close()


def test_failed_items_are_attempted_once_per_invocation(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    repo.init_schema()
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    failing = _FailingIngest()
    runner = LatestCrawlRunner(
        repo=repo,
        source_id="javbus",
        paths=LatestCrawlPaths.for_output_dir(
            tmp_path / "out",
            source_id="javbus",
            target_count=3,
            db_path=repo.db_path,
        ),
        target_count=3,
        batch_size=2,
        max_attempts=3,
        delay_seconds=10.0,
        snapshot_max_requests=20,
        batch_max_requests=20,
        crawler_builder=lambda _source, _policy: _FakeCrawler(candidates),
        ingest_fn=failing,
    )
    first = runner.run(refresh=True)
    assert first.status == "pending"
    assert failing.calls == [
        ["https://www.javbus.com/TST-001", "https://www.javbus.com/TST-002"],
        ["https://www.javbus.com/TST-003"],
    ]
    assert {
        row["attempts"] for row in runner.job_store.items(runner.current_job_id)
    } == {1}

    second = runner.run(refresh=False)
    assert second.status == "pending"
    assert {
        row["attempts"] for row in runner.job_store.items(runner.current_job_id)
    } == {2}

    third = runner.run(refresh=False)
    assert third.status == "partial"
    assert {
        row["attempts"] for row in runner.job_store.items(runner.current_job_id)
    } == {3}
    repo.close()


def test_completed_job_is_idempotent_no_network_replay(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    repo.init_schema()
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    ingest = _RecordingIngest()
    runner = _runner(tmp_path, repo, candidates, ingest)
    first = runner.run(refresh=True)
    assert first.status == "success"
    calls_after_first = list(ingest.calls)

    second = _runner(tmp_path, repo, candidates, ingest)
    result = second.run(refresh=False)
    assert result.status == "success"
    assert ingest.calls == calls_after_first
    assert result.covered_count == 3
    repo.close()


def test_max_batches_allows_short_foreground_slices(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    repo.init_schema()
    candidates = [_candidate(i) for i in range(1, 6)]
    ingest = _RecordingIngest()
    runner = _runner(
        tmp_path,
        repo,
        candidates,
        ingest,
        target_count=5,
        batch_size=2,
    )
    first = runner.run(refresh=True, max_batches=1)
    assert first.status == "pending"
    assert first.covered_count == 2
    status = read_latest_status(
        repo=repo,
        paths=runner.paths,
        source_id="javbus",
        target_count=5,
    )
    assert status["status"] == "pending"
    assert status["covered_count"] == 2
    assert len(status["unresolved"]) == 3
    second = _runner(
        tmp_path,
        repo,
        candidates,
        ingest,
        target_count=5,
        batch_size=2,
    ).run(refresh=False)
    assert second.status == "success"
    assert second.covered_count == 5
    repo.close()


def test_feed_is_atomic_ranked_and_has_full_coverage(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    repo.init_schema()
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    runner = _runner(tmp_path, repo, candidates, _RecordingIngest())
    result = runner.run(refresh=True)
    feed = json.loads(runner.paths.feed_path.read_text(encoding="utf-8"))
    assert result.status == "success"
    assert feed["summary"]["record_count"] == 3
    assert feed["summary"]["missing_urls"] == []
    assert [item["rank"] for item in feed["items"]] == [1, 2, 3]
    assert not list(runner.paths.feed_path.parent.glob("*.tmp-*"))
    repo.close()


def test_resume_after_directory_move_updates_stored_paths(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "shared.db")
    repo.init_schema()
    candidates = [_candidate(1), _candidate(2)]
    first = _runner(
        tmp_path / "first",
        repo,
        candidates,
        _RecordingIngest(),
        target_count=2,
    )
    first.run(refresh=True, max_batches=0)

    moved_paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "moved",
        source_id="javbus",
        target_count=2,
        db_path=repo.db_path,
    )
    moved_paths.output_dir.mkdir(parents=True, exist_ok=True)
    moved_paths.snapshot_path.write_bytes(first.paths.snapshot_path.read_bytes())
    moved = LatestCrawlRunner(
        repo=repo,
        source_id="javbus",
        paths=moved_paths,
        target_count=2,
        batch_size=2,
        max_attempts=3,
        delay_seconds=10.0,
        snapshot_max_requests=20,
        batch_max_requests=20,
        crawler_builder=lambda _source, _policy: _FakeCrawler(candidates),
        ingest_fn=_RecordingIngest(),
    )
    moved.run(refresh=False, max_batches=0)
    job = moved.job_store.get_job(moved.current_job_id)
    assert job["snapshot_path"] == str(moved_paths.snapshot_path)
    assert job["feed_path"] == str(moved_paths.feed_path)
    repo.close()


def test_runner_rejects_lock_path_for_a_different_database(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "actual.db")
    repo.init_schema()
    with pytest.raises(ResourceIndexError) as exc:
        LatestCrawlRunner(
            repo=repo,
            source_id="javbus",
            paths=LatestCrawlPaths.for_output_dir(
                tmp_path / "out",
                source_id="javbus",
                target_count=5,
                db_path=tmp_path / "different.db",
            ),
            target_count=5,
            batch_size=2,
            batch_max_requests=20,
        )
    assert exc.value.error_code == CONFIG_ERROR
    repo.close()


def test_batch_request_budget_must_cover_base_batch_shape(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    repo.init_schema()
    with pytest.raises(ResourceIndexError) as exc:
        LatestCrawlRunner(
            repo=repo,
            source_id="javbus",
            paths=LatestCrawlPaths.for_output_dir(
                tmp_path / "out",
                source_id="javbus",
                target_count=5,
                db_path=repo.db_path,
            ),
            target_count=5,
            batch_size=5,
            batch_max_requests=12,
        )
    assert exc.value.error_code == CONFIG_ERROR
    repo.close()


def test_status_rejects_corrupted_or_wrong_scope_snapshot(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    repo.init_schema()
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="javbus",
        target_count=3,
        db_path=repo.db_path,
    )
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_id": "other",
                "target_count": 3,
                "items": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ResourceIndexError):
        read_latest_status(
            repo=repo,
            paths=paths,
            source_id="javbus",
            target_count=3,
        )
    repo.close()


def test_doctor_checks_minimal_runtime_and_writable_paths(tmp_path: Path) -> None:
    report = run_deployment_doctor(
        output_dir=tmp_path / "out",
        db_path=tmp_path / "out" / "doctor.db",
        source_id="javbus",
    )
    assert report["status"] == "pass"
    assert report["checks"]["python"]["ok"] is True
    assert report["checks"]["curl_cffi"]["ok"] is True
    assert report["checks"]["beautifulsoup4"]["ok"] is True
    assert report["checks"]["sqlite"]["ok"] is True
    assert report["checks"]["writable_output"]["ok"] is True
    assert report["checks"]["source_registry"]["ok"] is True


def test_schema_0007_contains_latest_job_tables(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "m.db")
    assert repo.init_schema() == "0008"
    tables = {
        row[0]
        for row in repo.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {"latest_crawl_jobs", "latest_crawl_items"} <= tables
    repo.close()


def _create_schema_through_0006(db: Path) -> None:
    sql_dir = Path(__file__).resolve().parents[2] / "resource_index" / "store" / "sql"
    connection = sqlite3.connect(db)
    for version in range(1, 7):
        path = next(sql_dir.glob(f"{version:04d}_*.sql"))
        connection.executescript(path.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT OR REPLACE INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
            (f"{version:04d}", "2026-07-25T00:00:00Z", file_checksum(path)),
        )
    connection.commit()
    connection.close()


def test_legacy_0007_imdb_collision_is_structurally_verified_and_reconciled(tmp_path: Path) -> None:
    db = tmp_path / "legacy-imdb-0007.db"
    _create_schema_through_0006(db)
    connection = sqlite3.connect(db)
    connection.execute("ALTER TABLE movie_items ADD COLUMN imdb_rating REAL")
    connection.execute("ALTER TABLE movie_items ADD COLUMN imdb_rating_text TEXT")
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
        (
            "0007",
            "2026-07-26T00:00:00Z",
            "9316572ec726f5910e4ad3bae98aebd40d9c5e5dc1b72bb4d0c63bb2013c8fa9",
        ),
    )
    connection.commit()
    connection.close()

    repo = SqliteResourceRepository(db)
    assert repo.init_schema() == "0008"
    movie_columns = {row[1] for row in repo.conn.execute("PRAGMA table_xinfo(movie_items)")}
    latest_columns = {row[1] for row in repo.conn.execute("PRAGMA table_xinfo(latest_crawl_items)")}
    indexes = {
        row[0]
        for row in repo.conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert {"imdb_rating", "imdb_rating_text", "content_kind", "brand_id", "season_number"} <= movie_columns
    assert "source_item_key" in latest_columns
    assert {"idx_movie_items_kind_update", "idx_latest_crawl_items_source_key"} <= indexes
    versions = {row[0] for row in repo.conn.execute("SELECT version FROM schema_migrations")}
    assert {"0007", "0008", "0007_legacy_imdb_rating_9316572e"} <= versions
    assert repo.init_schema() == "0008"
    repo.close()


def test_legacy_0007_checksum_without_approved_structure_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "invalid-legacy-0007.db"
    _create_schema_through_0006(db)
    connection = sqlite3.connect(db)
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
        (
            "0007",
            "2026-07-26T00:00:00Z",
            "9316572ec726f5910e4ad3bae98aebd40d9c5e5dc1b72bb4d0c63bb2013c8fa9",
        ),
    )
    connection.commit()
    connection.close()

    repo = SqliteResourceRepository(db)
    with pytest.raises(StorageError, match="approved fingerprint"):
        repo.init_schema()
    repo.close()


def test_existing_schema_0002_upgrades_without_content_loss(tmp_path: Path) -> None:
    db = tmp_path / "upgrade.db"
    sql_dir = Path(__file__).resolve().parents[2] / "resource_index" / "store" / "sql"
    sql_1 = sql_dir / "0001_resource_index.sql"
    sql_2 = sql_dir / "0002_content_observations.sql"
    connection = sqlite3.connect(db)
    connection.executescript(sql_1.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT OR REPLACE INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
        ("0001", "2026-07-25T00:00:00Z", file_checksum(sql_1)),
    )
    connection.executescript(sql_2.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT OR REPLACE INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
        ("0002", "2026-07-25T00:00:00Z", file_checksum(sql_2)),
    )
    connection.execute(
        """
        INSERT INTO content_items(
            content_id, content_type, content_code, raw_content_code, title,
            detail_url, adult, source_id, source_item_key, parser_version,
            risk_status, first_seen_at, last_seen_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'manual_review', ?, ?, ?, ?)
        """,
        (
            "adult_video:OLD-001",
            "adult_video",
            "OLD-001",
            "OLD-001",
            "Old Title",
            "https://www.javbus.com/OLD-001",
            "javbus",
            "/OLD-001",
            "legacy/1",
            "2026-07-25T00:00:00Z",
            "2026-07-25T00:00:00Z",
            "2026-07-25T00:00:00Z",
            "2026-07-25T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    repo = SqliteResourceRepository(db)
    assert repo.init_schema() == "0008"
    assert repo.conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 1
    assert repo.conn.execute(
        "SELECT COUNT(*) FROM latest_crawl_jobs"
    ).fetchone()[0] == 0
    repo.close()
