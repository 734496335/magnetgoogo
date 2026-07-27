"""Idempotently install the media location include in the existing HTTPS server block."""

import argparse
import datetime as dt
import os
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INCLUDE_LINE = "    include /etc/nginx/snippets/magnetgoogo-media.conf;"
ANCHOR = "    index index.html;"
ROOT_MARKER = "    root /var/www/magnetgoogo-site;"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--snippet-source", required=True)
    parser.add_argument("--snippet-target", required=True)
    args = parser.parse_args()

    config = Path(args.config)
    snippet_source = Path(args.snippet_source)
    snippet_target = Path(args.snippet_target)
    text = config.read_text(encoding="utf-8")
    if text.count(ROOT_MARKER) != 1:
        raise RuntimeError("expected exactly one magnetgoogo site root marker")
    if INCLUDE_LINE not in text:
        root_index = text.index(ROOT_MARKER)
        anchor_index = text.find(ANCHOR, root_index)
        if anchor_index < 0:
            raise RuntimeError("HTTPS server index anchor was not found")
        insert_at = anchor_index + len(ANCHOR)
        text = text[:insert_at] + "\n" + INCLUDE_LINE + text[insert_at:]
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = config.with_name(f"{config.name}.media-backup-{stamp}")
        shutil.copy2(config, backup)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{config.name}.", suffix=".tmp", dir=config.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, config)
        finally:
            if temporary.exists():
                temporary.unlink()

    snippet_target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{snippet_target.name}.", suffix=".tmp", dir=snippet_target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(snippet_source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, snippet_target)
    finally:
        if temporary.exists():
            temporary.unlink()
    print("NGINX_MEDIA_INCLUDE_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
