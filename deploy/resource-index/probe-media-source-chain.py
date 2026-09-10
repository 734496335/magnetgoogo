from __future__ import annotations

import argparse
import json
from pathlib import Path

from magnet.resource_index.pipeline.media_source_chain_probe import (
    DEFAULT_MEDIA_SOURCE_IDS,
    probe_media_sources,
)
from magnet.resource_index.release.protocol import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", choices=DEFAULT_MEDIA_SOURCE_IDS)
    parser.add_argument("--candidate-limit", type=int, default=3)
    parser.add_argument("--output")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    source_ids = tuple(args.source or DEFAULT_MEDIA_SOURCE_IDS)
    report = probe_media_sources(source_ids, candidate_limit=args.candidate_limit)
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.parent / f".{output.name}.tmp"
        temporary.write_bytes(canonical_json_bytes(report))
        temporary.replace(output)
    if args.pretty:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
