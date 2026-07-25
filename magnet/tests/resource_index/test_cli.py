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
    assert "schema_version=0001" in r.stdout
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
