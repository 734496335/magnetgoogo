#!/usr/bin/env python3
"""Serve a device-local update config and APK for Android in-app update E2E tests."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--latest-version", default="0.2.5")
    parser.add_argument("--min-version", default="0.1.10")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    apk = args.apk.resolve()
    if not apk.is_file():
        raise SystemExit(f"APK not found: {apk}")

    config = {
        "latest_version": args.latest_version,
        "min_version": args.min_version,
        "download": {
            "primary": f"http://127.0.0.1:{args.port}/magnetgoogo-v{args.latest_version}.apk",
            "mirrors": [],
        },
        "announcement": "0.2.3 → 0.2.5 本地App内更新全链路测试",
        "source_expiry_hours": 72,
        "source_schema_version": 1,
        "updated_at": "2026-08-04T21:40:00+08:00",
    }
    config_bytes = json.dumps(config, ensure_ascii=False).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        server_version = "MagGoogoUpdateE2E/1.0"

        def log_message(self, fmt: str, *values: object) -> None:
            print(json.dumps({"client": self.client_address[0], "message": fmt % values}, ensure_ascii=False), flush=True)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/health":
                self._send_bytes(b"ok\n", "text/plain; charset=utf-8")
                return
            if path == "/config.json":
                self._send_bytes(config_bytes, "application/json; charset=utf-8")
                return
            if path == f"/magnetgoogo-v{args.latest_version}.apk":
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(apk.name)[0] or "application/vnd.android.package-archive")
                self.send_header("Content-Length", str(apk.stat().st_size))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with apk.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        self.wfile.write(chunk)
                return
            self.send_error(404)

        def _send_bytes(self, payload: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(json.dumps({"status": "READY", "port": args.port, "apk": str(apk), "bytes": apk.stat().st_size}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
