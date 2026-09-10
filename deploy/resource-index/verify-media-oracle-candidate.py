from __future__ import annotations

import argparse
import json
from pathlib import Path

from magnet.resource_index.pipeline.media_daily import load_media_daily_config
from magnet.resource_index.pipeline.media_oracle_acceptance import verify_oracle_media_candidate
from magnet.resource_index.release.protocol import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--r2-before", required=True)
    parser.add_argument("--r2-after", required=True)
    parser.add_argument("--aliyun-before", required=True)
    parser.add_argument("--aliyun-after", required=True)
    parser.add_argument("--allow-partial-freshness-group", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    status = json.loads(Path(args.status).read_text(encoding="utf-8-sig"))
    config = load_media_daily_config(args.config)
    report = verify_oracle_media_candidate(
        status=status,
        config=config,
        r2_before=Path(args.r2_before).read_bytes(),
        r2_after=Path(args.r2_after).read_bytes(),
        aliyun_before=Path(args.aliyun_before).read_bytes(),
        aliyun_after=Path(args.aliyun_after).read_bytes(),
        require_all_group_members_fresh=not args.allow_partial_freshness_group,
    )
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.parent / f".{output.name}.tmp"
        temporary.write_bytes(canonical_json_bytes(report))
        temporary.replace(output)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
