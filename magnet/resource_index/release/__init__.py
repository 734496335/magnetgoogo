"""Content-addressed media release protocol and local staging builder."""

from magnet.resource_index.release.builder import (
    MediaReleaseBuildResult,
    MediaReleaseConfig,
    build_media_release,
    verify_media_release,
)
from magnet.resource_index.release.protocol import (
    generate_ed25519_keypair,
    sign_document,
    verify_document,
)

__all__ = [
    "MediaReleaseBuildResult",
    "MediaReleaseConfig",
    "build_media_release",
    "verify_media_release",
    "generate_ed25519_keypair",
    "sign_document",
    "verify_document",
]
