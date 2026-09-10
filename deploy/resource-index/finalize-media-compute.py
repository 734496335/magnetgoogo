from __future__ import annotations

import argparse
import json

from magnet.resource_index.pipeline.media_compute_finalize import finalize_compute_handoff
from magnet.resource_index.pipeline.media_daily import load_media_daily_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--force-publish", action="store_true")
    args = parser.parse_args()
    result = finalize_compute_handoff(load_media_daily_config(args.config), package_path=args.package, publish=args.publish, force_publish=args.force_publish)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
