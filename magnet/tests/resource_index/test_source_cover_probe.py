from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from magnet.resource_index.pipeline.source_cover_probe import probe_source_covers


def _image_bytes(seed: int = 0) -> bytes:
    image = Image.new("RGB", (600, 900), (seed % 255, (seed * 17) % 255, (seed * 31) % 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _feed(path: Path, count: int = 2) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "movie-feed/1",
                "source_id": "fixture",
                "items": [
                    {
                        "movie_id": f"movie:{index}",
                        "title": f"Fixture {index}",
                        "detail_url": f"https://fixture.example/{index}",
                        "cover_source_url": f"https://images.example/{index}.png",
                    }
                    for index in range(count)
                ],
            }
        ),
        encoding="utf-8",
    )


def test_source_cover_probe_downloads_and_reuses_all_assets(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    output = tmp_path / "covers"
    _feed(feed)
    calls: list[str] = []

    def fetch(url: str, referer: str | None) -> bytes:
        calls.append(url)
        assert referer and referer.startswith("https://fixture.example/")
        return _image_bytes(int(url.rsplit("/", 1)[-1].split(".", 1)[0]))

    first = probe_source_covers(
        feed_path=feed,
        output_dir=output,
        expected_count=2,
        fetcher=fetch,
    )
    assert first.status == "pass"
    assert first.verified_count == 2
    assert first.downloaded_count == 2
    assert len(calls) == 2
    assert len(list((output / "covers").glob("*.jpg"))) == 2

    calls.clear()
    second = probe_source_covers(
        feed_path=feed,
        output_dir=output,
        expected_count=2,
        fetcher=fetch,
    )
    assert second.status == "pass"
    assert second.downloaded_count == 0
    assert second.reused_count == 2
    assert calls == []


def test_source_cover_probe_rejects_placeholder_cover_reuse(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    _feed(feed, count=10)
    result = probe_source_covers(
        feed_path=feed,
        output_dir=tmp_path / "covers",
        expected_count=10,
        minimum_unique_ratio=0.9,
        fetcher=lambda _url, _referer: _image_bytes(),
    )
    assert result.status == "fail"
    assert result.verified_count == 10
    assert result.unique_cover_asset_count == 1
    assert result.unique_cover_ratio == 0.1


def test_source_cover_probe_reports_invalid_image(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    _feed(feed, count=1)
    result = probe_source_covers(
        feed_path=feed,
        output_dir=tmp_path / "covers",
        expected_count=1,
        fetcher=lambda _url, _referer: b"not-an-image",
    )
    assert result.status == "fail"
    assert result.failed_count == 1
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert report["failures"][0]["reason"] == "CONFIG_ERROR"
