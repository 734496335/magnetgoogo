from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline.media_compute_finalize import finalize_compute_handoff
from magnet.resource_index.pipeline.media_daily import load_media_daily_config


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_status(path_value: str | None, payload: dict[str, object]) -> None:
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--force-publish", action="store_true")
    parser.add_argument("--status-file")
    args = parser.parse_args()
    mode = "publish" if args.publish else "candidate"
    started_at = _utc_now()
    try:
        result = finalize_compute_handoff(
            load_media_daily_config(args.config),
            package_path=args.package,
            publish=args.publish,
            force_publish=args.force_publish,
        )
    except Exception as exc:
        error: dict[str, object] = {"type": type(exc).__name__, "message": str(exc)}
        if isinstance(exc, ResourceIndexError):
            error.update({"error_code": exc.error_code, "context": exc.context})
        _write_status(
            args.status_file,
            {
                "schema_version": "media-compute-finalizer-status/1",
                "status": "failed",
                "mode": mode,
                "started_at": started_at,
                "finished_at": _utc_now(),
                "package": Path(args.package).name,
                "error": error,
            },
        )
        raise
    _write_status(
        args.status_file,
        {
            "schema_version": "media-compute-finalizer-status/1",
            "status": "success",
            "mode": mode,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "package": Path(args.package).name,
            "result": result,
        },
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
