from __future__ import annotations

import json
from pathlib import Path

from magnet.resource_index.pipeline.source_resource_probe import (
    ResourceProbeResponse,
    probe_source_resources,
)


def _feed(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "movie-feed/1",
                "source_id": "fixture",
                "items": [
                    {
                        "movie_id": "movie:1",
                        "title": "Fixture",
                        "resources": [
                            {
                                "resource_type": "magnet",
                                "provider": "magnet",
                                "url": "magnet:?xt=urn:btih:1111111111111111111111111111111111111111",
                            },
                            {
                                "resource_type": "player",
                                "provider": "m3u8",
                                "url": "https://video.example/1.m3u8",
                            },
                            {
                                "resource_type": "cloud",
                                "provider": "quark",
                                "url": "https://pan.example/share",
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_resource_probe_checks_non_magnets_and_skips_magnet_network(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    output = tmp_path / "report.json"
    _feed(feed)

    def transport(url: str, _kind: str) -> ResourceProbeResponse:
        if url.endswith(".m3u8"):
            return ResourceProbeResponse(200, "application/vnd.apple.mpegurl", b"#EXTM3U\n")
        return ResourceProbeResponse(200, "text/html", b"ok")

    result = probe_source_resources(
        feed_path=feed,
        output_path=output,
        max_per_provider=20,
        delay_seconds=0,
        transport=transport,
    )
    assert result.status == "pass"
    assert result.selected_count == 2
    assert result.skipped_magnet_count == 1


def test_resource_probe_rejects_non_playlist_m3u8(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    _feed(feed)
    result = probe_source_resources(
        feed_path=feed,
        output_path=tmp_path / "report.json",
        delay_seconds=0,
        transport=lambda _url, _kind: ResourceProbeResponse(200, "text/html", b"not-playlist"),
    )
    assert result.status == "fail"
    assert result.failed_count >= 1
