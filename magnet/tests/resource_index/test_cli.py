"""CLI smoke tests."""

import json
import subprocess
import sys
from pathlib import Path

from magnet.tests.resource_index.conftest import MANIFEST_PATH


def test_cli_demo_loop(tmp_path: Path):
    db = tmp_path / "cli.db"
    feed = tmp_path / "feed.json"
    py = sys.executable

    r = subprocess.run(
        [py, "-m", "magnet.resource_index.cli", "init-db", "--db", str(db)],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "schema_version=0008" in r.stdout
    assert "status=ready" in r.stdout

    r = subprocess.run(
        [
            py,
            "-m",
            "magnet.resource_index.cli",
            "ingest-fixture",
            "--source",
            "javbus",
            "--manifest",
            str(MANIFEST_PATH),
            "--db",
            str(db),
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "contents_created=" in r.stdout

    # second import
    r = subprocess.run(
        [
            py,
            "-m",
            "magnet.resource_index.cli",
            "ingest-fixture",
            "--source",
            "javbus",
            "--manifest",
            str(MANIFEST_PATH),
            "--db",
            str(db),
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout

    r = subprocess.run(
        [py, "-m", "magnet.resource_index.cli", "stats", "--db", str(db)],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    stats = json.loads(r.stdout)
    assert stats["contents"] >= 6

    r = subprocess.run(
        [
            py,
            "-m",
            "magnet.resource_index.cli",
            "show-content",
            "TST-001",
            "--db",
            str(db),
            "--pretty",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    content = json.loads(r.stdout)
    assert content["content_code"] == "TST-001"

    r = subprocess.run(
        [
            py,
            "-m",
            "magnet.resource_index.cli",
            "export-feed",
            "--scope",
            "adult",
            "--db",
            str(db),
            "--output",
            str(feed),
            "--include-review-fixtures",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(feed.read_text(encoding="utf-8"))
    assert data["scope"] == "adult"
    assert all(i["adult"] is True for i in data["items"])


def test_cli_doctor_and_latest_policy_gate(tmp_path: Path):
    py = sys.executable
    root = str(Path(__file__).resolve().parents[3])
    output = tmp_path / "portable"

    doctor = subprocess.run(
        [
            py,
            "-B",
            "-m",
            "magnet.resource_index.cli",
            "doctor",
            "--source",
            "javbus",
            "--count",
            "100",
            "--output-dir",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert doctor.returncode == 0, doctor.stderr + doctor.stdout
    report = json.loads(doctor.stdout)
    assert report["status"] == "pass"
    assert report["checks"]["sqlite"]["schema_version"] == "0008"

    gated = subprocess.run(
        [
            py,
            "-B",
            "-m",
            "magnet.resource_index.cli",
            "crawl-latest",
            "--source",
            "javbus",
            "--count",
            "3",
            "--output-dir",
            str(output),
            "--max-batches",
            "0",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert gated.returncode == 1
    assert "LIVE_POLICY_NOT_ACKNOWLEDGED" in gated.stderr


def test_cli_lists_movie_brands_and_gates_live_probe() -> None:
    py = sys.executable
    root = str(Path(__file__).resolve().parents[3])
    sources = subprocess.run(
        [py, "-B", "-m", "magnet.resource_index.cli", "list-movie-sources"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sources.returncode == 0
    source_payload = json.loads(sources.stdout)
    assert {"sixv", "dytt8899", "sixv-series", "meijumi"} <= set(source_payload)
    assert source_payload["sixv"]["default_count"] == 100
    assert source_payload["dytt8899"]["default_count"] == 250
    assert source_payload["dytt8899"]["publish_count"] == 100
    assert source_payload["sixv-series"]["default_count"] == 100
    assert source_payload["meijumi"]["default_count"] == 100
    assert source_payload["meijumi"]["content_kind"] == "series"

    brands = subprocess.run(
        [py, "-B", "-m", "magnet.resource_index.cli", "list-movie-brands"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert brands.returncode == 0
    brand_payload = json.loads(brands.stdout)
    assert brand_payload["sixv"]["strategy"] == "mirror_family"
    assert brand_payload["meijumi"]["content_kinds"] == [
        "series",
        "documentary",
        "anime",
        "variety",
    ]

    gated = subprocess.run(
        [py, "-B", "-m", "magnet.resource_index.cli", "probe-movie-brands", "--brand", "sixv"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert gated.returncode == 1
    assert "LIVE_POLICY_NOT_ACKNOWLEDGED" in gated.stderr


def test_cli_strict_media_quota_and_duplicate_source_count_fail_cleanly(tmp_path: Path) -> None:
    py = sys.executable
    root = str(Path(__file__).resolve().parents[3])
    feed = tmp_path / "movie-feed.json"
    feed.write_text(
        json.dumps(
            {
                "schema_version": "movie-feed/1",
                "source_id": "sixv",
                "items": [
                    {
                        "rank": 1,
                        "source_id": "sixv",
                        "brand_id": "sixv",
                        "source_item_key": "/dy/1.html",
                        "detail_url": "https://www.6v520.com/dy/1.html",
                        "content_kind": "movie",
                        "title": "唯一电影",
                        "year": 2026,
                        "update_date": "2026-07-26",
                        "resources": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    strict = subprocess.run(
        [
            py,
            "-B",
            "-m",
            "magnet.resource_index.cli",
            "aggregate-media-feeds",
            "--feed",
            str(feed),
            "--output",
            str(tmp_path / "combined.json"),
            "--movie-limit",
            "1",
            "--series-limit",
            "1",
            "--strict-kind-limits",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert strict.returncode == 1
    assert "error_code=CONFIG_ERROR" in strict.stderr
    assert "strict kind limits" in strict.stderr
    assert "Traceback" not in strict.stderr

    duplicate = subprocess.run(
        [
            py,
            "-B",
            "-m",
            "magnet.resource_index.cli",
            "movie-sources-status",
            "--source",
            "sixv",
            "--source-count",
            "sixv=100",
            "--source-count",
            "sixv=50",
            "--output-dir",
            str(tmp_path / "status"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert duplicate.returncode == 1
    assert "duplicate per-source count override" in duplicate.stderr
    assert "Traceback" not in duplicate.stderr


def test_cli_select_latest_database_path_only_prefers_first_missing_candidate(tmp_path: Path) -> None:
    py = sys.executable
    root = str(Path(__file__).resolve().parents[3])
    exact = tmp_path / "sixv_latest_100.db"
    legacy = tmp_path / "sixv_latest_50.db"
    result = subprocess.run(
        [
            py,
            "-B",
            "-m",
            "magnet.resource_index.cli",
            "select-latest-database",
            "--source",
            "sixv",
            "--count",
            "100",
            "--candidate",
            str(exact),
            "--candidate",
            str(legacy),
            "--path-only",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == str(exact.resolve())
    assert result.stderr == ""
