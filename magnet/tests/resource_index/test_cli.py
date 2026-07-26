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
    assert "schema_version=0007" in r.stdout
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
    assert report["checks"]["sqlite"]["schema_version"] == "0007"

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
    assert {"sixv", "dytt8899", "meijumi"} <= set(source_payload)
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
