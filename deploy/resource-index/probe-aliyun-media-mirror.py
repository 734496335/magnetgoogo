from __future__ import annotations

import argparse
import json

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.pipeline.media_daily import _aliyun_publisher, load_media_daily_config
from magnet.resource_index.publish.ssh_static_mirror import SshStaticMirrorPublisher


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = load_media_daily_config(args.config)
    publisher = _aliyun_publisher(config)
    if not isinstance(publisher, SshStaticMirrorPublisher):
        raise ResourceIndexError(CONFIG_ERROR, "Oracle mirror probe requires an SSH Aliyun publisher", {})
    report = publisher.healthcheck()
    print(
        json.dumps(
            {
                "schema_version": "media-aliyun-mirror-probe/1",
                "status": "pass",
                "backend": publisher.name,
                "destination": publisher.destination,
                "remote": report,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
