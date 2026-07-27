"""Remote publishers for verified media release bundles."""

from magnet.resource_index.publish.base import (
    PublishedObject,
    PublisherBackend,
    UploadOutcome,
    UploadRequest,
)
from magnet.resource_index.publish.orchestrator import (
    MediaPublishConfig,
    MediaPublishResult,
    publish_media_release,
)
from magnet.resource_index.publish.r2 import R2PublisherBackend
from magnet.resource_index.publish.worker_bridge import WorkerR2PublisherBackend

__all__ = [
    "PublishedObject",
    "PublisherBackend",
    "UploadOutcome",
    "UploadRequest",
    "MediaPublishConfig",
    "MediaPublishResult",
    "publish_media_release",
    "R2PublisherBackend",
    "WorkerR2PublisherBackend",
]
