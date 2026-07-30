"""Safe deterministic normalization for offline media cover images."""

from __future__ import annotations

import hashlib
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError

_MAX_SOURCE_BYTES = 12 * 1024 * 1024
_MAX_SOURCE_PIXELS = 40_000_000
_MAX_WIDTH = 720
_MAX_HEIGHT = 1080
_TARGET_BYTES = 96 * 1024


def normalize_cover_image(raw: bytes) -> tuple[bytes, str, int, int, str]:
    """Validate, orient, resize and encode one cover as bounded progressive JPEG."""
    if not raw or len(raw) > _MAX_SOURCE_BYTES:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "cover payload is empty or too large",
            {"byte_size": len(raw)},
        )
    try:
        with Image.open(BytesIO(raw)) as opened:
            opened.verify()
        with Image.open(BytesIO(raw)) as opened:
            width, height = opened.size
            if width <= 0 or height <= 0 or width * height > _MAX_SOURCE_PIXELS:
                raise ResourceIndexError(
                    CONFIG_ERROR,
                    "cover dimensions are invalid or excessive",
                    {"width": width, "height": height},
                )
            image = ImageOps.exif_transpose(opened)
            image.thumbnail((_MAX_WIDTH, _MAX_HEIGHT), Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "L"}:
                background = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A") if "A" in image.getbands() else None
                background.paste(image.convert("RGB"), mask=alpha)
                image = background
            elif image.mode == "L":
                image = image.convert("RGB")
            else:
                image = image.copy()

        encoded = b""
        for maximum, quality in (
            ((_MAX_WIDTH, _MAX_HEIGHT), 82),
            ((640, 960), 76),
            ((560, 840), 70),
            ((480, 720), 64),
            ((420, 630), 58),
        ):
            candidate = image.copy()
            candidate.thumbnail(maximum, Image.Resampling.LANCZOS)
            output = BytesIO()
            candidate.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )
            encoded = output.getvalue()
            image = candidate
            if len(encoded) <= _TARGET_BYTES:
                break
        width, height = image.size
    except ResourceIndexError:
        raise
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError) as exc:
        raise ResourceIndexError(
            CONFIG_ERROR,
            "cover payload is not a valid image",
            {},
        ) from exc
    digest = hashlib.sha256(encoded).hexdigest()
    return encoded, "image/jpeg", width, height, digest
