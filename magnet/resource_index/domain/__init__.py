"""Domain package."""

from magnet.resource_index.domain.enums import ContentType, DocumentType, PersonRole
from magnet.resource_index.domain.models import ContentItem, ParsedContentBundle

__all__ = [
    "ContentType",
    "DocumentType",
    "PersonRole",
    "ContentItem",
    "ParsedContentBundle",
]
