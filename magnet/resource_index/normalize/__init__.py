"""Normalization helpers."""

from magnet.resource_index.normalize.content_code import normalize_content_code, require_content_code
from magnet.resource_index.normalize.magnets import extract_info_hash, normalize_magnet_uri
from magnet.resource_index.normalize.sizes import parse_size_bytes
from magnet.resource_index.normalize.text import normalize_title, normalize_whitespace

__all__ = [
    "normalize_content_code",
    "require_content_code",
    "extract_info_hash",
    "normalize_magnet_uri",
    "parse_size_bytes",
    "normalize_title",
    "normalize_whitespace",
]
